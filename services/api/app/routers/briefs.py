from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
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
from app.domain.exporter import export_project_bundle
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
    return {
        "briefs": [serialize_brief(b) for b in briefs],
        "mappings_eligibility": [
            {
                "id": m.id,
                "primary_keyword": m.primary_keyword,
                "page_type": m.page_type,
                "revision": m.revision,
                "eligibility": gates["mapping_eligibilities"][m.id],
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
    records = (
        db.query(ExportRecord)
        .filter(ExportRecord.project_id == project_id)
        .order_by(ExportRecord.created_at.desc())
        .all()
    )
    return {
        "exports": [
            {
                "id": r.id,
                "export_format": r.export_format,
                "filename": r.filename,
                "brief_mode": r.brief_mode,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "download_url": f"/api/v1/projects/{project_id}/exports/file/{r.id}",
            }
            for r in records
        ]
    }


@router.post("/exports/download")
def create_and_download_export(project_id: str, payload: ExportRequest, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Không tìm thấy dự án.")
    try:
        content, filename, media_type, _rec = export_project_bundle(db, project, payload.format)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-FinZ-Export-Filename": filename,
        },
    )


@router.get("/exports/file/{export_id}")
def download_existing_export(project_id: str, export_id: str, db: Session = Depends(get_db)):
    rec = db.get(ExportRecord, export_id)
    if not rec or rec.project_id != project_id:
        raise HTTPException(status_code=404, detail="Không tìm thấy bản xuất.")
    p = Path(rec.stored_path)
    if not p.exists():
        raise HTTPException(status_code=404, detail="File xuất không còn tồn tại trên đĩa.")
    media_types = {
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "csv": "text/csv; charset=utf-8",
        "json": "application/json; charset=utf-8",
        "html": "text/html; charset=utf-8",
    }
    return Response(
        content=p.read_bytes(),
        media_type=media_types.get(rec.export_format, "application/octet-stream"),
        headers={"Content-Disposition": f'attachment; filename="{rec.filename}"'},
    )
