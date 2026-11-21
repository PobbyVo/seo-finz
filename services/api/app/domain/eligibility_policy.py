from __future__ import annotations

import hashlib
import json
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

POLICY_VERSION = "1.6.1"
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


def evaluate_serp_for_keyword(
    project: Project,
    keyword: str,
    organic_rows: list[EvidenceRow],
    batches_by_id: dict[str, ResearchBatch],
    uploads_by_id: dict[str, FileUpload],
) -> dict[str, Any]:
    """
    Authoritative per-project, per-keyword, per-market SERP provenance evaluator.
    - NEVER uses project-global rows or another keyword's SERP rows as fallback.
    - Rejects non-organic (AI Overview/Ads), invalid URLs, malformed positions (<1), and mismatched market.
    - Distinguishes:
      * SERP_NOT_VERIFIED (0 valid unique ranked organic URLs)
      * PARTIAL_SERP_EVIDENCE (1..2 valid unique ranked organic URLs — insufficient for OFFICIAL!)
      * SERP_VERIFIED (>=3 valid unique ranked organic URLs — sufficient for decision, disclaimer if Top 10 incomplete)
      * TOP_10_VERIFIED (all positions 1..10 covered by valid unique ranked organic URLs in matching keyword & market)
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

    valid_by_url: dict[str, EvidenceRow] = {}
    ai_overview_count = 0
    non_organic_count = 0
    rejected_market_count = 0
    rejected_invalid_count = 0
    duplicate_url_count = 0
    batch_ids: set[str] = set()
    file_hashes: set[str] = set()
    page_type_counts: dict[str, int] = {}
    rank_counts: dict[int, int] = {}

    for r in matching_kw_rows:
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
            # Keep highest (lowest number) rank
            if r.organic_position is not None and (
                existing.organic_position is None or r.organic_position < existing.organic_position
            ):
                valid_by_url[url_key] = r
        else:
            valid_by_url[url_key] = r

    unique_rows = sorted(
        valid_by_url.values(),
        key=lambda x: (x.organic_position if x.organic_position is not None else 9999, x.source_row_number),
    )

    positions_covered: list[int] = []
    for r in unique_rows:
        batch_ids.add(r.batch_id)
        b = batches_by_id.get(r.batch_id)
        if b and b.file_upload_id and b.file_upload_id in uploads_by_id:
            file_hashes.add(uploads_by_id[b.file_upload_id].sha256)
        pt = (r.organic_page_type or "UNKNOWN").upper()
        page_type_counts[pt] = page_type_counts.get(pt, 0) + 1
        if r.organic_position is not None:
            positions_covered.append(r.organic_position)
            rank_counts[r.organic_position] = rank_counts.get(r.organic_position, 0) + 1

    top10_covered = sorted(p for p in set(positions_covered) if 1 <= p <= 10)
    top10_missing = sorted(TOP_10_RANKS - set(top10_covered))
    duplicate_ranks = sorted(pos for pos, cnt in rank_counts.items() if cnt > 1)
    unique_count = len(unique_rows)

    if unique_count == 0:
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
            f"Mới có {unique_count} URL organic cho '{keyword}' (cần tối thiểu {MIN_ORGANIC_URLS_FOR_SERP_VERIFIED} URL xếp hạng hợp lệ "
            "để xác minh dạng trang; tuyệt đối chưa đủ để tuyên bố kiểm chứng Top 10)."
        )
    elif not top10_missing:
        serp_tier = "TOP_10_VERIFIED"
        serp_status = "SERP_VERIFIED"
        top10_verified = True
        sufficiency_reason = (
            f"Đã kiểm chứng đầy đủ Top 10 (vị trí 1–10, tổng {unique_count} URL organic duy nhất) "
            f"cho '{keyword}' tại thị trường {proj_market}."
        )
    else:
        serp_tier = "SERP_VERIFIED"
        serp_status = "SERP_VERIFIED"
        top10_verified = False
        sufficiency_reason = (
            f"Đã có {unique_count} URL organic xếp hạng hợp lệ cho '{keyword}' (đủ kiểm chứng dạng trang cơ bản, "
            f"chưa đầy đủ Top 10 — thiếu vị trí {top10_missing})."
        )

    dominant_page_type = (
        max(page_type_counts, key=lambda k: page_type_counts[k])
        if page_type_counts
        else None
    )

    warnings: list[str] = []
    if rejected_market_count > 0:
        warnings.append(f"Bỏ qua {rejected_market_count} dòng SERP lệch thị trường (khác {proj_market}).")
    if ai_overview_count > 0:
        warnings.append(f"Đã tách riêng {ai_overview_count} dòng AI Overview khỏi bảng xếp hạng Organic.")
    if non_organic_count > 0:
        warnings.append(f"Đã tách riêng {non_organic_count} dòng phi-Organic khỏi bằng chứng xếp hạng.")
    if rejected_invalid_count > 0:
        warnings.append(f"Loại {rejected_invalid_count} dòng có URL/Position không hợp lệ (vẫn giữ bản thô).")
    if duplicate_ranks:
        warnings.append(f"Phát hiện vị trí xếp hạng trùng lặp: {duplicate_ranks[:6]}.")
    if serp_tier == "SERP_VERIFIED" and top10_missing:
        warnings.append(f"Chưa đủ bằng chứng Top 10 hoàn chỉnh (thiếu vị trí {top10_missing}); không được đóng dấu Top 10 Verified.")

    # Deterministic fingerprint of the valid SERP evidence supporting this keyword
    evidence_sig_payload = [
        {"batch": r.batch_id, "pos": r.organic_position, "url": r.organic_url, "pt": r.organic_page_type}
        for r in unique_rows[:20]
    ]
    serp_evidence_hash = hashlib.sha256(
        json.dumps(evidence_sig_payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:16] if unique_rows else ""

    return {
        "keyword": keyword,
        "keyword_normalized": kw_norm,
        "market": proj_market,
        "serp_file_present": len(matching_kw_rows) > 0,
        "serp_tier": serp_tier,
        "serp_status": serp_status,
        "serp_sufficient": serp_tier in ("SERP_VERIFIED", "TOP_10_VERIFIED"),
        "top10_verified": top10_verified,
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
        "batch_ids": sorted(batch_ids),
        "file_hashes": sorted(file_hashes),
        "page_type_distribution": page_type_counts,
        "dominant_page_type_hypothesis": dominant_page_type,
        "sample_urls": [r.organic_url for r in unique_rows[:5] if r.organic_url],
        "serp_evidence_hash": serp_evidence_hash,
        "sufficiency_reason": sufficiency_reason,
        "warnings": warnings,
    }


def compute_mapping_fingerprint(
    *,
    primary_keyword: str,
    secondary_keywords: list[str],
    demand_group_id: str | None,
    proposed_url: str,
    page_type: str,
    market: str,
    metrics_evidence_id: str | None,
    metrics_batch_id: str | None,
    serp_evidence_hash: str,
    priority: str,
    business_value: str,
    effort: str,
    merge_split_proposal: str,
) -> str:
    """Canonical SHA-256 fingerprint covering every high-impact mapping & evidence field."""
    canonical = {
        "policy_version": POLICY_VERSION,
        "primary_keyword": normalize_text(primary_keyword),
        "secondary_keywords": sorted(normalize_text(k) for k in secondary_keywords if normalize_text(k)),
        "demand_group_id": demand_group_id or "",
        "proposed_url": (proposed_url or "").strip().lower(),
        "page_type": (page_type or "UNKNOWN").upper(),
        "market": (market or "VN").upper(),
        "metrics_evidence_id": metrics_evidence_id or "",
        "metrics_batch_id": metrics_batch_id or "",
        "serp_evidence_hash": serp_evidence_hash or "",
        "priority": (priority or "").upper(),
        "business_value": (business_value or "").upper(),
        "effort": (effort or "").upper(),
        "merge_split_proposal": (merge_split_proposal or "").strip(),
    }
    encoded = json.dumps(canonical, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def verify_batch_integrity(
    batch: ResearchBatch | None,
    uploads_by_id: dict[str, FileUpload],
    evidence_rows: list[EvidenceRow],
) -> tuple[bool, list[str]]:
    """Verify F2 import integrity for a specific batch (NOT mere table non-emptiness!)."""
    if batch is None:
        return False, ["Chưa có ResearchBatch gắn với bằng chứng này."]
    issues: list[str] = []
    if batch.status != "PROCESS_COMPLETED":
        issues.append(f"Batch {batch.id} chưa hoàn tất kỹ thuật (status={batch.status}).")
    if batch.total_raw_rows <= 0 or batch.total_normalized_rows < 0:
        issues.append(f"Batch {batch.id} có số dòng không hợp lệ ({batch.total_raw_rows}/{batch.total_normalized_rows}).")
    if batch.total_normalized_rows > batch.total_raw_rows:
        issues.append(f"Batch {batch.id} có số dòng chuẩn hóa vượt dòng thô.")
    if batch.file_upload_id:
        upl = uploads_by_id.get(batch.file_upload_id)
        if not upl:
            issues.append(f"Thiếu bản ghi FileUpload {batch.file_upload_id} cho batch {batch.id}.")
        else:
            if upl.status != "CONFIRMED":
                issues.append(f"FileUpload {upl.id} chưa được xác nhận import (status={upl.status}).")
            if not (upl.sha256 or "").strip():
                issues.append(f"FileUpload {upl.id} thiếu mã băm SHA-256.")
    batch_rows = [r for r in evidence_rows if r.batch_id == batch.id]
    if not batch_rows:
        issues.append(f"Batch {batch.id} không có dòng EvidenceRow nào trong SQLite.")
    elif any(not (r.raw_row_json or "").strip() for r in batch_rows[:5]):
        issues.append(f"Batch {batch.id} thiếu raw_row_json bảo toàn dữ liệu nguồn.")
    return len(issues) == 0, issues


def load_project_policy_context(db: Session, project: Project) -> dict[str, Any]:
    """Load all project-scoped evidence/approval records once for deterministic evaluation."""
    return {
        "valid_refs": valid_source_refs_for_project(db, project),
        "source_keywords": db.query(SourceKeyword).filter(SourceKeyword.project_id == project.id).all(),
        "demand_groups_by_id": {
            dg.id: dg for dg in db.query(DemandGroup).filter(DemandGroup.project_id == project.id).all()
        },
        "batches_by_id": {
            b.id: b for b in db.query(ResearchBatch).filter(ResearchBatch.project_id == project.id).all()
        },
        "uploads_by_id": {
            u.id: u for u in db.query(FileUpload).filter(FileUpload.project_id == project.id).all()
        },
        "evidence_rows": db.query(EvidenceRow).filter(EvidenceRow.project_id == project.id).all(),
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
    Used identically by Quality Gates, Mapping UI, Brief Generation, and Exports.
    """
    blockers: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    evidence_refs: list[str] = []
    gate_statuses: dict[str, str] = {}

    proj_market = (project.market or "VN").upper()
    pk_norm = normalize_text(mapping.primary_keyword)
    demand_groups_by_id: dict[str, DemandGroup] = ctx["demand_groups_by_id"]
    batches_by_id: dict[str, ResearchBatch] = ctx["batches_by_id"]
    uploads_by_id: dict[str, FileUpload] = ctx["uploads_by_id"]
    evidence_rows: list[EvidenceRow] = ctx["evidence_rows"]
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
                and a.target_fingerprint == mapping.content_fingerprint
                for a in approvals
            )
            gate_statuses["E2"] = "PASSED" if overlap_approved else "HOLD"
            if not overlap_approved:
                blockers.append(
                    _make_blocker(
                        "E2_OVERLAP_REVIEW_REQUIRED",
                        f"Nhóm '{dg.name}' có dấu hiệu giao thoa/trùng nhu cầu (OVERLAP) và chưa được phê duyệt quyết định gộp/tách.",
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

    # --- F1: Exact-keyword, exact-market Metrics validation ---
    metric_rows_all = [
        r for r in evidence_rows
        if r.row_type == "METRICS" and not r.is_duplicate and r.keyword_normalized == pk_norm
    ]
    metric_rows_market = [
        r for r in metric_rows_all
        if (r.market or proj_market).upper() == proj_market
    ]
    # Prefer the specific metrics_evidence_id linked to the mapping if still matching keyword & market
    m_row: EvidenceRow | None = None
    if mapping.metrics_evidence_id:
        m_row = next((r for r in metric_rows_market if r.id == mapping.metrics_evidence_id), None)
    if m_row is None and metric_rows_market:
        m_row = metric_rows_market[-1]

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

    # --- F2: Import provenance & normalization integrity ---
    metrics_batch = batches_by_id.get(m_row.batch_id) if m_row else None
    f2_ok, f2_issues = verify_batch_integrity(metrics_batch, uploads_by_id, evidence_rows) if m_row else (False, ["Chưa có batch metrics hợp lệ."])
    gate_statuses["F2"] = "PASSED" if f2_ok else ("NOT_STARTED" if m_row is None else "FAILED")
    if m_row is not None and not f2_ok:
        blockers.append(
            _make_blocker(
                "F2_IMPORT_INTEGRITY_FAILED",
                f"Batch dữ liệu của '{mapping.primary_keyword}' chưa đạt toàn vẹn import: {'; '.join(f2_issues)}",
                "Không thể đảm bảo dữ liệu thô & chuẩn hóa nhất quán.",
                "Kiểm tra lại file upload tại Bước 04 và xác nhận import lại.",
                "Xác minh lại batch import.",
                "Mở Bước 04",
                "/steps/04-upload",
            )
        )

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

    # --- F5: Strict per-keyword, per-market SERP provenance ---
    organic_rows = [r for r in evidence_rows if r.row_type == "ORGANIC_RESULTS"]
    serp_eval = evaluate_serp_for_keyword(project, mapping.primary_keyword, organic_rows, batches_by_id, uploads_by_id)
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
                "1–2 URL chưa đủ bằng chứng dạng trang/ý định để phát hành Content Brief chính thức và không thể tuyên bố kiểm chứng Top 10.",
                f"Bổ sung báo cáo ORGANIC_RESULTS có ít nhất {MIN_ORGANIC_URLS_FOR_SERP_VERIFIED} URL organic xếp hạng hợp lệ cho '{mapping.primary_keyword}'.",
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
        # Check intent: if metrics CSV omitted Intent column (real Semrush exports), note SERP-backed intent
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

    # --- F6: Exact Revision & Fingerprint Human Approval ---
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
        and a.target_fingerprint == mapping.content_fingerprint
        for a in target_approvals
    )
    mapping_fingerprint_matches = (
        bool(mapping.is_approved)
        and bool(mapping.content_fingerprint)
        and mapping.approved_revision == mapping.revision
        and mapping.approved_fingerprint == mapping.content_fingerprint
        and exact_approved
    )
    has_rejected = any(
        a.status in {"REJECTED", "NEED_MORE_EVIDENCE"}
        and a.target_revision == mapping.revision
        and a.target_fingerprint == mapping.content_fingerprint
        for a in target_approvals
    )
    had_older_approval = bool(mapping.approved_fingerprint and mapping.approved_fingerprint != mapping.content_fingerprint) or any(
        a.status == "APPROVED" and a.target_fingerprint != mapping.content_fingerprint
        for a in target_approvals
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
        approval_state = "STALE_SUPERSEDED" if had_older_approval else "PENDING_APPROVAL"
        gate_statuses["F6"] = "HOLD"
        reason_msg = (
            f"Mapping '{mapping.primary_keyword}' đã thay đổi dữ liệu/bằng chứng sang rev #{mapping.revision} "
            "— phê duyệt cũ đã hết hiệu lực và cần duyệt lại."
            if had_older_approval
            else f"Mapping '{mapping.primary_keyword}' (rev #{mapping.revision}) chưa được chuyên viên SEO phê duyệt."
        )
        blockers.append(
            _make_blocker(
                "F6_APPROVAL_STALE" if had_older_approval else "F6_APPROVAL_REQUIRED",
                reason_msg,
                "Gate F6 ở trạng thái HOLD; không thể xuất Content Brief CHÍNH THỨC trước khi người dùng duyệt đúng phiên bản hiện hành.",
                "Mở màn hình Chờ phê duyệt để kiểm tra bằng chứng và duyệt phiên bản mới nhất.",
                "Phê duyệt Mapping tại /approvals.",
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


def evaluate_brief_quality(
    brief: ContentBrief,
    mapping: KeywordMapping | None,
    mapping_decision: dict[str, Any] | None,
) -> dict[str, Any]:
    """
    Phase 2: Post-Generation Brief Quality (F7).
    Strictly separate from Phase 1 pre-generation eligibility to prevent circular logic!
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

    if brief.is_stale or (mapping is not None and brief.mapping_fingerprint and brief.mapping_fingerprint != mapping.content_fingerprint):
        issues.append(f"{brief.br_code}: Brief đã cũ (stale) do Mapping hoặc bằng chứng thay đổi — cần duyệt và tạo lại.")

    if brief.brief_mode == "OFFICIAL":
        if mapping_decision is None or not mapping_decision.get("eligible_official"):
            issues.append(f"{brief.br_code}: Đang gắn nhãn OFFICIAL nhưng Mapping không còn đủ điều kiện Quality Gates.")

    return {
        "brief_id": brief.id,
        "br_code": brief.br_code,
        "brief_mode": brief.brief_mode,
        "is_stale": bool(brief.is_stale),
        "passed": len(issues) == 0,
        "issues": issues,
    }
