"""Lọc volume theo chính sách dự án, giữ nguồn và đề xuất nghiên cứu riêng."""

import json
from app.domain.taxonomy_parser import normalize_text
from app.domain.eligibility_policy import (
    load_project_policy_context,
    select_effective_metrics_row,
)
from app.models import SourceKeyword


def enabled(project):
    return bool(
        json.loads(project.provenance_json or "{}").get(
            "exclude_keywords_without_volume"
        )
    )


def volume_for(db, project, keyword, context=None):
    ctx = context or load_project_policy_context(db, project)
    row, _, _ = select_effective_metrics_row(
        project, keyword, ctx["evidence_rows"], ctx["batches_by_id"]
    )
    return row.volume if row else None


def source_review(db, project):
    ctx = load_project_policy_context(db, project)
    rows = []
    for source in db.query(SourceKeyword).filter_by(project_id=project.id).all():
        value = volume_for(db, project, source.keyword, ctx)
        rows.append(
            {
                "keyword": source.keyword,
                "role": source.role,
                "content_code": source.content_code,
                "volume": value,
                "included": value is not None and value > 0,
                "reason": (
                    "Đã có Volume dương"
                    if value is not None and value > 0
                    else (
                        "Volume bằng 0"
                        if value == 0
                        else "Chưa có Volume; loại khỏi kế hoạch, giữ nguyên nguồn"
                    )
                ),
            }
        )
    return rows


def refresh_candidates(db, project):
    from app.models import KeywordCandidate, Approval, ResearchRequest

    context = load_project_policy_context(db, project)
    for candidate in (
        db.query(KeywordCandidate)
        .filter_by(project_id=project.id, candidate_type="RESEARCH_EXPANSION")
        .all()
    ):
        value = volume_for(db, project, candidate.keyword, context)
        if value is None:
            continue
        if value <= 0:
            if candidate.status == "WAITING_SEMRUSH":
                candidate.status = "EXCLUDED_ZERO_VOLUME"
            continue
        if (
            not db.query(ResearchRequest)
            .filter_by(
                project_id=project.id,
                seed_keyword=candidate.keyword,
                report_type="ORGANIC_RESULTS",
            )
            .first()
        ):
            db.add(
                ResearchRequest(
                    project_id=project.id,
                    seed_keyword=candidate.keyword,
                    report_type="ORGANIC_RESULTS",
                    market=project.market,
                    origin="EXPANSION_V2",
                    purpose="Kiểm SERP cho keyword mới có Volume; chưa duyệt bài.",
                )
            )
        if (
            not db.query(Approval)
            .filter_by(
                project_id=project.id,
                target_ref=candidate.id,
                approval_type="NEW_TOPIC_PROPOSAL",
            )
            .first()
        ):
            candidate.status = "PENDING_APPROVAL"
            db.add(
                Approval(
                    project_id=project.id,
                    approval_type="NEW_TOPIC_PROPOSAL",
                    target_ref=candidate.id,
                    title=f"Chủ đề mới có Volume: {candidate.keyword}",
                    proposed_value=candidate.keyword,
                    rationale=candidate.rationale,
                    scope="RESEARCH_ONLY",
                )
            )
