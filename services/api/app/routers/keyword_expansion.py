import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import (
    Project,
    KeywordCandidate,
    ResearchRequest,
    ProjectEvent,
    Approval,
)
from app.domain.keyword_expansion import source_review, volume_for
from app.domain.taxonomy_parser import normalize_text
from app.knowledge import ROOT

router = APIRouter(
    prefix="/projects/{project_id}/keyword-expansion", tags=["keyword-research"]
)


@router.get("")
def review(project_id: str, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Không tìm thấy dự án.")
    rows = source_review(db, project)
    candidates = (
        db.query(KeywordCandidate)
        .filter_by(project_id=project.id, candidate_type="RESEARCH_EXPANSION")
        .all()
    )
    from app.domain.eligibility_policy import (
        load_project_policy_context,
        select_effective_metrics_row,
    )

    context = load_project_policy_context(db, project)
    metrics = {
        c.id: select_effective_metrics_row(
            project, c.keyword, context["evidence_rows"], context["batches_by_id"]
        )[0]
        for c in candidates
    }
    return {
        "source_keywords": rows,
        "target_min": project.soft_article_min,
        "target_max": project.soft_article_max,
        "candidates": [
            {
                "id": c.id,
                "keyword": c.keyword,
                "rationale": c.rationale,
                "status": c.status,
                "volume": volume_for(db, project, c.keyword),
                "kd": metrics[c.id].kd if metrics[c.id] else None,
            }
            for c in candidates
        ],
        "notice": "Keyword mới chỉ là giả thuyết; cần Semrush, kiểm intent/SERP và người duyệt trước khi tạo bài.",
    }


@router.post("")
def propose(project_id: str, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Không tìm thấy dự án.")
    provenance = json.loads(project.provenance_json or "{}")
    provenance["exclude_keywords_without_volume"] = True
    project.provenance_json = json.dumps(provenance, ensure_ascii=False)
    code = (project.topic_pillar_code or project.code).upper()
    seeds = (
        json.loads((ROOT / "p01_research_seeds.json").read_text())
        if code == "P01"
        else []
    )
    for seed in seeds:
        norm = normalize_text(seed["keyword"])
        candidate = (
            db.query(KeywordCandidate)
            .filter_by(project_id=project.id, keyword_normalized=norm)
            .first()
        )
        if not candidate:
            candidate = KeywordCandidate(
                project_id=project.id,
                keyword=seed["keyword"],
                keyword_normalized=norm,
                candidate_type="RESEARCH_EXPANSION",
                status="WAITING_SEMRUSH",
                source_refs_json=json.dumps([f"TOPIC:{code}"]),
                source_ref_valid=False,
                rationale=f"Góc bài giả thuyết: {seed['angle']}. {seed['reason']}. Chưa có Volume/KD, chưa duyệt bài mới.",
            )
            db.add(candidate)
    db.flush()
    for candidate in (
        db.query(KeywordCandidate)
        .filter_by(project_id=project.id, candidate_type="RESEARCH_EXPANSION")
        .all()
    ):
        if (volume_for(db, project, candidate.keyword) or 0) > 0 and not db.query(
            Approval
        ).filter_by(
            project_id=project.id,
            target_ref=candidate.id,
            approval_type="NEW_TOPIC_PROPOSAL",
        ).first():
            candidate.status = "PENDING_APPROVAL"
            db.add(
                Approval(
                    project_id=project.id,
                    approval_type="NEW_TOPIC_PROPOSAL",
                    target_ref=candidate.id,
                    title=f"Chủ đề mới đã có Volume, chờ duyệt: {candidate.keyword}",
                    rationale=candidate.rationale,
                    proposed_value=candidate.keyword,
                    scope="RESEARCH_ONLY",
                )
            )
    keywords = "\n".join(s["keyword"] for s in seeds)
    if (
        keywords
        and not db.query(ResearchRequest)
        .filter_by(
            project_id=project.id,
            origin="EXPANSION_V2",
            report_type="KEYWORD_OVERVIEW",
            seed_keyword=keywords,
        )
        .first()
    ):
        db.add(
            ResearchRequest(
                project_id=project.id,
                origin="EXPANSION_V2",
                report_type="KEYWORD_OVERVIEW",
                seed_keyword=keywords,
                market="VN",
                expected_columns_json=json.dumps(
                    ["Keyword", "Volume", "Keyword Difficulty", "Intent"]
                ),
                semrush_steps_json=json.dumps(
                    [
                        "Mở Keyword Overview → Bulk Analysis, chọn database Vietnam (VN).",
                        "Dán danh sách keyword trong phiếu, không lấy số từ bản mẫu.",
                        "Xuất CSV/XLSX có Keyword, Volume, Keyword Difficulty và Intent nếu có.",
                        "Tải kết quả về Bước 04, chọn phiếu này và xác nhận import.",
                        "Sau khi có số, kiểm SERP/intent và duyệt chủ đề trước khi đưa vào mapping.",
                    ],
                    ensure_ascii=False,
                ),
                purpose="Kiểm tra keyword mới để hướng tới 5–7 bài độc lập. Volume/KD chưa xác minh; không tách đồng nghĩa thành bài.",
            )
        )
    db.add(
        ProjectEvent(
            project_id=project.id,
            event_type="VOLUME_POLICY_ENABLED",
            message="Loại keyword thiếu Volume/Volume 0 khỏi kế hoạch; giữ nguồn và tạo danh sách nghiên cứu Semrush riêng.",
        )
    )
    db.commit()
    from app.domain.mapping_engine import build_keyword_mapping_preview

    build_keyword_mapping_preview(db, project)
    return review(project_id, db)
