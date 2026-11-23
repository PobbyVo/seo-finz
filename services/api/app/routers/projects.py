from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import BackupError, backup_database, get_db
from app.domain.taxonomy_parser import normalize_text
from app.domain.workflow import ensure_workflow_steps, refresh_workflow_state
from app.models import (
    AIRun,
    Approval,
    Project,
    ProjectEvent,
    ProjectSnapshot,
    SourceKeyword,
)
from app.schemas import ProjectCreateRequest, ProjectUpdateRequest

router = APIRouter(prefix="/projects", tags=["projects"])


def serialize_project(db: Session, project: Project, *, include_workflow: bool = True) -> dict[str, Any]:
    secondary = json.loads(project.secondary_keywords_json or "[]")
    provenance = json.loads(project.provenance_json or "{}")
    base: dict[str, Any] = {
        "id": project.id,
        "code": project.code,
        "name": project.name,
        "pillar_name": project.pillar_name,
        "topic_pillar_code": project.topic_pillar_code,
        "topic_pillar_name": project.topic_pillar_name,
        "topic_type": project.topic_type,
        "split_axis": project.split_axis,
        "main_topic": project.main_topic,
        "content_code": project.content_code,
        "content_title": project.content_title,
        "primary_keyword_original": project.primary_keyword_original,
        "primary_keyword_current": project.primary_keyword_current,
        "secondary_keywords": secondary,
        "business_goal": project.business_goal,
        "target_audience": project.target_audience,
        "market": project.market,
        "language": project.language,
        "soft_article_min": project.soft_article_min,
        "soft_article_max": project.soft_article_max,
        "provenance": provenance,
        "version": project.version,
        "research_cycle": project.research_cycle,
        "status": project.status,
        "created_at": project.created_at.isoformat() if project.created_at else None,
        "updated_at": project.updated_at.isoformat() if project.updated_at else None,
    }
    if include_workflow:
        base["workflow"] = refresh_workflow_state(db, project)
    return base


def _sync_source_keywords(db: Session, project: Project, *, provenance: dict[str, Any] | None = None) -> None:
    """Keep original source keywords immutable while adding newly specified keywords with provenance."""
    existing = {
        sk.keyword_normalized: sk
        for sk in db.query(SourceKeyword).filter(SourceKeyword.project_id == project.id).all()
    }
    prov = provenance or json.loads(project.provenance_json or "{}")
    tp_code = project.topic_pillar_code or project.code
    c_code = project.content_code or f"{tp_code}-01"
    default_ref = f"CONTENT:{c_code}" if project.content_code else f"TOPIC:{tp_code}"

    pk = project.primary_keyword_original or project.primary_keyword_current
    if pk:
        norm = normalize_text(pk)
        if norm not in existing:
            db.add(
                SourceKeyword(
                    project_id=project.id,
                    topic_pillar_code=tp_code,
                    content_code=c_code,
                    keyword=pk.strip(),
                    keyword_normalized=norm,
                    role="PRIMARY",
                    is_original=True,
                    source_ref=default_ref,
                    source_file=str(prov.get("source_file", "manual_form")),
                    source_sheet=str(prov.get("source_sheet", "")),
                    source_row=prov.get("source_row"),
                )
            )
            existing[norm] = True  # type: ignore[assignment]

    for sk in json.loads(project.secondary_keywords_json or "[]"):
        cleaned = str(sk).strip()
        norm = normalize_text(cleaned)
        if cleaned and norm not in existing:
            db.add(
                SourceKeyword(
                    project_id=project.id,
                    topic_pillar_code=tp_code,
                    content_code=c_code,
                    keyword=cleaned,
                    keyword_normalized=norm,
                    role="SECONDARY",
                    is_original=True,
                    source_ref=default_ref,
                    source_file=str(prov.get("source_file", "manual_form")),
                    source_sheet=str(prov.get("source_sheet", "")),
                    source_row=prov.get("source_row"),
                )
            )
            existing[norm] = True  # type: ignore[assignment]


def _save_snapshot(db: Session, project: Project, reason: str) -> None:
    payload = {
        "code": project.code,
        "name": project.name,
        "pillar_name": project.pillar_name,
        "topic_pillar_code": project.topic_pillar_code,
        "topic_pillar_name": project.topic_pillar_name,
        "topic_type": project.topic_type,
        "split_axis": project.split_axis,
        "main_topic": project.main_topic,
        "content_code": project.content_code,
        "content_title": project.content_title,
        "primary_keyword_original": project.primary_keyword_original,
        "primary_keyword_current": project.primary_keyword_current,
        "secondary_keywords": json.loads(project.secondary_keywords_json or "[]"),
        "business_goal": project.business_goal,
        "target_audience": project.target_audience,
        "market": project.market,
        "language": project.language,
        "version": project.version,
    }
    db.add(
        ProjectSnapshot(
            project_id=project.id,
            version=project.version,
            reason=reason,
            payload_json=json.dumps(payload, ensure_ascii=False),
        )
    )


