from __future__ import annotations
import json
from app.knowledge import ROOT
from app.domain.taxonomy_parser import normalize_text
from app.models import ProjectEvent

REASON_CODES = set(
    "F0-THIEU-COT F0-KEY-CHINH F0-PILLAR F0-GIAI-DOAN F2-GOP F2-HAI-MA F3-THUONG-HIEU F3-CHUYEN-PILLAR F3-KHOP-THAP F1-PHU-KHONG-SO F1-CHINH-KHONG-SO F1-SO-CU F1-PHU-MOI F5-BACKLOG-CONG-CU F5-BACKLOG-TEP F5-BACKLOG-DU-LIEU F5-CHO-BO-SUNG F5-CHUA-XAC-MINH F6-GOP-BAI V-CHUA-DUYET V-THIEU-DU-LIEU F7-TITLE F7-META F7-KEY-PHU F7-LINK F7-NGUON F7-TRUNG-OUTLINE F7-BACKLOG-LAN".split()
)


def record_decision(db, project_id, code, message, *, needs_review=False, **details):
    if code not in REASON_CODES:
        raise ValueError("Mã lý do chưa đăng ký.")
    db.add(
        ProjectEvent(
            project_id=project_id,
            event_type=code,
            level="WARNING" if needs_review else "INFO",
            message=message,
            details_json=json.dumps(
                {"needs_review": needs_review, **details}, ensure_ascii=False
            ),
        )
    )


def preflight(source, pillar_code):
    rules = json.loads((ROOT / "routing.yaml").read_text())
    seen = {}
    retained = []
    decisions = []
    for row in source:
        norm = normalize_text(row.keyword)
        if norm in seen:
            other = seen[norm]
            code = "F2-HAI-MA" if other.content_code != row.content_code else "F2-GOP"
            decisions.append(
                {
                    "code": code,
                    "keyword": row.keyword,
                    "needs_review": code == "F2-HAI-MA",
                    "message": f"{row.keyword}: trùng với {other.content_code}; giữ nguyên chờ duyệt nếu hai mã.",
                }
            )
            continue
        seen[norm] = row
        if any(normalize_text(name) in norm for name in rules["competitor_names"]):
            decisions.append(
                {
                    "code": "F3-THUONG-HIEU",
                    "keyword": row.keyword,
                    "needs_review": True,
                    "message": f"{row.keyword}: chứa thương hiệu đối thủ trong cấu hình.",
                }
            )
            continue
        matched = next(
            (
                r
                for r in rules["pillar_rules"]
                if all(normalize_text(k) in norm for k in r["contains"])
                and r["pillar"] != pillar_code
            ),
            None,
        )
        if matched:
            decisions.append(
                {
                    "code": "F3-CHUYEN-PILLAR",
                    "keyword": row.keyword,
                    "needs_review": True,
                    "message": f"{row.keyword}: đề xuất {matched['pillar']} — {matched['reason']}.",
                }
            )
            continue
        if "thấp" in normalize_text(row.title_match_check):
            decisions.append(
                {
                    "code": "F3-KHOP-THAP",
                    "keyword": row.keyword,
                    "needs_review": True,
                    "message": f"{row.keyword}: mức khớp tiêu đề thấp, cần xem lại góc bài.",
                }
            )
        retained.append(row)
    return retained, decisions


