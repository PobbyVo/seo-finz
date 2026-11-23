from __future__ import annotations

import hashlib
import json
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.config import ensure_data_dirs, settings
from app.db import get_db
from app.domain.taxonomy_parser import normalize_text, parse_topic_source_file
from app.security.upload_guard import build_unique_upload_path, read_bounded_upload, sanitize_upload_filename
from app.models import (
    ContentCode,
    FileUpload,
    Project,
    ProjectEvent,
    ProjectSnapshot,
    SourceKeyword,
    TaxonomyPillar,
    TopicPillar,
)
from app.routers.projects import serialize_project
from app.schemas import TopicSourceConfirmRequest

router = APIRouter(prefix="/projects/{project_id}/topic-source", tags=["topic-source"])


@router.post("/preview")
async def preview_topic_source(
    project_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    Step 01 preview ONLY:
    - Parses Topic Pillar (even at row 4) and Keywords (even at row 1).
    - Does NOT overwrite project form data or mark step complete until user clicks Confirm!
    """
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Không tìm thấy dự án.")

    raw = await read_bounded_upload(file)
    filename = sanitize_upload_filename(file.filename, default_name="topic_source.xlsx")
    try:
        preview = parse_topic_source_file(raw, filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    for warning in preview.warnings:
        if warning.get("severity") == "ERROR":
            db.add(ProjectEvent(project_id=project.id,level="WARNING",event_type=warning["code"],message=warning["message"],details_json=json.dumps({**warning,"needs_review":True},ensure_ascii=False)))
    ensure_data_dirs()
    sha = hashlib.sha256(raw).hexdigest()
    stored = build_unique_upload_path(settings.uploads_dir, project.id, "topic", sha, filename)
    stored.write_bytes(raw)

    upload = FileUpload(
        project_id=project.id,
        purpose="TOPIC_SOURCE",
        filename=filename,
        stored_path=str(stored),
        sha256=sha,
        size_bytes=len(raw),
        file_format=preview.file_format,
        sheet_name=preview.topic_pillar_sheet or preview.keywords_sheet,
        row_count_total=len(preview.topic_pillars) + len(preview.content_items),
        status="PREVIEWED",
        preview_meta_json=json.dumps(
            {
                "topic_pillar_sheet": preview.topic_pillar_sheet,
                "topic_pillar_header_row": preview.topic_pillar_header_row,
                "keywords_sheet": preview.keywords_sheet,
                "keywords_header_row": preview.keywords_header_row,
                "topic_pillars": preview.topic_pillars,
                "content_items": preview.content_items,
                "validation_errors": [w for w in preview.warnings if w.get("severity") == "ERROR"],
            },
            ensure_ascii=False,
        ),
    )
    db.add(upload)
    db.commit()
    db.refresh(upload)

    return {
        "upload_id": upload.id,
        "saved_to_project": False,  # Preview never overwrites project until confirmed!
        "navigation_eligible": False,
        "filename": filename,
        "file_format": preview.file_format,
        "sheets_scanned": preview.sheets_scanned,
        "topic_pillar_sheet": preview.topic_pillar_sheet,
        "topic_pillar_header_row": preview.topic_pillar_header_row,
        "keywords_sheet": preview.keywords_sheet,
        "keywords_header_row": preview.keywords_header_row,
        "topic_pillars": preview.topic_pillars,
        "content_items": preview.content_items,
        "warnings": preview.warnings,
        "stats": preview.stats,
        "notice": (
            "Đây là bản xem trước. Hãy chọn Topic Pillar và Mã nội dung rồi bấm 'Điền vào form', "
            "nhập thêm Mục tiêu kinh doanh & Đối tượng độc giả (hệ thống không tự suy đoán) và bấm Xác nhận lưu."
        ),
    }


@router.post("/confirm")
def confirm_topic_source(
    project_id: str,
    payload: TopicSourceConfirmRequest,
    db: Session = Depends(get_db),
):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Không tìm thấy dự án.")

    upload = db.get(FileUpload, payload.upload_id)
    if not upload or upload.project_id != project.id:
        raise HTTPException(status_code=404, detail="Không tìm thấy bản preview file nguồn tương ứng.")

    meta = json.loads(upload.preview_meta_json or "{}")
    tp_rows = meta.get("topic_pillars") or []
    kw_rows = meta.get("content_items") or []

    if meta.get("validation_errors"):
        raise HTTPException(status_code=422, detail={"message": "F0 chưa đạt; sửa dữ liệu nguồn trước khi lưu.", "errors": meta["validation_errors"]})

    # Persist taxonomy tables cleanly for this project
    db.query(TaxonomyPillar).filter(TaxonomyPillar.project_id == project.id).delete()
    db.query(TopicPillar).filter(TopicPillar.project_id == project.id).delete()
    db.query(ContentCode).filter(ContentCode.project_id == project.id).delete()

    pillar_cache: dict[str, TaxonomyPillar] = {}
    for t in tp_rows:
        p_name = t.get("pillar") or "General Pillar"
        if p_name not in pillar_cache:
            tp_parent = TaxonomyPillar(
                project_id=project.id,
                name=p_name,
                source_file=upload.filename,
                source_sheet=t.get("source_sheet", ""),
                source_row=t.get("source_row"),
            )
            db.add(tp_parent)
            db.flush()
            pillar_cache[p_name] = tp_parent

        db.add(
            TopicPillar(
                project_id=project.id,
                taxonomy_pillar_id=pillar_cache[p_name].id,
                code=t.get("topic_pillar_code", ""),
                name=t.get("topic_pillar_name", ""),
                pillar_name=p_name,
                topic_type=t.get("topic_type", ""),
                split_axis=t.get("split_axis", ""),
                main_topic=t.get("main_topic", ""),
                notes=t.get("notes", ""),
                legacy_code=t.get("legacy_code", ""),
                source_file=upload.filename,
                source_sheet=t.get("source_sheet", ""),
                source_row=t.get("source_row"),
                raw_json=json.dumps(t, ensure_ascii=False),
            )
        )

    for item in kw_rows:
        db.add(
            ContentCode(
                project_id=project.id,
                topic_pillar_code=item.get("topic_pillar_code", ""),
                code=item.get("content_code", ""),
                title=item.get("content_title", ""),
                source_file=upload.filename,
                source_sheet=item.get("source_sheet", ""),
                source_row=item.get("source_row"),
            )
        )

    # Update active project from user-confirmed values (NEVER fabricate business_goal/audience)
    project.pillar_name = payload.pillar_name.strip()
    project.topic_pillar_code = payload.selected_topic_pillar_code.strip().upper() or project.topic_pillar_code
    project.topic_pillar_name = payload.topic_pillar_name.strip()
    project.topic_type = payload.topic_type.strip()
    project.split_axis = payload.split_axis.strip()
    project.main_topic = payload.main_topic.strip()
    project.content_code = payload.selected_content_code.strip()
    project.content_title = payload.content_title.strip()
    pk = payload.primary_keyword.strip()
    if pk:
        if not project.primary_keyword_original:
            project.primary_keyword_original = pk
        project.primary_keyword_current = pk
    cleaned_sec = [k.strip() for k in payload.secondary_keywords if k.strip()]
    project.secondary_keywords_json = json.dumps(cleaned_sec, ensure_ascii=False)
    project.business_goal = payload.business_goal.strip()
    project.target_audience = payload.target_audience.strip()
    project.market = payload.market.strip() or "VN"
    project.language = payload.language.strip() or "vi"
    project.soft_article_min = payload.soft_article_min
    project.soft_article_max = max(payload.soft_article_min, payload.soft_article_max)
    project.provenance_json = json.dumps(
        {
            "source_file": upload.filename,
            "upload_id": upload.id,
            "sha256": upload.sha256,
            "topic_pillar_sheet": meta.get("topic_pillar_sheet", ""),
            "topic_pillar_header_row": meta.get("topic_pillar_header_row"),
            "keywords_sheet": meta.get("keywords_sheet", ""),
            "keywords_header_row": meta.get("keywords_header_row"),
        },
        ensure_ascii=False,
    )
    project.version += 1
    upload.status = "CONFIRMED"

    # Save source keywords with full provenance
    db.query(SourceKeyword).filter(SourceKeyword.project_id == project.id).delete()
    tp_code = project.topic_pillar_code or project.code
    c_code = project.content_code or f"{tp_code}-01"
    ref = f"CONTENT:{c_code}" if project.content_code else f"TOPIC:{tp_code}"

    source_meta = {normalize_text(r["keyword"]): {**r, "content_title": item.get("content_title", "")} for item in kw_rows for r in item.get("keyword_rows", [])}
    def keyword_metadata(keyword):
        record = source_meta.get(normalize_text(keyword), {})
        return {key: record.get(key, "") for key in ("funnel_stage", "title_match_check", "content_title", "subtopic", "planner_volume")}

    if pk:
        db.add(
            SourceKeyword(
                project_id=project.id,
                topic_pillar_code=tp_code,
                content_code=c_code,
                keyword=pk,
                **keyword_metadata(pk),
                keyword_normalized=normalize_text(pk),
                role="PRIMARY",
                is_original=True,
                source_ref=ref,
                source_file=upload.filename,
                source_sheet=meta.get("keywords_sheet", ""),
            )
        )
    for sk in cleaned_sec:
        db.add(
            SourceKeyword(
                project_id=project.id,
                topic_pillar_code=tp_code,
                content_code=c_code,
                keyword=sk,
                **keyword_metadata(sk),
                keyword_normalized=normalize_text(sk),
                role="SECONDARY",
                is_original=True,
                source_ref=ref,
                source_file=upload.filename,
                source_sheet=meta.get("keywords_sheet", ""),
            )
        )

    if payload.source_scope == "PILLAR":
        db.flush()
        db.query(SourceKeyword).filter_by(project_id=project.id).delete()
        for item in kw_rows:
            if item.get("topic_pillar_code") != tp_code:
                continue
            records = item.get("keyword_rows") or [{"keyword": item["primary_keyword"], "role": "PRIMARY"}] + [{"keyword": k, "role": "SECONDARY"} for k in item.get("secondary_keywords", [])]
            for record in records:
                db.add(SourceKeyword(project_id=project.id, topic_pillar_code=tp_code, content_code=item["content_code"], keyword=record["keyword"], keyword_normalized=normalize_text(record["keyword"]), role=record["role"], source_ref=f"CONTENT:{item['content_code']}", source_file=upload.filename, source_sheet=item.get("source_sheet", ""), source_row=record.get("source_row"), **keyword_metadata(record["keyword"])))
        project.content_code = ""
        project.content_title = ""

    db.add(
        ProjectSnapshot(
            project_id=project.id,
            version=project.version,
            reason=f"Xác nhận nhập từ file {upload.filename}",
            payload_json=json.dumps(
                {
                    "topic_pillar_code": project.topic_pillar_code,
                    "content_code": project.content_code,
                    "primary_keyword_original": project.primary_keyword_original,
                    "secondary_keywords": cleaned_sec,
                    "business_goal": project.business_goal,
                    "target_audience": project.target_audience,
                },
                ensure_ascii=False,
            ),
        )
    )
    db.add(
        ProjectEvent(
            project_id=project.id,
            level="SUCCESS",
            event_type="TOPIC_SOURCE_CONFIRMED",
            message=f"Đã xác nhận dữ liệu nguồn từ '{upload.filename}' vào SQLite (v{project.version}).",
        )
    )
    db.commit()
    db.refresh(project)

    return {
        "saved": True,
        "version": project.version,
        "navigation_eligible": bool(project.primary_keyword_original),
        "next_step_href": "/steps/02-demand-map",
        "message": f"Đã lưu nguồn chủ đề từ {upload.filename} vào SQLite (v{project.version}).",
        "project": serialize_project(db, project, include_workflow=True),
    }