@router.get("")
def list_projects(db: Session = Depends(get_db)):
    projects = db.query(Project).order_by(Project.updated_at.desc()).all()
    return {
        "projects": [serialize_project(db, p, include_workflow=True) for p in projects],
    }


@router.post("", status_code=201)
def create_project(payload: ProjectCreateRequest, db: Session = Depends(get_db)):
    pk = payload.primary_keyword.strip()
    project = Project(
        code=payload.code.strip().upper(),
        name=payload.name.strip(),
        pillar_name=payload.pillar_name.strip(),
        topic_pillar_code=(payload.topic_pillar_code or payload.code).strip().upper(),
        topic_pillar_name=payload.topic_pillar_name.strip(),
        topic_type=payload.topic_type.strip(),
        split_axis=payload.split_axis.strip(),
        main_topic=payload.main_topic.strip(),
        content_code=payload.content_code.strip(),
        content_title=payload.content_title.strip(),
        primary_keyword_original=pk,
        primary_keyword_current=pk,
        secondary_keywords_json=json.dumps([k.strip() for k in payload.secondary_keywords if k.strip()], ensure_ascii=False),
        business_goal=payload.business_goal.strip(),
        target_audience=payload.target_audience.strip(),
        market=payload.market.strip() or "VN",
        language=payload.language.strip() or "vi",
        soft_article_min=payload.soft_article_min,
        soft_article_max=max(payload.soft_article_min, payload.soft_article_max),
        provenance_json=json.dumps({"source": "manual_create"}, ensure_ascii=False),
        version=1,
    )
    db.add(project)
    db.flush()
    ensure_workflow_steps(db, project.id)
    _sync_source_keywords(db, project)
    _save_snapshot(db, project, "Khởi tạo dự án")
    db.add(
        ProjectEvent(
            project_id=project.id,
            level="SUCCESS",
            event_type="PROJECT_CREATED",
            message=f"Đã tạo dự án {project.code} — {project.name} trong SQLite.",
        )
    )
    db.commit()
    db.refresh(project)
    return {
        "saved": True,
        "navigation_eligible": bool(project.primary_keyword_original),
        "next_step_href": "/steps/02-demand-map" if project.primary_keyword_original else "/steps/01-topic",
        "project": serialize_project(db, project, include_workflow=True),
    }


