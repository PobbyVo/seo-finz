from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.domain.semrush_parser import validate_organic_url
from app.domain.taxonomy_parser import normalize_text
from app.models import (
    Approval,
    ContentBrief,
    DemandGroup,
    EvidenceRow,
    FileUpload,
    KeywordMapping,
    Project,
    ResearchBatch,
    SourceKeyword,
)

POLICY_VERSION = "1.6.2"
MIN_ORGANIC_URLS_FOR_SERP_VERIFIED = 3
TOP_10_RANKS = set(range(1, 11))

VALID_FORMULA_IDS = {
    "AIDA", "PAS", "BAB", "FAB", "4P", "APP", "QUEST",
    "ACC", "SLAP", "4U", "Checklist", "Q&A", "Storytelling",
}
VALID_TACTIC_CODES = {f"T{i:02d}" for i in range(1, 17)}


def valid_source_refs_for_project(db: Session, project: Project) -> set[str]:
    refs: set[str] = set()
    if project.topic_pillar_code:
        refs.add(f"TOPIC:{project.topic_pillar_code}")
        refs.add(project.topic_pillar_code)
    if project.content_code:
        refs.add(f"CONTENT:{project.content_code}")
        refs.add(project.content_code)
    for sk in db.query(SourceKeyword).filter(SourceKeyword.project_id == project.id).all():
        if sk.source_ref:
            refs.add(sk.source_ref)
        if sk.content_code:
            refs.add(f"CONTENT:{sk.content_code}")
            refs.add(sk.content_code)
        if sk.topic_pillar_code:
            refs.add(f"TOPIC:{sk.topic_pillar_code}")
            refs.add(sk.topic_pillar_code)
    if not refs:
        refs.add(f"TOPIC:{project.code}")
        refs.add(project.code)
    return refs


def _make_blocker(
    code: str,
    reason: str,
    impact: str,
    solution: str,
    next_action: str,
    cta_label: str = "Xem chi tiết",
    cta_href: str = "/steps/05-evidence",
) -> dict[str, str]:
    return {
        "code": code,
        "reason": reason,
        "impact": impact,
        "solution": solution,
        "next_action": next_action,
        "cta_label": cta_label,
        "cta_href": cta_href,
    }


def compute_file_sha256_streaming(file_path: Path, chunk_size: int = 65536) -> tuple[str, int]:
    """Stream-hash a stored file in bounded chunks; returns (sha256_hex, size_bytes)."""
    h = hashlib.sha256()
    total = 0
    with file_path.open("rb") as fh:
        while True:
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
            total += len(chunk)
    return h.hexdigest(), total