def mapping_handoff(db, project, mapping):
    from app.models import SourceKeyword, EvidenceRow, ProjectEvent
    from app.knowledge import priority_for
    from app.domain.eligibility_policy import (
        load_project_policy_context,
        select_effective_metrics_row,
    )

    source = db.query(SourceKeyword).filter_by(project_id=project.id).all()
    primary = next(
        (
            r
            for r in source
            if r.keyword_normalized == normalize_text(mapping.primary_keyword)
        ),
        None,
    )
    secondary = json.loads(mapping.secondary_keywords_json or "[]")
    policy = load_project_policy_context(db, project)
    verified = []
    questions = []
    for keyword in secondary:
        metric, _, _ = select_effective_metrics_row(
            project, keyword, policy["evidence_rows"], policy["batches_by_id"]
        )
        if metric and metric.volume is not None and metric.kd is not None:
            verified.append(
                {
                    "keyword": keyword,
                    "volume": metric.volume,
                    "kd": metric.kd,
                    "source": metric.id,
                }
            )
        else:
            questions.append(keyword)
    analyses = (
        db.query(ProjectEvent)
        .filter_by(project_id=project.id)
        .order_by(ProjectEvent.created_at.desc())
        .all()
    )
    analysis = (
        next(
            (
                json.loads(e.details_json or "{}").get("serp_analysis")
                for e in analyses
                if json.loads(e.details_json or "{}")
                .get("serp_analysis", {})
                .get("keyword")
                == mapping.primary_keyword
            ),
            {},
        )
        or {}
    )
    notes = next(
        (
            json.loads(e.details_json or "{}").get("note", "")
            for e in analyses
            if json.loads(e.details_json or "{}").get("mapping_id") == mapping.id
            and json.loads(e.details_json or "{}").get("note")
        ),
        "",
    )
    priority, reason = priority_for(mapping.volume, mapping.kd)
    return {
        "article_code": article_code_for(db, project.id, mapping.id),
        "backlog_label": (
            "Backlog dữ liệu"
            if infer_query_asset(mapping.primary_keyword) == "UNKNOWN"
            else (
                "Backlog công cụ"
                if mapping.page_type == "TOOL"
                else (
                    "Backlog tệp"
                    if mapping.page_type == "DOWNLOAD"
                    else (
                        "Bài viết"
                        if mapping.page_type == "ARTICLE"
                        else "Backlog tài nguyên"
                    )
                )
            )
        ),
        "review_notes": notes,
        "mapping_id": mapping.id,
        "content_code": primary.content_code if primary else "",
        "content_title": primary.content_title if primary else "",
        "funnel_stage": primary.funnel_stage if primary else "",
        "priority_reason": reason,
        "verified_secondary": verified,
        "suggested_questions": questions,
        "analysis": analysis,
        "approval_status": "Đã duyệt" if mapping.is_approved else "Chờ duyệt",
    }


def infer_query_asset(keyword: str) -> str:
    low = keyword.lower()
    if any(term in low for term in ("hôm nay", "bảng lãi suất", "giá vàng", "tỷ giá")):
        return "UNKNOWN"  # Backlog dữ liệu, không dùng chứng nhận ARTICLE của V1.6.
    if low.startswith(("câu trả lời mẫu", "mẫu câu trả lời")):
        return "ARTICLE"
    if any(k in low for k in ("công cụ", "calculator", "tool", "máy tính", "quy đổi")):
        return "TOOL"
    if any(
        k in low
        for k in (
            "mẫu ",
            "file excel",
            "template",
            "tải ",
            "download",
            "biểu mẫu",
            "pdf",
        )
    ):
        return "DOWNLOAD"
    if any(k in low for k in ("dịch vụ", "tư vấn", "thuê ngoài", "service")):
        return "SERVICE"
    if any(k in low for k in ("phần mềm", "khóa học", "sản phẩm", "gói ", "bảng giá")):
        return "PRODUCT"
    return "ARTICLE"


def assess_keyword_data(db, project):
    """F1 không đổi keyword nguồn hay quyết định của người duyệt."""
    from datetime import datetime, timezone
    from app.models import SourceKeyword, KeywordCandidate, Approval
    from app.domain.eligibility_policy import (
        load_project_policy_context,
        select_effective_metrics_row,
    )
    from app.knowledge import load_thresholds

    policy = load_project_policy_context(db, project)
    thresholds = load_thresholds()
    source = db.query(SourceKeyword).filter_by(project_id=project.id).all()
    source_norms = {r.keyword_normalized for r in source}
    for row in source:
        metric, batch, _ = select_effective_metrics_row(
            project, row.keyword, policy["evidence_rows"], policy["batches_by_id"]
        )
        if metric is None or metric.volume is None or metric.kd is None:
            code = "F1-CHINH-KHONG-SO" if row.role == "PRIMARY" else "F1-PHU-KHONG-SO"
            message = f"{row.keyword}: " + (
                "key chính thiếu số; xem biến thể Related/Questions và chờ duyệt."
                if row.role == "PRIMARY"
                else "câu hỏi gợi ý (chưa xác minh)."
            )
            record_decision(
                db,
                project.id,
                code,
                message,
                needs_review=row.role == "PRIMARY",
                content_code=row.content_code,
            )
        elif batch and batch.source_timestamp:
            timestamp = batch.source_timestamp
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            if (datetime.now(timezone.utc) - timestamp).days > thresholds["stale_days"]:
                record_decision(
                    db,
                    project.id,
                    "F1-SO-CU",
                    f'{row.keyword}: số liệu cũ hơn {thresholds["stale_days"]} ngày.',
                    needs_review=True,
                    evidence_id=metric.id,
                )
    known = {
        r.keyword_normalized
        for r in db.query(KeywordCandidate).filter_by(project_id=project.id).all()
    }
    for metric in policy["evidence_rows"]:
        batch = policy["batches_by_id"].get(metric.batch_id)
        if (
            not batch
            or batch.report_type not in {"RELATED", "QUESTIONS"}
            or metric.keyword_normalized in source_norms | known
            or metric.row_type != "METRICS"
        ):
            continue
        parent = next(
            (
                row
                for row in source
                if row.role == "PRIMARY"
                and row.keyword_normalized == normalize_text(batch.target_keyword)
            ),
            None,
        )
        if parent is None and len([r for r in source if r.role == "PRIMARY"]) == 1:
            parent = next(r for r in source if r.role == "PRIMARY")
        candidate = KeywordCandidate(
            project_id=project.id,
            keyword=metric.keyword,
            keyword_normalized=metric.keyword_normalized,
            candidate_type="SECONDARY_PROPOSAL",
            source_ref_valid=False,
            source_refs_json=json.dumps(
                [metric.id] + ([f"CONTENT:{parent.content_code}"] if parent else [])
            ),
            rationale=f"Phụ (mới): từ {batch.report_type}, dòng {metric.source_row_number}; cần duyệt intent và phạm vi.",
            status="PENDING_APPROVAL",
        )
        db.add(candidate)
        db.flush()
        known.add(metric.keyword_normalized)
        db.add(
            Approval(
                project_id=project.id,
                approval_type="NEW_TOPIC_PROPOSAL",
                target_ref=candidate.id,
                title=f"Phụ (mới) cần duyệt: {candidate.keyword}",
                proposed_value=candidate.keyword,
                rationale=candidate.rationale,
                scope="RESEARCH_ONLY",
            )
        )
        record_decision(
            db,
            project.id,
            "F1-PHU-MOI",
            candidate.rationale,
            needs_review=True,
            candidate_id=candidate.id,
            evidence_id=metric.id,
        )


