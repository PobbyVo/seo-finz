from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.db import get_db
from app.domain.brief_engine import (
    BriefEligibilityError,
    ENGAGEMENT_TACTICS,
    WRITING_FORMULAS,
    generate_content_briefs,
    serialize_brief,
)
from app.domain.eligibility_policy import compute_effective_brief_freshness
from app.domain.exporter import (
    compute_project_export_state,
    evaluate_export_record_freshness,
    export_project_bundle,
)
from app.domain.quality_gates import evaluate_all_gates
from app.domain.workflow import refresh_workflow_state
from app.models import ContentBrief, ExportRecord, KeywordMapping, Project, ProjectEvent
from app.schemas import BriefGenerateRequest, ExportRequest

router = APIRouter(prefix="/projects/{project_id}", tags=["briefs-exports"])


@router.get("/briefs")
def list_briefs(project_id: str, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Không tìm thấy dự án.")
    briefs = (
        db.query(ContentBrief)
        .filter(ContentBrief.project_id == project_id)
        .order_by(ContentBrief.br_code.asc())
        .all()
    )
    gates = evaluate_all_gates(db, project)
    active_mappings = (
        db.query(KeywordMapping)
        .filter(KeywordMapping.project_id == project_id, KeywordMapping.is_archived == False)  # noqa: E712
        .order_by(KeywordMapping.priority.asc(), KeywordMapping.created_at.asc())
        .all()
    )
    mappings_by_id = {m.id: m for m in active_mappings}
    elig_map = gates["mapping_eligibilities"]

    serialized_briefs = [
        serialize_brief(
            b,
            freshness=compute_effective_brief_freshness(
                b,
                mappings_by_id.get(b.keyword_mapping_id) if b.keyword_mapping_id else None,
                elig_map.get(b.keyword_mapping_id) if b.keyword_mapping_id else None,
            ),
        )
        for b in briefs
    ]

    return {
        "briefs": serialized_briefs,
        "mappings_eligibility": [
            {
                "id": m.id,
                "primary_keyword": m.primary_keyword,
                "page_type": m.page_type,
                "revision": m.revision,
                "eligibility": elig_map[m.id],
            }
            for m in active_mappings
        ],
        "writing_formulas_catalog": WRITING_FORMULAS,
        "engagement_tactics_catalog": ENGAGEMENT_TACTICS,
        "workflow": refresh_workflow_state(db, project),
    }


@router.post("/briefs/generate")
def generate_briefs(project_id: str, payload: BriefGenerateRequest, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Không tìm thấy dự án.")

    try:
        res = generate_content_briefs(
            db,
            project,
            allow_draft=payload.allow_draft,
            mapping_ids=payload.mapping_ids,
        )
    except BriefEligibilityError as exc:
        raise HTTPException(status_code=400, detail=exc.detail)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    db.add(
        ProjectEvent(
            project_id=project.id,
            level="SUCCESS",
            event_type="CONTENT_BRIEFS_GENERATED",
            message=(
                f"Đã tạo {len(res['briefs'])} Content Brief "
                f"({res['official_count']} CHÍNH THỨC, {res['draft_count']} DỰ THẢO)."
            ),
        )
    )
    db.commit()

    return {
        "saved": True,
        "navigation_eligible": False,  # Final step
        **res,
        "workflow": refresh_workflow_state(db, project),
    }


@router.get("/exports")
def list_exports(project_id: str, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Không tìm thấy dự án.")
    live_state = compute_project_export_state(db, project)
    records = (
        db.query(ExportRecord)
        .filter(ExportRecord.project_id == project_id)
        .order_by(ExportRecord.created_at.desc())
        .all()
    )
    items = []
    for r in records:
        fresh = evaluate_export_record_freshness(r, live_state)
        items.append(
            {
                "id": r.id,
                "export_format": r.export_format,
                "filename": r.filename,
                "brief_mode": r.brief_mode,
                "recorded_brief_mode": r.brief_mode,
                "is_superseded": fresh["is_superseded"],
                "freshness_status": fresh["freshness_status"],
                "superseded_reason": fresh["superseded_reason"],
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "download_url": f"/api/v1/projects/{project_id}/exports/file/{r.id}",
                "historical_download_url": f"/api/v1/projects/{project_id}/exports/file/{r.id}?acknowledge_historical=true",
            }
        )
    return {"exports": items}


@router.post("/exports/download")
def create_and_download_export(project_id: str, payload: ExportRequest, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Không tìm thấy dự án.")
    try:
        content, filename, media_type, rec = export_project_bundle(db, project, payload.format)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-FinZ-Export-Filename": filename,
            "X-FinZ-Export-Id": rec.id,
            "X-FinZ-Export-Freshness": "CURRENT",
        },
    )


@router.get("/exports/file/{export_id}")
def download_existing_export(
    project_id: str,
    export_id: str,
    acknowledge_historical: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Không tìm thấy dự án.")

    rec = db.get(ExportRecord, export_id)
    if not rec or rec.project_id != project_id:
        raise HTTPException(status_code=404, detail="Không tìm thấy bản xuất.")
    p = Path(rec.stored_path)
    if not p.exists():
        raise HTTPException(status_code=404, detail="File xuất không còn tồn tại trên đĩa.")

    live_state = compute_project_export_state(db, project)
    fresh = evaluate_export_record_freshness(rec, live_state)

    if fresh["is_superseded"] and not acknowledge_historical:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "HISTORICAL_EXPORT_SUPERSEDED",
                "reason": (
                    f"Bản xuất lịch sử '{rec.filename}' ({rec.brief_mode}) đã hết hiệu lực do bằng chứng hoặc Mapping thay đổi. "
                    f"{fresh['superseded_reason']}"
                ).strip(),
                "impact": "Tải âm thầm bản xuất cũ có thể khiến biên tập viên dùng tài liệu OFFICIAL lỗi thời.",
                "solution": "Hãy xuất bản mới nhất tại Bước 07, hoặc xác nhận tải bản lịch sử để đối chiếu bằng tham số acknowledge_historical=true.",
                "next_action": "Xuất lại file mới nhất tại Bước 07 hoặc xác nhận tải bản lưu lịch sử.",
                "cta_label": "Mở Bước 07",
                "cta_href": "/steps/07-brief",
                "historical_download_url": f"/api/v1/projects/{project_id}/exports/file/{rec.id}?acknowledge_historical=true",
            },
        )

    media_types = {
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "csv": "text/csv; charset=utf-8",
        "json": "application/json; charset=utf-8",
        "html": "text/html; charset=utf-8",
    }
    dl_name = f"HISTORICAL_SUPERSEDED_{rec.filename}" if fresh["is_superseded"] else rec.filename
    headers = {
        "Content-Disposition": f'attachment; filename="{dl_name}"',
        "X-FinZ-Export-Freshness": "HISTORICAL_SUPERSEDED" if fresh["is_superseded"] else "CURRENT",
    }
    if fresh["is_superseded"]:
        headers["X-FinZ-Export-Warning"] = "Historical export superseded by newer evidence"

    return Response(
        content=p.read_bytes(),
        media_type=media_types.get(rec.export_format, "application/octet-stream"),
        headers=headers,
    )