def compute_batch_manifest_sha256(
    batch: ResearchBatch,
    upload_sha256: str,
    batch_rows: list[EvidenceRow],
) -> str:
    """
    Canonical tamper-evident SHA-256 manifest covering batch metadata, upload SHA-256,
    and EVERY normalized + raw EvidenceRow in the batch (never just first 5 rows).
    """
    sorted_rows = sorted(
        batch_rows,
        key=lambda r: (
            r.source_row_number if r.source_row_number is not None else 0,
            r.row_type or "",
            r.keyword_normalized or "",
            r.organic_position if r.organic_position is not None else -1,
            (r.organic_url or "").strip().lower(),
            r.id or "",
        ),
    )
    h = hashlib.sha256()
    header_payload = {
        "manifest_version": "1.6.2",
        "project_id": batch.project_id,
        "report_type": (batch.report_type or "").upper(),
        "market": (batch.market or "VN").upper(),
        "locale": batch.locale or "en-US",
        "upload_sha256": (upload_sha256 or "").strip().lower(),
        "total_raw_rows": int(batch.total_raw_rows or 0),
        "total_normalized_rows": int(batch.total_normalized_rows or 0),
        "duplicate_rows_detected": int(batch.duplicate_rows_detected or 0),
        "stored_rows_count": len(sorted_rows),
    }
    h.update(json.dumps(header_payload, sort_keys=True, ensure_ascii=False).encode("utf-8"))
    h.update(b"\n")
    for r in sorted_rows:
        raw_digest = hashlib.sha256((r.raw_row_json or "").encode("utf-8")).hexdigest()
        row_sig = {
            "row_no": r.source_row_number,
            "project_id": r.project_id,
            "row_type": r.row_type,
            "kw": r.keyword_normalized,
            "vol": r.volume,
            "kd": r.kd,
            "intent": r.intent,
            "cpc": r.cpc,
            "sf": r.serp_features,
            "url": r.organic_url,
            "pos": r.organic_position,
            "pt": r.organic_page_type,
            "srt": getattr(r, "serp_result_type", "ORGANIC"),
            "dom": getattr(r, "organic_domain", ""),
            "valid": bool(getattr(r, "organic_valid", True)),
            "market": (r.market or "").upper(),
            "dup": bool(r.is_duplicate),
            "raw_sha": raw_digest,
        }
        h.update(json.dumps(row_sig, sort_keys=True, ensure_ascii=False).encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()


def _batch_sort_key(batch: ResearchBatch | None) -> tuple[float, int, float, str]:
    """Deterministic total ordering for ResearchBatches independent of SQL retrieval order."""
    if batch is None:
        return (0.0, 0, 0.0, "")
    obs = getattr(batch, "source_observation_at", None) or batch.source_timestamp or batch.created_at
    crt = batch.created_at or batch.source_timestamp
    obs_ts = obs.replace(tzinfo=timezone.utc).timestamp() if (obs and obs.tzinfo is None) else (obs.timestamp() if obs else 0.0)
    crt_ts = crt.replace(tzinfo=timezone.utc).timestamp() if (crt and crt.tzinfo is None) else (crt.timestamp() if crt else 0.0)
    seq = int(getattr(batch, "import_seq", 0) or 0)
    # When source_observation_at is explicitly present, prioritize observation time; otherwise monotonic import_seq dominates same-second imports
    has_obs = 1.0 if getattr(batch, "source_observation_at", None) is not None else 0.0
    if has_obs:
        return (obs_ts, seq, crt_ts, batch.id)
    return (float(seq) if seq > 0 else obs_ts, seq, crt_ts, batch.id)


def verify_batch_integrity_detailed(
    batch: ResearchBatch | None,
    uploads_by_id: dict[str, FileUpload],
    evidence_rows: list[EvidenceRow],
    *,
    verify_disk: bool = True,
    disk_hash_cache: dict[str, tuple[bool, str, int, str]] | None = None,
) -> dict[str, Any]:
    """
    Full F2 batch integrity validation:
    - Validates batch ownership, status, upload ownership/confirmation, SHA-256 format & disk bytes.
    - Validates EVERY EvidenceRow in the batch (never only the first 5 rows!).
    - Recomputes exact normalized & duplicate counts and full canonical manifest SHA-256.
    - Classifies:
      * VERIFIED: complete manifest + rows + disk file match.
      * UNVERIFIED: legacy batch missing manifest_sha256 (never falsely PASSED!).
      * FAILED: tampered rows/file, missing file, count mismatch, or provenance anomaly.
    """
    if batch is None:
        return {
            "status": "FAILED",
            "ok": False,
            "disk_verified": False,
            "manifest_verified": False,
            "issues": ["Chưa có ResearchBatch gắn với bằng chứng này."],
        }

    issues: list[str] = []
    failed = False
    unverified = False
    disk_verified = False
    manifest_verified = False

    if batch.status != "PROCESS_COMPLETED":
        failed = True
        issues.append(f"Batch {batch.id} chưa hoàn tất kỹ thuật (status={batch.status}).")

    if batch.total_raw_rows <= 0 or batch.total_normalized_rows < 0:
        failed = True
        issues.append(f"Batch {batch.id} có số dòng không hợp lệ ({batch.total_raw_rows}/{batch.total_normalized_rows}).")
    if batch.total_normalized_rows > batch.total_raw_rows:
        failed = True
        issues.append(f"Batch {batch.id} có số dòng chuẩn hóa vượt dòng thô.")

    upl: FileUpload | None = None
    if not batch.file_upload_id:
        failed = True
        issues.append(f"Batch {batch.id} thiếu liên kết FileUpload nguồn.")
    else:
        upl = uploads_by_id.get(batch.file_upload_id)
        if not upl:
            failed = True
            issues.append(f"Thiếu bản ghi FileUpload {batch.file_upload_id} cho batch {batch.id}.")
        else:
            if upl.project_id != batch.project_id:
                failed = True
                issues.append(f"FileUpload {upl.id} không thuộc cùng dự án với batch {batch.id}.")
            if upl.status != "CONFIRMED":
                failed = True
                issues.append(f"FileUpload {upl.id} chưa được xác nhận import (status={upl.status}).")
            sha_clean = (upl.sha256 or "").strip().lower()
            if len(sha_clean) != 64 or any(c not in "0123456789abcdef" for c in sha_clean):
                failed = True
                issues.append(f"FileUpload {upl.id} thiếu hoặc sai định dạng mã băm SHA-256.")
            elif getattr(batch, "source_file_sha256", "") and batch.source_file_sha256.lower() != sha_clean:
                failed = True
                issues.append(f"SHA-256 của batch {batch.id} không khớp với FileUpload {upl.id}.")

            # Bounded per-request disk verification (each file path hashed at most once via disk_hash_cache)
            if verify_disk and not failed:
                sp = upl.stored_path or ""
                if not sp:
                    failed = True
                    issues.append(f"FileUpload {upl.id} thiếu đường dẫn tệp nguồn lưu trữ.")
                else:
                    cached = disk_hash_cache.get(sp) if disk_hash_cache is not None else None
                    if cached is None:
                        p = Path(sp)
                        if not p.exists() or not p.is_file():
                            cached = (False, "", 0, f"Tệp nguồn trên đĩa không còn tồn tại ({p.name}).")
                        else:
                            try:
                                d_sha, d_size = compute_file_sha256_streaming(p)
                                cached = (True, d_sha, d_size, "")
                            except OSError as exc:
                                cached = (False, "", 0, f"Lỗi đọc tệp nguồn trên đĩa ({exc}).")
                        if disk_hash_cache is not None:
                            disk_hash_cache[sp] = cached
                    ok_read, d_sha, d_size, read_err = cached
                    if not ok_read:
                        failed = True
                        issues.append(f"Batch {batch.id}: {read_err}")
                    elif d_sha.lower() != sha_clean or (upl.size_bytes and d_size != upl.size_bytes):
                        failed = True
                        issues.append(
                            f"Batch {batch.id}: Tệp nguồn '{upl.filename}' trên đĩa đã bị sửa đổi so với SHA-256 lúc xác nhận import."
                        )
                    else:
                        disk_verified = True

    batch_rows = [r for r in evidence_rows if r.batch_id == batch.id]
    expected_row_type = "ORGANIC_RESULTS" if (batch.report_type or "").upper() == "ORGANIC_RESULTS" else "METRICS"
    batch_market = (batch.market or "VN").upper()

    if not batch_rows:
        failed = True
        issues.append(f"Batch {batch.id} không có dòng EvidenceRow nào trong SQLite.")
    else:
        bad_project_rows = 0
        bad_raw_rows = 0
        bad_market_rows = 0
        bad_type_rows = 0
        actual_norm_count = 0
        actual_dup_count = 0

        for r in batch_rows:
            if r.project_id != batch.project_id:
                bad_project_rows += 1
            if r.row_type != expected_row_type:
                bad_type_rows += 1
            if (r.market or "").upper() != batch_market:
                bad_market_rows += 1
            raw_txt = (r.raw_row_json or "").strip()
            if not raw_txt or raw_txt == "{}":
                # Check if JSON parses cleanly; allow non-empty valid JSON object
                if not raw_txt:
                    bad_raw_rows += 1
            else:
                try:
                    parsed_raw = json.loads(raw_txt)
                    if not isinstance(parsed_raw, dict):
                        bad_raw_rows += 1
                except ValueError:
                    bad_raw_rows += 1

            if r.is_duplicate:
                actual_dup_count += 1
            if expected_row_type == "ORGANIC_RESULTS":
                if getattr(r, "organic_valid", True) and not r.is_duplicate:
                    actual_norm_count += 1
            else:
                if not r.is_duplicate:
                    actual_norm_count += 1

        if bad_project_rows:
            failed = True
            issues.append(f"Batch {batch.id} có {bad_project_rows} dòng lệch project_id.")
        if bad_type_rows:
            failed = True
            issues.append(f"Batch {batch.id} có {bad_type_rows} dòng lệch loại báo cáo ({expected_row_type}).")
        if bad_market_rows:
            failed = True
            issues.append(f"Batch {batch.id} có {bad_market_rows} dòng lệch thị trường ({batch_market}).")
        if bad_raw_rows:
            failed = True
            issues.append(f"Batch {batch.id} có {bad_raw_rows} dòng thiếu hoặc hỏng raw_row_json.")
        if actual_norm_count != int(batch.total_normalized_rows or 0):
            failed = True
            issues.append(
                f"Batch {batch.id} lệch số dòng chuẩn hóa (ghi nhận {batch.total_normalized_rows}, thực tế {actual_norm_count})."
            )
        if actual_dup_count != int(batch.duplicate_rows_detected or 0):
            failed = True
            issues.append(
                f"Batch {batch.id} lệch số dòng trùng lặp (ghi nhận {batch.duplicate_rows_detected}, thực tế {actual_dup_count})."
            )
        if expected_row_type == "ORGANIC_RESULTS" and len(batch_rows) != int(batch.total_raw_rows or 0):
            failed = True
            issues.append(
                f"Batch {batch.id} (ORGANIC_RESULTS) lưu {len(batch_rows)} dòng nhưng báo {batch.total_raw_rows} dòng thô."
            )
        if expected_row_type == "METRICS" and len(batch_rows) > int(batch.total_raw_rows or 0):
            failed = True
            issues.append(
                f"Batch {batch.id} (METRICS) lưu nhiều dòng hơn tổng dòng thô ({len(batch_rows)} > {batch.total_raw_rows})."
            )

    # Full manifest check across ALL rows (closes first-5-only tampering gap!)
    recorded_manifest = getattr(batch, "manifest_sha256", None)
    if not failed:
        if not recorded_manifest:
            unverified = True
            issues.append(
                f"Batch cũ {batch.id} chưa có import manifest (UNVERIFIED — cần xác minh lại tệp nguồn trước khi F2 đạt PASSED)."
            )
        elif upl is not None:
            recomputed = compute_batch_manifest_sha256(batch, upl.sha256, batch_rows)
            if recomputed != recorded_manifest:
                failed = True
                issues.append(
                    f"Batch {batch.id}: Dữ liệu EvidenceRow trong SQLite không khớp với import manifest (phát hiện thay đổi sau khi import)."
                )
            else:
                manifest_verified = True

    if failed:
        status = "FAILED"
    elif unverified:
        status = "UNVERIFIED"
    else:
        status = "VERIFIED"

    return {
        "status": status,
        "ok": status == "VERIFIED",
        "disk_verified": disk_verified,
        "manifest_verified": manifest_verified,
        "issues": issues,
    }


def verify_batch_integrity(
    batch: ResearchBatch | None,
    uploads_by_id: dict[str, FileUpload],
    evidence_rows: list[EvidenceRow],
    *,
    verify_disk: bool = True,
) -> tuple[bool, list[str]]:
    """Backward-compatible tuple wrapper returning (is_verified, issues)."""
    res = verify_batch_integrity_detailed(batch, uploads_by_id, evidence_rows, verify_disk=verify_disk)
    return bool(res["ok"]), list(res["issues"])


def select_effective_metrics_row(
    project: Project,
    keyword: str,
    evidence_rows: list[EvidenceRow],
    batches_by_id: dict[str, ResearchBatch],
) -> tuple[EvidenceRow | None, ResearchBatch | None, list[EvidenceRow]]:
    """
    Deterministically select the latest confirmed metrics row for exact `(project, keyword, market)`.
    NEVER borrows from another keyword, another market, or arbitrary SQL retrieval order.
    """
    kw_norm = normalize_text(keyword)
    proj_market = (project.market or "VN").upper()
    if not kw_norm:
        return None, None, []

    matching_all = [
        r for r in evidence_rows
        if r.project_id == project.id
        and r.row_type == "METRICS"
        and not r.is_duplicate
        and r.keyword_normalized == kw_norm
    ]
    matching_market = [
        r for r in matching_all
        if (r.market or proj_market).upper() == proj_market
    ]
    if not matching_market:
        return None, None, matching_all

    # Deterministic selection by latest coherent batch order (then source_row_number tie-break)
    best_row = max(
        matching_market,
        key=lambda r: (_batch_sort_key(batches_by_id.get(r.batch_id)), -(r.source_row_number or 0), r.id),
    )
    return best_row, batches_by_id.get(best_row.batch_id), matching_all


def compute_metrics_evidence_hash(
    m_row: EvidenceRow | None,
    m_batch: ResearchBatch | None,
    market: str,
) -> str:
    """
    Canonical semantic SHA-256 digest of the active metrics observation.
    - Changes immediately when Volume, KD, Intent, CPC, SERP features, market, or report_type change.
    - Remains IDENTICAL across re-imports of semantically identical files (no random UUID churn).
    """
    if m_row is None:
        return ""
    payload = {
        "policy_version": POLICY_VERSION,
        "keyword_normalized": m_row.keyword_normalized,
        "market": (m_row.market or market or "VN").upper(),
        "report_type": (m_batch.report_type if m_batch else "KEYWORD_OVERVIEW").upper(),
        "volume": m_row.volume,
        "kd": round(float(m_row.kd), 4) if m_row.kd is not None else None,
        "intent": (m_row.intent or "").strip().lower(),
        "cpc": round(float(m_row.cpc), 4) if m_row.cpc is not None else None,
        "serp_features": (m_row.serp_features or "").strip().lower(),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _evaluate_single_serp_snapshot(
    project: Project,
    keyword: str,
    kw_norm: str,
    proj_market: str,
    batch_id: str,
    batch_rows: list[EvidenceRow],
    batch: ResearchBatch | None,
    uploads_by_id: dict[str, FileUpload],
    batch_integrity: dict[str, Any] | None,
) -> dict[str, Any]:
    """Evaluate ONE single coherent SERP report batch without ever merging across batches."""
    valid_by_url: dict[str, EvidenceRow] = {}
    ai_overview_count = 0
    non_organic_count = 0
    rejected_market_count = 0
    rejected_invalid_count = 0
    duplicate_url_count = 0
    page_type_counts: dict[str, int] = {}
    rank_counts: dict[int, int] = {}

    for r in batch_rows:
        row_market = (r.market or "").upper()
        if row_market and proj_market and row_market != proj_market:
            rejected_market_count += 1
            continue

        rtype = (getattr(r, "serp_result_type", None) or "ORGANIC").upper()
        if rtype == "AI_OVERVIEW":
            ai_overview_count += 1
            continue
        if rtype != "ORGANIC":
            non_organic_count += 1
            continue

        url_ok, canonical_url, _domain = validate_organic_url(r.organic_url)
        pos_ok = r.organic_position is not None and r.organic_position >= 1
        row_flag_valid = getattr(r, "organic_valid", True)
        if not row_flag_valid or not url_ok or not pos_ok:
            rejected_invalid_count += 1
            continue

        url_key = canonical_url.lower()
        existing = valid_by_url.get(url_key)
        if existing is not None:
            duplicate_url_count += 1
            if r.organic_position is not None and (
                existing.organic_position is None or r.organic_position < existing.organic_position
            ):
                valid_by_url[url_key] = r
        else:
            valid_by_url[url_key] = r

    unique_rows = sorted(
        valid_by_url.values(),
        key=lambda x: (
            x.organic_position if x.organic_position is not None else 9999,
            validate_organic_url(x.organic_url)[1].lower(),
            x.source_row_number,
        ),
    )

    positions_covered: list[int] = []
    for r in unique_rows:
        pt = (r.organic_page_type or "UNKNOWN").upper()
        page_type_counts[pt] = page_type_counts.get(pt, 0) + 1
        if r.organic_position is not None:
            positions_covered.append(r.organic_position)
            rank_counts[r.organic_position] = rank_counts.get(r.organic_position, 0) + 1

    top10_covered = sorted(p for p in set(positions_covered) if 1 <= p <= 10)
    top10_missing = sorted(TOP_10_RANKS - set(top10_covered))
    duplicate_ranks = sorted(pos for pos, cnt in rank_counts.items() if cnt > 1)
    unique_count = len(unique_rows)

    # Provenance & certification checks for this single snapshot
    provenance_issues: list[str] = []
    upl = uploads_by_id.get(batch.file_upload_id) if (batch and batch.file_upload_id) else None
    if batch is None:
        provenance_issues.append(f"Thiếu bản ghi ResearchBatch {batch_id}.")
    else:
        if batch.project_id != project.id:
            provenance_issues.append("Batch SERP không thuộc dự án này.")
        if batch.status != "PROCESS_COMPLETED":
            provenance_issues.append(f"Batch SERP chưa hoàn tất kỹ thuật (status={batch.status}).")
        if batch.market and batch.market.upper() != proj_market:
            provenance_issues.append(f"Thị trường batch ({batch.market}) lệch dự án ({proj_market}).")
        if getattr(batch, "keyword_binding_source", "COLUMN") == "NONE":
            provenance_issues.append("Tệp SERP thiếu cột Keyword và chưa có ràng buộc từ khóa mục tiêu rõ ràng.")
    if upl is None or upl.status != "CONFIRMED" or not (upl.sha256 or "").strip():
        provenance_issues.append("Thiếu FileUpload đã xác nhận hoặc thiếu SHA-256 nguồn.")
    if batch_integrity is not None and not batch_integrity.get("ok"):
        provenance_issues.append(
            f"Batch SERP chưa đạt toàn vẹn F2 (status={batch_integrity.get('status')}): "
            + "; ".join(batch_integrity.get("issues") or [])
        )
    if duplicate_ranks:
        provenance_issues.append(
            f"Phát hiện xung đột thứ hạng Organic trùng lặp trong cùng snapshot tại vị trí {duplicate_ranks[:6]} — không thể chứng nhận snapshot."
        )

    certifiable = len(provenance_issues) == 0

    if unique_count == 0 or not certifiable:
        if not certifiable and unique_count > 0:
            serp_tier = "PARTIAL_SERP_EVIDENCE" if unique_count < MIN_ORGANIC_URLS_FOR_SERP_VERIFIED else "SERP_NOT_VERIFIED"
            serp_status = serp_tier
            top10_verified = False
            sufficiency_reason = (
                f"Snapshot SERP (batch {batch_id}) cho '{keyword}' không đủ điều kiện chứng nhận: "
                + " ".join(provenance_issues)
            )
        else:
            serp_tier = "SERP_NOT_VERIFIED"
            serp_status = "SERP_NOT_VERIFIED"
            top10_verified = False
            sufficiency_reason = (
                f"Chưa có URL organic hợp lệ nào khớp đúng từ khóa '{keyword}' tại thị trường {proj_market}."
            )
    elif unique_count < MIN_ORGANIC_URLS_FOR_SERP_VERIFIED:
        serp_tier = "PARTIAL_SERP_EVIDENCE"
        serp_status = "PARTIAL_SERP_EVIDENCE"
        top10_verified = False
        sufficiency_reason = (
            f"Snapshot mới nhất (batch {batch_id}) chỉ có {unique_count} URL organic cho '{keyword}' "
            f"(cần tối thiểu {MIN_ORGANIC_URLS_FOR_SERP_VERIFIED} URL trong CÙNG 1 snapshot để xác minh dạng trang; không gộp nhiều batch)."
        )
    elif not top10_missing:
        serp_tier = "TOP_10_VERIFIED"
        serp_status = "SERP_VERIFIED"
        top10_verified = True
        sufficiency_reason = (
            f"Đã kiểm chứng đầy đủ Top 10 cho snapshot (vị trí 1–10 trong CÙNG batch {batch_id}, "
            f"tổng {unique_count} URL organic duy nhất) cho '{keyword}' tại thị trường {proj_market}."
        )
    else:
        serp_tier = "SERP_VERIFIED"
        serp_status = "SERP_VERIFIED"
        top10_verified = False
        sufficiency_reason = (
            f"Snapshot (batch {batch_id}) có {unique_count} URL organic xếp hạng hợp lệ cho '{keyword}' "
            f"(đủ xác minh dạng trang cơ bản trong 1 snapshot, chưa đủ Top 10 — thiếu vị trí {top10_missing})."
        )

    dominant_page_type = (
        max(sorted(page_type_counts), key=lambda k: page_type_counts[k])
        if page_type_counts
        else None
    )

    warnings: list[str] = list(provenance_issues)
    if rejected_market_count > 0:
        warnings.append(f"Bỏ qua {rejected_market_count} dòng SERP lệch thị trường (khác {proj_market}).")
    if ai_overview_count > 0:
        warnings.append(f"Đã tách riêng {ai_overview_count} dòng AI Overview khỏi bảng xếp hạng Organic.")
    if non_organic_count > 0:
        warnings.append(f"Đã tách riêng {non_organic_count} dòng phi-Organic khỏi bằng chứng xếp hạng.")
    if rejected_invalid_count > 0:
        warnings.append(f"Loại {rejected_invalid_count} dòng có URL/Position không hợp lệ (vẫn giữ bản thô).")
    if serp_tier == "SERP_VERIFIED" and top10_missing:
        warnings.append(
            f"Chưa đủ bằng chứng Top 10 hoàn chỉnh trong snapshot này (thiếu vị trí {top10_missing}); không được đóng dấu Top 10 Verified."
        )

    # Full canonical SHA-256 over ALL valid supporting rows in this single coherent snapshot (NEVER truncated to 20!)
    full_sig_payload = {
        "policy_version": POLICY_VERSION,
        "keyword_normalized": kw_norm,
        "market": proj_market,
        "serp_tier": serp_tier,
        "top10_verified": top10_verified,
        "certifiable": certifiable,
        "rows": [
            {
                "pos": r.organic_position,
                "url": validate_organic_url(r.organic_url)[1].lower(),
                "rt": (getattr(r, "serp_result_type", None) or "ORGANIC").upper(),
                "pt": (r.organic_page_type or "UNKNOWN").upper(),
            }
            for r in unique_rows
        ],
    }
    serp_evidence_hash = (
        hashlib.sha256(
            json.dumps(full_sig_payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        if (unique_rows or not certifiable)
        else ""
    )

    obs_dt = getattr(batch, "source_observation_at", None) if batch else None
    ing_dt = (batch.source_timestamp or batch.created_at) if batch else None
    eff_dt = obs_dt or ing_dt
    snapshot_identity = {
        "project_id": project.id,
        "keyword_normalized": kw_norm,
        "market": proj_market,
        "batch_id": batch_id,
        "file_upload_id": batch.file_upload_id if batch else None,
        "file_sha256": upl.sha256 if upl else "",
        "observed_at": eff_dt.isoformat() if eff_dt else None,
        "timestamp_kind": "SOURCE_OBSERVED" if obs_dt is not None else "INGESTED_AT",
        "device": "UNKNOWN",
        "location": proj_market,
        "language": project.language or "UNKNOWN",
        "keyword_binding_source": getattr(batch, "keyword_binding_source", "COLUMN") if batch else "NONE",
        "live_serp_freshness_claim": "HISTORICAL_SNAPSHOT_ONLY",
    }

    return {
        "batch": batch,
        "batch_id": batch_id,
        "sort_key": _batch_sort_key(batch),
        "certifiable": certifiable,
        "provenance_issues": provenance_issues,
        "serp_tier": serp_tier,
        "serp_status": serp_status,
        "serp_sufficient": certifiable and serp_tier in ("SERP_VERIFIED", "TOP_10_VERIFIED"),
        "top10_verified": top10_verified,
        "top10_verified_for_snapshot": top10_verified,
        "valid_organic_count": unique_count,
        "unique_ranked_urls": unique_count,
        "top10_positions_covered": top10_covered,
        "top10_positions_missing": top10_missing,
        "duplicate_url_count": duplicate_url_count,
        "duplicate_ranks": duplicate_ranks,
        "ai_overview_count": ai_overview_count,
        "non_organic_count": non_organic_count,
        "rejected_market_count": rejected_market_count,
        "rejected_invalid_count": rejected_invalid_count,
        "file_hashes": [upl.sha256] if (upl and upl.sha256) else [],
        "page_type_distribution": page_type_counts,
        "dominant_page_type_hypothesis": dominant_page_type,
        "sample_urls": [r.organic_url for r in unique_rows[:5] if r.organic_url],
        "rank1_url": (
            next((validate_organic_url(r.organic_url)[1].lower() for r in unique_rows if r.organic_position == 1), None)
        ),
        "serp_evidence_hash": serp_evidence_hash,
        "sufficiency_reason": sufficiency_reason,
        "warnings": warnings,
        "snapshot_identity": snapshot_identity,
    }


def evaluate_serp_for_keyword(
    project: Project,
    keyword: str,
    organic_rows: list[EvidenceRow],
    batches_by_id: dict[str, ResearchBatch],
    uploads_by_id: dict[str, FileUpload],
    *,
    batch_integrity_by_id: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Authoritative per-project, per-keyword, per-market SINGLE-SNAPSHOT SERP provenance evaluator.
    Invariants (Policy v1.6.2):
    - NEVER merges URLs or ranks across distinct ResearchBatch snapshots to construct Top-10 or >=3 URLs!
    - NEVER borrows SERP rows from another keyword or another market.
    - Selects ONE deterministic effective snapshot (latest confirmed matching-market batch by
      observation/ingestion sequence + batch ID tie-break, completely independent of retrieval order).
    - Conservative fail-closed policy: a newer incomplete or conflicting snapshot supersedes older
      snapshots rather than silently cherry-picking an older green batch.
    - Full canonical SHA-256 digest over ALL valid supporting rows in the selected snapshot (not first 20).
    """
    kw_norm = normalize_text(keyword)
    proj_market = (project.market or "VN").upper()

    matching_kw_rows = [
        r for r in organic_rows
        if r.project_id == project.id
        and r.row_type == "ORGANIC_RESULTS"
        and r.keyword_normalized == kw_norm
        and kw_norm != ""
    ]

    # Group strictly by batch_id, filtering out wrong-market batches from candidate snapshot pool
    rows_by_batch: dict[str, list[EvidenceRow]] = {}
    rejected_market_batches = 0
    rejected_market_rows_total = 0
    for r in matching_kw_rows:
        b = batches_by_id.get(r.batch_id)
        eff_market = ((b.market if b else None) or r.market or "").upper()
        if eff_market and proj_market and eff_market != proj_market:
            rejected_market_rows_total += 1
            continue
        rows_by_batch.setdefault(r.batch_id, []).append(r)

    if rejected_market_rows_total > 0:
        rejected_market_batches = len({
            r.batch_id for r in matching_kw_rows
            if (((batches_by_id.get(r.batch_id).market if batches_by_id.get(r.batch_id) else None) or r.market or "").upper() not in ("", proj_market))
        })

    if not rows_by_batch:
        warns = (
            [f"Bỏ qua {rejected_market_rows_total} dòng SERP ({rejected_market_batches} batch) lệch thị trường (khác {proj_market})."]
            if rejected_market_rows_total > 0
            else []
        )
        return {
            "keyword": keyword,
            "keyword_normalized": kw_norm,
            "market": proj_market,
            "serp_file_present": len(matching_kw_rows) > 0,
            "serp_tier": "SERP_NOT_VERIFIED",
            "serp_status": "SERP_NOT_VERIFIED",
            "serp_sufficient": False,
            "top10_verified": False,
            "top10_verified_for_snapshot": False,
            "selected_batch_id": None,
            "snapshot_identity": None,
            "candidate_snapshots_count": 0,
            "conflicts_with_prior_snapshot": False,
            "valid_organic_count": 0,
            "unique_ranked_urls": 0,
            "top10_positions_covered": [],
            "top10_positions_missing": list(range(1, 11)),
            "duplicate_url_count": 0,
            "duplicate_ranks": [],
            "ai_overview_count": 0,
            "non_organic_count": 0,
            "rejected_market_count": rejected_market_rows_total,
            "rejected_invalid_count": 0,
            "batch_ids": [],
            "file_hashes": [],
            "page_type_distribution": {},
            "dominant_page_type_hypothesis": None,
            "sample_urls": [],
            "serp_evidence_hash": "",
            "sufficiency_reason": (
                f"Chưa có snapshot SERP hợp lệ nào khớp đúng từ khóa '{keyword}' tại thị trường {proj_market}."
            ),
            "warnings": warns,
        }

    candidates = [
        _evaluate_single_serp_snapshot(
            project=project,
            keyword=keyword,
            kw_norm=kw_norm,
            proj_market=proj_market,
            batch_id=bid,
            batch_rows=brows,
            batch=batches_by_id.get(bid),
            uploads_by_id=uploads_by_id,
            batch_integrity=(batch_integrity_by_id.get(bid) if batch_integrity_by_id is not None else None),
        )
        for bid, brows in rows_by_batch.items()
    ]
    # Deterministic total order: latest confirmed snapshot wins (never cherry-pick old green over newer incomplete/conflicting)
    candidates.sort(key=lambda c: c["sort_key"])
    selected = candidates[-1]

    conflicts_with_prior = False
    if len(candidates) > 1:
        prior = candidates[-2]
        if selected["rank1_url"] and prior["rank1_url"] and selected["rank1_url"] != prior["rank1_url"]:
            conflicts_with_prior = True
            selected["warnings"].append(
                f"Snapshot mới nhất ({selected['batch_id']}) có URL top 1 khác snapshot trước ({prior['batch_id']}); "
                "hệ thống chọn duy nhất snapshot mới nhất và không gộp dữ liệu hai snapshot."
            )
        elif not selected["serp_sufficient"] and prior["serp_sufficient"]:
            selected["warnings"].append(
                f"Snapshot mới nhất ({selected['batch_id']}) chưa đủ bằng chứng so với snapshot cũ ({prior['batch_id']}); "
                "áp dụng chính sách an toàn không tự giữ trạng thái cũ."
            )

    if rejected_market_rows_total > 0:
        selected["warnings"].append(
            f"Bỏ qua {rejected_market_rows_total} dòng SERP lệch thị trường (khác {proj_market})."
        )

    snap_id = dict(selected["snapshot_identity"])
    snap_id["snapshot_count_for_keyword"] = len(candidates)

    return {
        "keyword": keyword,
        "keyword_normalized": kw_norm,
        "market": proj_market,
        "serp_file_present": True,
        "serp_tier": selected["serp_tier"],
        "serp_status": selected["serp_status"],
        "serp_sufficient": selected["serp_sufficient"],
        "top10_verified": selected["top10_verified"],
        "top10_verified_for_snapshot": selected["top10_verified_for_snapshot"],
        "selected_batch_id": selected["batch_id"],
        "snapshot_identity": snap_id,
        "candidate_snapshots_count": len(candidates),
        "conflicts_with_prior_snapshot": conflicts_with_prior,
        "valid_organic_count": selected["valid_organic_count"],
        "unique_ranked_urls": selected["unique_ranked_urls"],
        "top10_positions_covered": selected["top10_positions_covered"],
        "top10_positions_missing": selected["top10_positions_missing"],
        "duplicate_url_count": selected["duplicate_url_count"],
        "duplicate_ranks": selected["duplicate_ranks"],
        "ai_overview_count": selected["ai_overview_count"],
        "non_organic_count": selected["non_organic_count"],
        "rejected_market_count": selected["rejected_market_count"] + rejected_market_rows_total,
        "rejected_invalid_count": selected["rejected_invalid_count"],
        "batch_ids": [selected["batch_id"]],
        "all_candidate_batch_ids": [c["batch_id"] for c in candidates],
        "file_hashes": selected["file_hashes"],
        "page_type_distribution": selected["page_type_distribution"],
        "dominant_page_type_hypothesis": selected["dominant_page_type_hypothesis"],
        "sample_urls": selected["sample_urls"],
        "serp_evidence_hash": selected["serp_evidence_hash"],
        "sufficiency_reason": selected["sufficiency_reason"],
        "warnings": selected["warnings"],
    }


def compute_mapping_fingerprint(
    *,
    primary_keyword: str,
    secondary_keywords: list[str],
    demand_group_id: str | None,
    proposed_url: str,
    page_type: str,
    market: str,
    metrics_evidence_hash: str = "",
    serp_evidence_hash: str = "",
    priority: str = "P2",
    business_value: str = "MEDIUM",
    effort: str = "MEDIUM",
    # Optional legacy params kept for backward compatibility (random UUIDs intentionally excluded from semantic digest!)
    metrics_evidence_id: str | None = None,
    metrics_batch_id: str | None = None,
    merge_split_proposal: str = "",
) -> str:
    """
    Canonical SHA-256 fingerprint covering every high-impact mapping & semantic evidence field.
    - Changes whenever policy, mapping plan, metrics values/source, or ANY row in the coherent SERP snapshot changes.
    - Stable across identical file re-imports (excludes incidental UUIDs / timestamps) and unrelated keyword imports.
    """
    _ = (metrics_evidence_id, metrics_batch_id, merge_split_proposal)
    canonical = {
        "policy_version": POLICY_VERSION,
        "primary_keyword": normalize_text(primary_keyword),
        "secondary_keywords": sorted(normalize_text(k) for k in secondary_keywords if normalize_text(k)),
        "demand_group_id": demand_group_id or "",
        "proposed_url": (proposed_url or "").strip().lower(),
        "page_type": (page_type or "UNKNOWN").upper(),
        "market": (market or "VN").upper(),
        "metrics_evidence_hash": metrics_evidence_hash or "",
        "serp_evidence_hash": serp_evidence_hash or "",
        "priority": (priority or "").upper(),
        "business_value": (business_value or "").upper(),
        "effort": (effort or "").upper(),
    }
    encoded = json.dumps(canonical, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def load_project_policy_context(
    db: Session,
    project: Project,
    *,
    verify_disk: bool = True,
) -> dict[str, Any]:
    """
    Load all project-scoped evidence/approval records ONCE per request and compute
    bounded per-batch F2 integrity (each source file on disk hashed at most once).
    """
    batches_by_id = {
        b.id: b for b in db.query(ResearchBatch).filter(ResearchBatch.project_id == project.id).all()
    }
    uploads_by_id = {
        u.id: u for u in db.query(FileUpload).filter(FileUpload.project_id == project.id).all()
    }
    evidence_rows = db.query(EvidenceRow).filter(EvidenceRow.project_id == project.id).all()

    rows_by_batch: dict[str, list[EvidenceRow]] = {}
    for r in evidence_rows:
        rows_by_batch.setdefault(r.batch_id, []).append(r)

    disk_hash_cache: dict[str, tuple[bool, str, int, str]] = {}
    batch_integrity_by_id: dict[str, dict[str, Any]] = {}
    for bid, batch in batches_by_id.items():
        batch_integrity_by_id[bid] = verify_batch_integrity_detailed(
            batch,
            uploads_by_id,
            rows_by_batch.get(bid, []),
            verify_disk=verify_disk,
            disk_hash_cache=disk_hash_cache,
        )

    return {
        "valid_refs": valid_source_refs_for_project(db, project),
        "source_keywords": db.query(SourceKeyword).filter(SourceKeyword.project_id == project.id).all(),
        "demand_groups_by_id": {
            dg.id: dg for dg in db.query(DemandGroup).filter(DemandGroup.project_id == project.id).all()
        },
        "batches_by_id": batches_by_id,
        "uploads_by_id": uploads_by_id,
        "evidence_rows": evidence_rows,
        "batch_integrity_by_id": batch_integrity_by_id,
        "approvals": db.query(Approval).filter(Approval.project_id == project.id).all(),
        "briefs": db.query(ContentBrief).filter(ContentBrief.project_id == project.id).all(),
    }


def evaluate_mapping_eligibility(
    project: Project,
    mapping: KeywordMapping,
    ctx: dict[str, Any],
) -> dict[str, Any]:
    """
    Phase 1 Authoritative Pre-Generation Eligibility Decision for ONE KeywordMapping.
    Recomputes LIVE effective metrics + coherent SERP snapshot + canonical fingerprint on EVERY call
    so stale evidence ALWAYS blocks OFFICIAL even without manual mapping regeneration!
    """
    blockers: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    evidence_refs: list[str] = []
    gate_statuses: dict[str, str] = {}

    proj_market = (project.market or "VN").upper()
    demand_groups_by_id: dict[str, DemandGroup] = ctx["demand_groups_by_id"]
    batches_by_id: dict[str, ResearchBatch] = ctx["batches_by_id"]
    uploads_by_id: dict[str, FileUpload] = ctx["uploads_by_id"]
    evidence_rows: list[EvidenceRow] = ctx["evidence_rows"]
    batch_integrity_by_id: dict[str, dict[str, Any]] = ctx.get("batch_integrity_by_id") or {}
    approvals: list[Approval] = ctx["approvals"]
    valid_refs: set[str] = ctx["valid_refs"]

    # --- F0: Project core taxonomy & required context ---
    has_topic = bool(project.topic_pillar_code or project.topic_pillar_name or project.main_topic)
    has_pk = bool(project.primary_keyword_original or project.primary_keyword_current)
    has_goal = bool((project.business_goal or "").strip())
    has_audience = bool((project.target_audience or "").strip())
    if not (has_topic and has_pk and has_goal and has_audience):
        missing_f0 = [
            lbl
            for ok, lbl in [
                (has_topic, "Topic Pillar / Chủ đề chính"),
                (has_pk, "Keyword chính gốc"),
                (has_goal, "Mục tiêu kinh doanh"),
                (has_audience, "Đối tượng độc giả"),
            ]
            if not ok
        ]
        gate_statuses["F0"] = "FAILED" if not (has_topic and has_pk) else "WARNING"
        blockers.append(
            _make_blocker(
                "F0_PROJECT_CONTEXT_INCOMPLETE",
                f"Dự án còn thiếu thông tin đầu vào bắt buộc cho Brief chính thức: {', '.join(missing_f0)}.",
                "Không thể đảm bảo định hướng kinh doanh & độc giả chính xác khi xuất Content Brief chính thức.",
                "Bổ sung đầy đủ Topic Pillar, Keyword chính, Mục tiêu kinh doanh và Đối tượng độc giả tại Bước 01.",
                "Hoàn thiện thông tin dự án ở Bước 01 rồi lưu SQLite.",
                "Mở Bước 01",
                "/steps/01-topic",
            )
        )
    else:
        gate_statuses["F0"] = "PASSED"

    # --- F1: Exact-keyword, exact-market LIVE Metrics validation (deterministic latest batch) ---
    m_row, metrics_batch, metric_rows_all = select_effective_metrics_row(
        project, mapping.primary_keyword, evidence_rows, batches_by_id
    )
    metrics_hash = compute_metrics_evidence_hash(m_row, metrics_batch, proj_market)

    f1_blocked = False
    if m_row is None:
        f1_blocked = True
        if metric_rows_all:
            wrong_markets = sorted({(r.market or "?").upper() for r in metric_rows_all})
            blockers.append(
                _make_blocker(
                    "F1_MARKET_MISMATCH",
                    f"Dữ liệu Semrush cho '{mapping.primary_keyword}' thuộc thị trường {wrong_markets}, lệch với thị trường dự án ({proj_market}).",
                    "Không được dùng chỉ số của thị trường khác để lập Content Brief chính thức.",
                    f"Xuất lại báo cáo Semrush đúng thị trường {proj_market} và tải lên Bước 04.",
                    "Tạo yêu cầu Semrush đúng thị trường.",
                    "Mở Bước 04",
                    "/steps/04-upload",
                )
            )
        else:
            blockers.append(
                _make_blocker(
                    "F1_METRICS_MISSING",
                    f"Chưa có dòng bằng chứng Semrush khớp chính xác keyword '{mapping.primary_keyword}' tại thị trường {proj_market}.",
                    "Không có dữ liệu thực tế về Volume/KD cho từ khóa chính này.",
                    "Xuất báo cáo Keyword Overview trên Semrush chứa từ khóa này rồi tải lên Bước 04.",
                    "Bổ sung bằng chứng Semrush cho từ khóa chính.",
                    "Mở Bước 03",
                    "/steps/03-semrush",
                )
            )
    else:
        evidence_refs.append(f"metrics_batch:{m_row.batch_id}")
        evidence_refs.append(f"metrics_row:{m_row.id}")
        if m_row.volume is None:
            f1_blocked = True
            blockers.append(
                _make_blocker(
                    "F1_VOLUME_MISSING",
                    f"Keyword '{mapping.primary_keyword}' thiếu giá trị Volume (null khác 0).",
                    "Không thể đánh giá nhu cầu tìm kiếm thực tế khi thiếu Volume.",
                    "Xuất lại báo cáo Keyword Overview có cột Volume từ Semrush.",
                    "Bổ sung dữ liệu Volume.",
                    "Mở Bước 03",
                    "/steps/03-semrush",
                )
            )
        if m_row.kd is None:
            f1_blocked = True
            blockers.append(
                _make_blocker(
                    "F1_KD_MISSING",
                    f"Keyword '{mapping.primary_keyword}' thiếu chỉ số KD (Keyword Difficulty = null).",
                    "Chưa đủ dữ liệu đánh giá độ khó cạnh tranh để phát hành Content Brief chính thức (vẫn xem được Volume & tạo bản DỰ THẢO).",
                    "Xuất báo cáo Semrush có cột Keyword Difficulty cho từ khóa này và tải lên Bước 04.",
                    "Bổ sung chỉ số KD qua Bước 03–04.",
                    "Mở Bước 03",
                    "/steps/03-semrush",
                )
            )
        if m_row.volume is not None and m_row.volume < 100:
            warnings.append(
                {
                    "code": "LOW_VOLUME_BUT_RELEVANT",
                    "message": f"Keyword '{mapping.primary_keyword}' có Volume={m_row.volume} (<100) nhưng được bảo lưu đánh giá theo giá trị kinh doanh (không loại bằng ngưỡng cứng).",
                }
            )
    gate_statuses["F1"] = "FAILED" if f1_blocked else "PASSED"

    # --- F2: Full tamper-evident import integrity ---
    if m_row is None:
        f2_status = "NOT_STARTED"
        f2_issues: list[str] = ["Chưa có batch metrics hợp lệ."]
    else:
        b_int = batch_integrity_by_id.get(m_row.batch_id) or verify_batch_integrity_detailed(
            metrics_batch, uploads_by_id, evidence_rows
        )
        f2_issues = list(b_int["issues"])
        if b_int["status"] == "VERIFIED":
            f2_status = "PASSED"
        elif b_int["status"] == "UNVERIFIED":
            f2_status = "WARNING"
        else:
            f2_status = "FAILED"
        if not b_int["ok"]:
            blockers.append(
                _make_blocker(
                    "F2_IMPORT_INTEGRITY_FAILED",
                    f"Batch dữ liệu của '{mapping.primary_keyword}' chưa đạt toàn vẹn import ({b_int['status']}): {'; '.join(f2_issues)}",
                    "Không thể đảm bảo tệp nguồn & toàn bộ dòng chuẩn hóa chưa bị thay đổi.",
                    "Kiểm tra lại file nguồn tại Bước 04 và xác nhận import lại.",
                    "Xác minh lại batch import.",
                    "Mở Bước 04",
                    "/steps/04-upload",
                )
            )
    gate_statuses["F2"] = f2_status

    # --- F5: Strict single-snapshot per-keyword, per-market SERP provenance ---
    organic_rows = [r for r in evidence_rows if r.row_type == "ORGANIC_RESULTS"]
    serp_eval = evaluate_serp_for_keyword(
        project,
        mapping.primary_keyword,
        organic_rows,
        batches_by_id,
        uploads_by_id,
        batch_integrity_by_id=batch_integrity_by_id,
    )
    for bid in serp_eval["batch_ids"]:
        evidence_refs.append(f"serp_batch:{bid}")
    for fh in serp_eval["file_hashes"]:
        evidence_refs.append(f"serp_sha256:{fh[:12]}")

    if serp_eval["serp_tier"] == "SERP_NOT_VERIFIED":
        gate_statuses["F5"] = "FAILED"
        blockers.append(
            _make_blocker(
                "F5_SERP_NOT_VERIFIED",
                serp_eval["sufficiency_reason"],
                "Kế hoạch và Content Brief chỉ được ở trạng thái DỰ THẢO (SERP_NOT_VERIFIED); không được đóng dấu đã kiểm chứng SERP.",
                "Xuất báo cáo ORGANIC_RESULTS / SERP Analysis từ Semrush cho đúng từ khóa này (gắn đúng phiếu hoặc nhập từ khóa mục tiêu ở Bước 04).",
                "Tải file ORGANIC_RESULTS cho đúng từ khóa ở Bước 04.",
                "Mở Bước 04",
                "/steps/04-upload",
            )
        )
    elif serp_eval["serp_tier"] == "PARTIAL_SERP_EVIDENCE":
        gate_statuses["F5"] = "WARNING"
        blockers.append(
            _make_blocker(
                "F5_PARTIAL_SERP_EVIDENCE",
                serp_eval["sufficiency_reason"],
                "1–2 URL hoặc snapshot chưa đủ điều kiện không được phép phát hành Content Brief chính thức và không thể tuyên bố Top 10.",
                f"Bổ sung báo cáo ORGANIC_RESULTS có ít nhất {MIN_ORGANIC_URLS_FOR_SERP_VERIFIED} URL organic xếp hạng hợp lệ trong CÙNG 1 snapshot cho '{mapping.primary_keyword}'.",
                "Tải bổ sung dữ liệu SERP tại Bước 04.",
                "Mở Bước 04",
                "/steps/04-upload",
            )
        )
    else:
        gate_statuses["F5"] = "PASSED"
        if not serp_eval["top10_verified"]:
            warnings.append(
                {
                    "code": "PARTIAL_TOP_10_COVERAGE",
                    "message": serp_eval["sufficiency_reason"],
                }
            )
        if m_row is not None and not m_row.intent:
            warnings.append(
                {
                    "code": "INTENT_INFERRED_FROM_SERP",
                    "message": "File Semrush metrics không có cột Intent; Search Intent được đối chiếu từ URL Organic SERP.",
                }
            )

    if m_row is not None and not m_row.intent and not serp_eval["serp_sufficient"]:
        warnings.append(
            {
                "code": "F1_INTENT_MISSING",
                "message": f"Keyword '{mapping.primary_keyword}' thiếu cả cột Intent trên Semrush lẫn bằng chứng SERP.",
            }
        )

    # Compute LIVE effective fingerprint against current SQLite evidence (catches drift EVEN without mapping/preview!)
    secondary_kws = json.loads(mapping.secondary_keywords_json or "[]")
    live_fingerprint = compute_mapping_fingerprint(
        primary_keyword=mapping.primary_keyword,
        secondary_keywords=secondary_kws,
        demand_group_id=mapping.demand_group_id,
        proposed_url=mapping.proposed_url,
        page_type=mapping.page_type,
        market=proj_market,
        metrics_evidence_hash=metrics_hash,
        serp_evidence_hash=serp_eval["serp_evidence_hash"],
        priority=mapping.priority,
        business_value=mapping.business_value,
        effort=mapping.effort,
    )
    evidence_drifted = bool(mapping.content_fingerprint and live_fingerprint != mapping.content_fingerprint)

    # --- E0 / E1 / E2: Demand Group lineage & overlap review ---
    dg = demand_groups_by_id.get(mapping.demand_group_id) if mapping.demand_group_id else None
    if dg is not None:
        refs = json.loads(dg.source_refs_json or "[]")
        refs_valid = bool(refs) and all(r in valid_refs for r in refs) and dg.status != "UNCERTAIN"
        if not refs_valid:
            gate_statuses["E0"] = "FAILED"
            blockers.append(
                _make_blocker(
                    "E0_INVALID_SOURCE_REF",
                    f"Nhóm nhu cầu '{dg.name}' có mã nguồn source_refs không khớp với taxonomy SQLite ({refs}).",
                    "Đề xuất AI thiếu nguồn kiểm chứng không được phép xuất Content Brief chính thức.",
                    "Xác minh lại taxonomy ở Bước 01 hoặc chạy lại phân tích / phê duyệt nguồn ở Bước 02.",
                    "Kiểm tra nguồn taxonomy của nhóm nhu cầu.",
                    "Mở Bước 02",
                    "/steps/02-demand-map",
                )
            )
        else:
            gate_statuses["E0"] = "PASSED"
            evidence_refs.extend([f"source_ref:{r}" for r in refs])

        if not (dg.strongest_counterargument or "").strip():
            gate_statuses["E1"] = "WARNING"
            warnings.append({"code": "E1_MISSING_COUNTERARGUMENT", "message": f"Nhóm '{dg.name}' thiếu phản biện mạnh nhất."})
        else:
            gate_statuses["E1"] = "PASSED"

        if dg.coverage_type == "OVERLAP":
            overlap_approved = any(
                a.target_ref == mapping.id
                and a.approval_type == "OVERLAP_MERGE_SPLIT"
                and a.status == "APPROVED"
                and a.target_fingerprint == live_fingerprint
                for a in approvals
            )
            gate_statuses["E2"] = "PASSED" if overlap_approved else "HOLD"
            if not overlap_approved:
                blockers.append(
                    _make_blocker(
                        "E2_OVERLAP_REVIEW_REQUIRED",
                        f"Nhóm '{dg.name}' có dấu hiệu giao thoa/trùng nhu cầu (OVERLAP) và chưa được phê duyệt quyết định gộp/tách cho bằng chứng hiện hành.",
                        "Nguy cơ cannibalization giữa các bài viết trong cùng Topic Pillar.",
                        "Rà soát đề xuất gộp/tách bằng bằng chứng SERP và phê duyệt tại màn hình Chờ phê duyệt.",
                        "Mở Chờ phê duyệt để quyết định gộp/tách.",
                        "Mở Chờ phê duyệt",
                        "/approvals",
                    )
                )
        else:
            gate_statuses["E2"] = "PASSED"
    else:
        gate_statuses["E0"] = "PASSED"
        gate_statuses["E1"] = "PASSED"
        gate_statuses["E2"] = "PASSED"

    # --- F3: Topical relevance & business rationale (NEVER discard low-volume B2B) ---
    has_biz_rationale = bool((project.business_goal or "").strip() or (dg and (dg.business_relevance_note or "").strip()))
    gate_statuses["F3"] = "PASSED" if (has_topic and has_biz_rationale) else "WARNING"
    if not has_biz_rationale:
        warnings.append(
            {
                "code": "F3_BUSINESS_RATIONALE_MISSING",
                "message": "Thiếu liên kết mục tiêu kinh doanh để đánh giá giá trị B2B.",
            }
        )

    # --- F4: Auditable priority/effort rationale (NO fixed KD cutoff) ---
    ev_list = json.loads(mapping.evidence_json or "[]")
    has_f4_rationale = bool(
        mapping.priority in {"P1", "P2", "P3"}
        and mapping.business_value
        and mapping.effort
        and (mapping.merge_split_proposal or "").strip()
        and len(ev_list) > 0
    )
    gate_statuses["F4"] = "PASSED" if has_f4_rationale else "WARNING"
    if not has_f4_rationale:
        blockers.append(
            _make_blocker(
                "F4_RATIONALE_INCOMPLETE",
                f"Mapping '{mapping.primary_keyword}' thiếu lập luận ưu tiên/công sức hoặc thiếu danh sách bằng chứng đính kèm.",
                "Quyết định ưu tiên không thể kiểm toán được.",
                "Chạy lại Bước 06 Lập Keyword Mapping để cập nhật đầy đủ lập luận bằng chứng.",
                "Cập nhật Keyword Mapping ở Bước 06.",
                "Mở Bước 06",
                "/steps/06-mapping",
            )
        )

    # --- F6: Exact Revision & LIVE Evidence Fingerprint Human Approval ---
    pending_pk_change = any(
        a.approval_type == "PRIMARY_KEYWORD_CHANGE" and a.status == "PENDING"
        for a in approvals
    )
    target_approvals = [
        a for a in approvals
        if a.target_ref == mapping.id and a.scope == "BRIEF_ELIGIBILITY"
    ]
    exact_approved = any(
        a.status == "APPROVED"
        and a.target_revision == mapping.revision
        and a.target_fingerprint == live_fingerprint
        for a in target_approvals
    )
    mapping_fingerprint_matches = (
        not evidence_drifted
        and bool(mapping.is_approved)
        and bool(mapping.content_fingerprint)
        and mapping.approved_revision == mapping.revision
        and mapping.approved_fingerprint == live_fingerprint
        and exact_approved
    )
    has_rejected = (not evidence_drifted) and any(
        a.status in {"REJECTED", "NEED_MORE_EVIDENCE"}
        and a.target_revision == mapping.revision
        and a.target_fingerprint == live_fingerprint
        for a in target_approvals
    )
    had_older_approval = (
        bool(mapping.approved_fingerprint and mapping.approved_fingerprint != live_fingerprint)
        or any(a.status == "APPROVED" and a.target_fingerprint != live_fingerprint for a in target_approvals)
    )

    if pending_pk_change:
        approval_state = "PENDING_PRIMARY_CHANGE"
        gate_statuses["F6"] = "HOLD"
        blockers.append(
            _make_blocker(
                "F6_PENDING_PRIMARY_KEYWORD_CHANGE",
                "Dự án đang có yêu cầu đổi Keyword chính gốc chưa được phê duyệt.",
                "Không thể xuất Brief chính thức khi keyword chính chưa được chốt.",
                "Mở Chờ phê duyệt để duyệt hoặc từ chối thay đổi keyword chính.",
                "Quyết định thay đổi keyword chính tại /approvals.",
                "Mở Chờ phê duyệt",
                "/approvals",
            )
        )
    elif has_rejected:
        approval_state = "REJECTED_OR_HOLD"
        gate_statuses["F6"] = "FAILED"
        blockers.append(
            _make_blocker(
                "F6_APPROVAL_REJECTED",
                f"Mapping '{mapping.primary_keyword}' (rev #{mapping.revision}) đã bị từ chối hoặc yêu cầu bổ sung bằng chứng.",
                "Không được phép xuất Content Brief chính thức khi quyết định phê duyệt chưa đạt.",
                "Bổ sung dữ liệu/điều chỉnh mapping rồi cập nhật lại Bước 06 để xin phê duyệt mới.",
                "Cập nhật dữ liệu và lập lại Mapping.",
                "Mở Chờ phê duyệt",
                "/approvals",
            )
        )
    elif not mapping_fingerprint_matches:
        is_stale_evidence = evidence_drifted or had_older_approval
        approval_state = "STALE_SUPERSEDED" if is_stale_evidence else "PENDING_APPROVAL"
        gate_statuses["F6"] = "HOLD"
        if is_stale_evidence:
            reason_msg = (
                f"Bằng chứng hoặc Mapping '{mapping.primary_keyword}' đã thay đổi so với phê duyệt cũ "
                f"(rev #{mapping.revision}, batch hiện hành: {serp_eval.get('selected_batch_id') or (m_row.batch_id if m_row else 'N/A')}) "
                "— phê duyệt cũ đã hết hiệu lực và cần duyệt lại."
            )
            blocker_code = "EVIDENCE_UPDATED_REAPPROVAL_REQUIRED"
        else:
            reason_msg = f"Mapping '{mapping.primary_keyword}' (rev #{mapping.revision}) chưa được chuyên viên SEO phê duyệt."
            blocker_code = "F6_APPROVAL_REQUIRED"
        blockers.append(
            _make_blocker(
                blocker_code,
                reason_msg,
                "Gate F6 ở trạng thái HOLD; không thể xuất Content Brief CHÍNH THỨC trước khi người dùng duyệt đúng phiên bản & bằng chứng hiện hành.",
                "Mở màn hình Chờ phê duyệt để kiểm tra bằng chứng mới nhất và phê duyệt lại.",
                "Phê duyệt lại Mapping tại /approvals.",
                "Mở Chờ phê duyệt",
                "/approvals",
            )
        )
    else:
        approval_state = "APPROVED_CURRENT"
        gate_statuses["F6"] = "PASSED"

    eligible_official = len(blockers) == 0

    if eligible_official:
        recommended_status = "READY_FOR_BRIEF"
    elif m_row is None or m_row.volume is None:
        recommended_status = "RESEARCH_REQUIRED"
    elif serp_eval["serp_tier"] == "SERP_NOT_VERIFIED":
        recommended_status = "SERP_NOT_VERIFIED"
    elif serp_eval["serp_tier"] == "PARTIAL_SERP_EVIDENCE":
        recommended_status = "PARTIAL_SERP_EVIDENCE"
    elif approval_state in {"PENDING_APPROVAL", "STALE_SUPERSEDED", "PENDING_PRIMARY_CHANGE"}:
        recommended_status = "PENDING_APPROVAL"
    elif m_row.volume < 100 and has_biz_rationale:
        recommended_status = "LOW_VOLUME_BUT_RELEVANT"
    else:
        recommended_status = "RESEARCH_REQUIRED"

    return {
        "mapping_id": mapping.id,
        "primary_keyword": mapping.primary_keyword,
        "policy_version": POLICY_VERSION,
        "current_revision": mapping.revision,
        "content_fingerprint": mapping.content_fingerprint,
        "live_fingerprint": live_fingerprint,
        "evidence_drifted": evidence_drifted,
        "metrics_evidence_hash": metrics_hash,
        "serp_evidence_hash": serp_eval["serp_evidence_hash"],
        "eligible_official": eligible_official,
        "recommended_content_status": recommended_status,
        "serp_tier": serp_eval["serp_tier"],
        "serp_status": serp_eval["serp_status"],
        "top10_verified": serp_eval["top10_verified"],
        "serp_evidence": serp_eval,
        "approval_state": approval_state,
        "blockers": blockers,
        "warnings": warnings,
        "evidence_refs": sorted(set(evidence_refs)),
        "gate_statuses": gate_statuses,
    }


def compute_effective_brief_freshness(
    brief: ContentBrief,
    mapping: KeywordMapping | None,
    mapping_decision: dict[str, Any] | None,
) -> dict[str, Any]:
    """Dynamically determine a brief's live staleness and truthful effective mode."""
    stale_reasons: list[str] = []
    if brief.is_stale:
        stale_reasons.append("Brief đã được đánh dấu cũ do Mapping hoặc bằng chứng thay đổi.")
    if mapping is not None and mapping_decision is not None:
        live_fp = mapping_decision.get("live_fingerprint") or mapping.content_fingerprint
        if brief.mapping_fingerprint and live_fp and brief.mapping_fingerprint != live_fp:
            stale_reasons.append("Dấu vân tay bằng chứng/Mapping hiện hành đã khác bản dùng khi tạo Brief.")
        if brief.mapping_revision is not None and brief.mapping_revision != mapping.revision:
            stale_reasons.append(f"Mapping đã lên rev #{mapping.revision} (Brief tạo từ rev #{brief.mapping_revision}).")
        if brief.brief_mode == "OFFICIAL" and not mapping_decision.get("eligible_official"):
            stale_reasons.append("Mapping không còn đạt đủ điều kiện Quality Gates cho Brief CHÍNH THỨC.")
    elif brief.brief_mode == "OFFICIAL":
        stale_reasons.append("Không tìm thấy Mapping đang hoạt động tương ứng với Brief CHÍNH THỨC này.")

    effective_is_stale = len(stale_reasons) > 0
    if brief.brief_mode == "OFFICIAL" and not effective_is_stale and mapping_decision and mapping_decision.get("eligible_official"):
        effective_mode = "OFFICIAL"
        effective_status = brief.status
    else:
        effective_mode = "DRAFT"
        effective_status = "STALE_NEEDS_REGENERATION" if effective_is_stale else brief.status

    return {
        "effective_is_stale": effective_is_stale,
        "effective_brief_mode": effective_mode,
        "effective_status": effective_status,
        "stale_reasons": stale_reasons,
    }


def evaluate_brief_quality(
    brief: ContentBrief,
    mapping: KeywordMapping | None,
    mapping_decision: dict[str, Any] | None,
) -> dict[str, Any]:
    """
    Phase 2: Post-Generation Brief Quality (F7).
    Strictly separate from Phase 1 pre-generation eligibility to prevent circular logic,
    while respecting LIVE evidence staleness!
    """
    issues: list[str] = []
    if not (brief.br_code and brief.primary_keyword and brief.seo_title and brief.h1 and brief.meta_description and brief.cta):
        issues.append(f"{brief.br_code}: Thiếu trường SEO cơ bản (Title/H1/Meta/CTA).")
    outline = json.loads(brief.outline_json or "[]")
    checklist = json.loads(brief.seo_checklist_json or "[]")
    if not outline or not checklist:
        issues.append(f"{brief.br_code}: Thiếu Outline H2/H3 hoặc SEO Checklist.")

    ws = json.loads(brief.writing_strategy_json or "{}")
    primary_f = ws.get("primary_formula")
    supporting_f = ws.get("supporting_formulas") or []
    openings = ws.get("opening_ideas") or []
    tactics = ws.get("engagement_tactics") or []
    if ws.get("scope") != "WHOLE_ARTICLE" or ws.get("per_heading_enforcement") is not False:
        issues.append(f"{brief.br_code}: Writing Strategy phải áp dụng ở cấp toàn bài, không ép từng H2/H3.")
    if primary_f not in VALID_FORMULA_IDS:
        issues.append(f"{brief.br_code}: Công thức viết chính '{primary_f}' không thuộc danh mục 13 công thức chuẩn.")
    if len(supporting_f) > 2 or any(f not in VALID_FORMULA_IDS for f in supporting_f):
        issues.append(f"{brief.br_code}: Công thức bổ trợ vượt quá 2 hoặc ngoài danh mục chuẩn.")
    if not (1 <= len(openings) <= 2):
        issues.append(f"{brief.br_code}: Cần 1–2 ý tưởng mở bài.")
    if not (3 <= len(tactics) <= 6) or any(t.get("code") not in VALID_TACTIC_CODES for t in tactics):
        issues.append(f"{brief.br_code}: Cần 3–6 chiến thuật thuộc thư viện 16 chiến thuật chuẩn.")

    from app.domain.brief_writer import business_quality
    if ws.get("generation_source"):
        payload = {"title_variants":ws.get("title_variants",[brief.seo_title]), "meta_description":brief.meta_description, "outline":outline, "faq":ws.get("faq",[]), "internal_links":json.loads(brief.internal_links_json or "[]"), "legal_sources":ws.get("legal_sources",[]), "content_type":brief.content_type}
        issues.extend(business_quality(payload, primary_keyword=brief.primary_keyword, secondary_keywords=json.loads(brief.secondary_keywords_json or "[]"), allowed_urls={link["target_url"] for link in payload["internal_links"]}))
        issues.extend(ws.get("quality_errors", []))
    fresh = compute_effective_brief_freshness(brief, mapping, mapping_decision)
    if fresh["effective_is_stale"]:
        issues.append(f"{brief.br_code}: Brief đã cũ (stale) — {' '.join(fresh['stale_reasons'])}")

    return {
        "brief_id": brief.id,
        "br_code": brief.br_code,
        "brief_mode": fresh["effective_brief_mode"],
        "is_stale": fresh["effective_is_stale"],
        "passed": len(issues) == 0,
        "issues": issues,
    }