def propose_serp_merges(db, project):
    from itertools import combinations
    from app.models import KeywordMapping, Approval
    from app.domain.eligibility_policy import (
        load_project_policy_context,
        evaluate_serp_for_keyword,
    )
    from app.knowledge import load_thresholds

    policy = load_project_policy_context(db, project)
    threshold = load_thresholds()["merge_min_shared_urls"]
    mappings = (
        db.query(KeywordMapping)
        .filter_by(project_id=project.id, is_archived=False, page_type="ARTICLE")
        .all()
    )
    snapshots = {}
    for mapping in mappings:
        serp = evaluate_serp_for_keyword(
            project,
            mapping.primary_keyword,
            policy["evidence_rows"],
            policy["batches_by_id"],
            policy["uploads_by_id"],
            batch_integrity_by_id=policy["batch_integrity_by_id"],
        )
        batch = serp.get("selected_batch_id")
        snapshots[mapping.id] = {
            r.organic_url
            for r in policy["evidence_rows"]
            if batch
            and r.batch_id == batch
            and r.keyword_normalized == normalize_text(mapping.primary_keyword)
            and r.organic_valid
            and r.serp_result_type == "ORGANIC"
            and r.organic_position
            and r.organic_position <= 10
        }
    for left, right in combinations(mappings, 2):
        shared = snapshots[left.id] & snapshots[right.id]
        if len(shared) < threshold:
            continue
        target = "merge:" + ":".join(sorted([left.id, right.id]))
        if (
            db.query(Approval)
            .filter_by(project_id=project.id, target_ref=target)
            .first()
        ):
            continue
        message = f"{left.primary_keyword} / {right.primary_keyword}: chung {len(shared)} URL top 10 ≥ {threshold}; đề xuất xem xét gộp, không tự đổi keyword hay URL."
        db.add(
            Approval(
                project_id=project.id,
                approval_type="OVERLAP_MERGE_SPLIT",
                target_ref=target,
                title="Xem xét gộp hai bài có SERP giao nhau",
                rationale=message,
                evidence_json=json.dumps(sorted(shared)),
                scope="RESEARCH_ONLY",
            )
        )
        record_decision(
            db,
            project.id,
            "F6-GOP-BAI",
            message,
            needs_review=True,
            mapping_ids=[left.id, right.id],
            shared_urls=sorted(shared),
        )


def article_code_for(db, project_id, mapping_id):
    from app.models import KeywordMapping, ContentBrief

    existing = (
        db.query(ContentBrief)
        .filter_by(project_id=project_id, keyword_mapping_id=mapping_id)
        .first()
    )
    if existing:
        return existing.br_code
    rows = (
        db.query(KeywordMapping)
        .filter_by(project_id=project_id)
        .order_by(KeywordMapping.created_at.asc(), KeywordMapping.id.asc())
        .all()
    )
    position = next(
        (index for index, row in enumerate(rows, 1) if row.id == mapping_id),
        len(rows) + 1,
    )
    used = {
        row.br_code
        for row in db.query(ContentBrief).filter_by(project_id=project_id).all()
    }
    candidate = f"BR{position:02d}"
    while candidate in used:
        position += 1
        candidate = f"BR{position:02d}"
    return candidate