@router.get("/{project_id}")
def get_project(project_id: str, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Không tìm thấy dự án.")
    snapshots = (
        db.query(ProjectSnapshot)
        .filter(ProjectSnapshot.project_id == project_id)
        .order_by(ProjectSnapshot.version.desc())
        .limit(20)
        .all()
    )
    source_keywords = db.query(SourceKeyword).filter(SourceKeyword.project_id == project_id).all()
    return {
        "project": serialize_project(db, project, include_workflow=True),
        "source_keywords": [
            {
                "id": sk.id,
                "topic_pillar_code": sk.topic_pillar_code,
                "content_code": sk.content_code,
                "keyword": sk.keyword,
                "role": sk.role,
                "is_original": sk.is_original,
                "source_ref": sk.source_ref,
                "source_file": sk.source_file,
                "source_row": sk.source_row,
            }
            for sk in source_keywords
        ],
        "snapshots": [
            {
                "id": s.id,
                "version": s.version,
                "reason": s.reason,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in snapshots
        ],
    }


@router.put("/{project_id}")
def update_project(project_id: str, payload: ProjectUpdateRequest, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Không tìm thấy dự án.")

    approval_created = False
    for field_name in (
        "code",
        "name",
        "pillar_name",
        "topic_pillar_code",
        "topic_pillar_name",
        "topic_type",
        "split_axis",
        "main_topic",
        "content_code",
        "content_title",
        "business_goal",
        "target_audience",
        "market",
        "language",
        "soft_article_min",
        "soft_article_max",
    ):
        val = getattr(payload, field_name)
        if val is not None:
            setattr(project, field_name, val.strip() if isinstance(val, str) else val)

    if payload.secondary_keywords is not None:
        cleaned = [k.strip() for k in payload.secondary_keywords if k.strip()]
        project.secondary_keywords_json = json.dumps(cleaned, ensure_ascii=False)

    # CRITICAL RULE (T05): Preserve original primary keyword! Changing it creates PENDING Approval.
    if payload.primary_keyword is not None:
        new_pk = payload.primary_keyword.strip()
        if not project.primary_keyword_original:
            project.primary_keyword_original = new_pk
            project.primary_keyword_current = new_pk
        elif normalize_text(new_pk) != normalize_text(project.primary_keyword_original) and new_pk:
            # Keep original intact and queue approval before replacing official primary keyword
            db.add(
                Approval(
                    project_id=project.id,
                    approval_type="PRIMARY_KEYWORD_CHANGE",
                    target_ref=project.id,
                    title=f"Đổi Keyword chính: '{project.primary_keyword_original}' → '{new_pk}'",
                    original_value=project.primary_keyword_original,
                    proposed_value=new_pk,
                    rationale=payload.change_reason or "Người dùng đề xuất đổi keyword chính tại Bước 01.",
                    evidence_json=json.dumps([f"Keyword chính gốc được bảo toàn: {project.primary_keyword_original}"], ensure_ascii=False),
                    impact="Thay đổi từ khóa mục tiêu chính của dự án; cần duyệt chính thức tại Chờ phê duyệt.",
                    scope="BRIEF_ELIGIBILITY",
                    status="PENDING",
                    version=project.version + 1,
                )
            )
            approval_created = True

    project.version += 1
    _sync_source_keywords(db, project)
    _save_snapshot(db, project, payload.change_reason)
    db.add(
        ProjectEvent(
            project_id=project.id,
            level="SUCCESS",
            event_type="PROJECT_UPDATED",
            message=f"Đã lưu cấu hình dự án {project.code} (phiên bản v{project.version}) vào SQLite.",
            details_json=json.dumps({"approval_created": approval_created}),
        )
    )
    db.commit()
    db.refresh(project)

    ready_for_step2 = bool(
        (project.topic_pillar_code or project.topic_pillar_name or project.main_topic)
        and (project.primary_keyword_original or project.primary_keyword_current)
        and not approval_created
    )
    return {
        "saved": True,
        "version": project.version,
        "primary_change_pending_approval": approval_created,
        "navigation_eligible": ready_for_step2,
        "next_step_href": "/steps/02-demand-map",
        "message": (
            f"Đã lưu phiên bản v{project.version} vào SQLite. Thay đổi Keyword chính đã chuyển sang Chờ phê duyệt (bản gốc vẫn được giữ nguyên)."
            if approval_created
            else f"Đã lưu phiên bản v{project.version} vào SQLite thành công."
        ),
        "project": serialize_project(db, project, include_workflow=True),
    }


@router.delete("/{project_id}")
def delete_project(project_id: str, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Không tìm thấy dự án.")
    backup_database(reason=f"before_delete_{project.code}")
    db.delete(project)
    db.commit()
    return {"deleted": True, "project_id": project_id}


@router.get("/{project_id}/logs")
def get_project_logs(project_id: str, reason_code: str | None = None, needs_review: bool | None = None, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Không tìm thấy dự án.")

    events = (
        db.query(ProjectEvent)
        .filter((ProjectEvent.project_id == project_id) | (ProjectEvent.project_id.is_(None)))
        .order_by(ProjectEvent.created_at.desc())
        .limit(100)
        .all()
    )
    if reason_code:
        events = [e for e in events if e.event_type == reason_code]
    if needs_review is not None:
        events = [e for e in events if bool(json.loads(e.details_json or "{}").get("needs_review")) == needs_review]
    ai_runs = (
        db.query(AIRun)
        .filter((AIRun.project_id == project_id) | (AIRun.project_id.is_(None)))
        .order_by(AIRun.created_at.desc())
        .limit(50)
        .all()
    )
    snapshots = (
        db.query(ProjectSnapshot)
        .filter(ProjectSnapshot.project_id == project_id)
        .order_by(ProjectSnapshot.version.desc())
        .limit(30)
        .all()
    )

    return {
        "events": [
            {
                "id": e.id,
                "level": e.level,
                "event_type": e.event_type,
                "message": e.message,
                "details": json.loads(e.details_json or "{}"),
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in events
        ],
        "ai_runs": [
            {
                "id": r.id,
                "role": r.role,
                "provider": r.provider,
                "requested_model": r.requested_model,
                "actual_model": r.actual_model,
                "prompt_version": r.prompt_version,
                "research_cycle": r.research_cycle,
                "latency_ms": r.latency_ms,
                "fallback_events": json.loads(r.fallback_events_json or "[]"),
                "source_refs": json.loads(r.source_refs_json or "[]"),
                "status": r.status,
                "error_code": r.error_code,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in ai_runs
        ],
        "snapshots": [
            {
                "id": s.id,
                "version": s.version,
                "reason": s.reason,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in snapshots
        ],
    }


@router.post("/{project_id}/backup")
def create_safe_backup(project_id: str, db: Session = Depends(get_db)):
    """Create verified online SQLite backup & return safe JSON backup snapshot (guaranteed NO API keys)."""
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Không tìm thấy dự án.")
    try:
        backup_file = backup_database(reason=f"project_{project.code}")
    except BackupError as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "DB_BACKUP_FAILED",
                "reason": str(exc),
                "impact": "Bản sao lưu SQLite không tạo được hoặc không vượt qua kiểm tra toàn vẹn (fail closed).",
                "solution": "Kiểm tra dung lượng đĩa và quyền ghi thư mục data/backups/ rồi thử lại.",
                "next_action": "Giải phóng dung lượng đĩa và tạo sao lưu lại.",
            },
        )
    return {
        "ok": True,
        "sqlite_backup_filename": backup_file.name if backup_file else None,
        "integrity_verified": backup_file is not None,
        "contains_api_keys": False,
        "project_snapshot": serialize_project(db, project, include_workflow=True),
    }
