from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.ai.errors import AIProviderError
from app.ai.gateway import gateway
from app.ai.prompts import CRITIC_POST_SYSTEM_PROMPT, build_critic_user_prompt
from app.config import ensure_data_dirs, settings
from app.db import get_db
from app.domain.quality_gates import evaluate_all_gates
from app.domain.semrush_parser import (
    parse_semrush_rows,
    read_tabular_file,
    suggest_column_mapping,
)
from app.domain.workflow import SEMRUSH_REPORT_GUIDES, refresh_workflow_state
from app.models import (
    Critique,
    DemandGroup,
    EvidenceRow,
    FileUpload,
    KeywordEvidenceLink,
    Project,
    ProjectEvent,
    ResearchBatch,
    ResearchRequest,
    SourceKeyword,
)
from app.schemas import (
    CriticRunRequest,
    FollowupApproveRequest,
    ImportConfirmRequest,
    ResearchRequestBatchCreate,
)

router = APIRouter(prefix="/projects/{project_id}", tags=["research-evidence"])

VALID_REPORT_TYPES = {"KEYWORD_OVERVIEW", "RELATED", "QUESTIONS", "ORGANIC_RESULTS"}


def _serialize_request(r: ResearchRequest) -> dict[str, Any]:
    return {
        "id": r.id,
        "project_id": r.project_id,
        "demand_group_id": r.demand_group_id,
        "seed_keyword": r.seed_keyword,
        "report_type": r.report_type,
        "market": r.market,
        "purpose": r.purpose,
        "expected_columns": json.loads(r.expected_columns_json or "[]"),
        "semrush_steps": json.loads(r.semrush_steps_json or "[]"),
        "research_cycle": r.research_cycle,
        "origin": r.origin,
        "status": r.status,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    }


@router.get("/research-requests")
def list_research_requests(project_id: str, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Không tìm thấy dự án.")
    reqs = (
        db.query(ResearchRequest)
        .filter(ResearchRequest.project_id == project_id)
        .order_by(ResearchRequest.created_at.desc())
        .all()
    )
    return {
        "research_requests": [_serialize_request(r) for r in reqs],
        "manual_only_notice": "Hệ thống KHÔNG yêu cầu mật khẩu, token, API hay MCP Semrush. Bạn thao tác trực tiếp trên giao diện Semrush và tải CSV/XLSX lên Bước 04.",
        "workflow": refresh_workflow_state(db, project),
    }


@router.post("/research-requests", status_code=201)
def create_research_requests(
    project_id: str,
    payload: ResearchRequestBatchCreate,
    db: Session = Depends(get_db),
):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Không tìm thấy dự án.")
    if not payload.items:
        raise HTTPException(status_code=400, detail="Cần ít nhất 1 yêu cầu Semrush.")

    created: list[ResearchRequest] = []
    for item in payload.items:
        rt = item.report_type.upper().strip()
        if rt not in VALID_REPORT_TYPES:
            raise HTTPException(status_code=400, detail=f"Loại báo cáo Semrush không hợp lệ: {rt}")
        guide = SEMRUSH_REPORT_GUIDES[rt]
        req = ResearchRequest(
            project_id=project.id,
            demand_group_id=item.demand_group_id,
            seed_keyword=item.seed_keyword.strip(),
            report_type=rt,
            market=(item.market or project.market or "VN").upper(),
            purpose=item.purpose.strip() or f"Lấy dữ liệu {rt} trên Semrush cho '{item.seed_keyword.strip()}'.",
            expected_columns_json=json.dumps(guide["columns"], ensure_ascii=False),
            semrush_steps_json=json.dumps(guide["steps"], ensure_ascii=False),
            research_cycle=project.research_cycle,
            origin=item.origin.upper(),
            status="WAITING_USER",
        )
        db.add(req)
        created.append(req)

    db.add(
        ProjectEvent(
            project_id=project.id,
            level="SUCCESS",
            event_type="RESEARCH_REQUESTS_CREATED",
            message=f"Đã tạo {len(created)} phiếu Yêu cầu Semrush thủ công (chu kỳ {project.research_cycle}).",
        )
    )
    db.commit()
    for r in created:
        db.refresh(r)

    return {
        "saved": True,
        "navigation_eligible": True,
        "next_step_href": "/steps/04-upload",
        "research_requests": [_serialize_request(r) for r in created],
        "workflow": refresh_workflow_state(db, project),
    }


@router.post("/imports/preview")
async def preview_semrush_import(
    project_id: str,
    file: UploadFile = File(...),
    research_request_id: str | None = Form(default=None),
    report_type: str = Form(default="KEYWORD_OVERVIEW"),
    locale: str = Form(default="en-US"),
    sheet_name: str | None = Form(default=None),
    db: Session = Depends(get_db),
):
    """
    Step 04 preview ONLY:
    - Detects sheet, encoding, delimiter, headers, sample rows, suggested column mapping.
    - Does NOT write research evidence or mark business step complete!
    """
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Không tìm thấy dự án.")

    req: ResearchRequest | None = None
    if research_request_id:
        req = db.get(ResearchRequest, research_request_id)
        if not req or req.project_id != project.id:
            raise HTTPException(status_code=404, detail="Không tìm thấy phiếu Yêu cầu Semrush đã chọn.")
        report_type = req.report_type

    rt = report_type.upper().strip()
    if rt not in VALID_REPORT_TYPES:
        raise HTTPException(status_code=400, detail=f"Loại báo cáo không hợp lệ: {rt}")

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="File tải lên rỗng.")

    filename = file.filename or "semrush_export.csv"
    try:
        headers, data_rows, meta = read_tabular_file(raw, filename, sheet_name=sheet_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    ensure_data_dirs()
    sha = hashlib.sha256(raw).hexdigest()
    safe_name = f"{project.id}_semrush_{sha[:10]}_{Path(filename).name}"
    stored = settings.uploads_dir / safe_name
    stored.write_bytes(raw)

    suggested = suggest_column_mapping(headers, rt)

    upload = FileUpload(
        project_id=project.id,
        research_request_id=req.id if req else None,
        purpose="SEMRUSH_IMPORT",
        filename=filename,
        stored_path=str(stored),
        sha256=sha,
        size_bytes=len(raw),
        file_format=meta["file_format"],
        sheet_name=meta["sheet_name"],
        encoding=meta["encoding"],
        delimiter=meta["delimiter"],
        locale=locale,
        row_count_total=len(data_rows),
        status="PREVIEWED",
        preview_meta_json=json.dumps({"headers": headers, "sheets": meta["sheets"]}, ensure_ascii=False),
    )
    db.add(upload)
    if req:
        req.status = "MAPPING_REQUIRED"
    db.commit()
    db.refresh(upload)

    sample_rows = [
        {headers[i]: (row[i] if i < len(row) else None) for i in range(len(headers))}
        for row in data_rows[:15]
    ]

    return {
        "upload_id": upload.id,
        "saved_to_research": False,  # Preview does NOT complete the import!
        "navigation_eligible": False,
        "filename": filename,
        "sha256": sha,
        "report_type": rt,
        "file_format": meta["file_format"],
        "sheets": meta["sheets"],
        "sheet_name": meta["sheet_name"],
        "encoding": meta["encoding"],
        "delimiter": meta["delimiter"],
        "locale": locale,
        "total_rows": len(data_rows),
        "max_supported_rows": settings.max_upload_rows,
        "headers": headers,
        "suggested_mapping": suggested,
        "sample_rows": sample_rows,
        "notice": (
            f"Đã đọc xem trước 15/{len(data_rows):,} dòng (khi bấm Xác nhận import, backend sẽ xử lý TOÀN BỘ {len(data_rows):,} dòng "
            f"trong giới hạn {settings.max_upload_rows:,} dòng). File chưa được ghi vào dữ liệu nghiên cứu."
        ),
    }


@router.post("/imports/confirm")
def confirm_semrush_import(
    project_id: str,
    payload: ImportConfirmRequest,
    db: Session = Depends(get_db),
):
    """
    Confirm Semrush import:
    - Processes ALL rows in stored file (not just preview rows).
    - Preserves raw rows + normalized rows + warnings + hash + source timestamp in SQLite.
    - Status is strictly PROCESS_COMPLETED, NEVER QUALITY_APPROVED or READY_FOR_BRIEF!
    """
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Không tìm thấy dự án.")

    upload = db.get(FileUpload, payload.upload_id)
    if not upload or upload.project_id != project.id:
        raise HTTPException(status_code=404, detail="Không tìm thấy file preview để xác nhận.")

    raw_path = Path(upload.stored_path)
    if not raw_path.exists():
        raise HTTPException(status_code=404, detail="File nguồn tạm đã bị xóa khỏi đĩa, vui lòng tải lại.")

    rt = payload.report_type.upper().strip()
    if rt not in VALID_REPORT_TYPES:
        raise HTTPException(status_code=400, detail=f"Loại báo cáo không hợp lệ: {rt}")

    try:
        headers, data_rows, meta = read_tabular_file(
            raw_path.read_bytes(),
            upload.filename,
            sheet_name=payload.sheet_name or upload.sheet_name,
        )
        parsed = parse_semrush_rows(
            headers,
            data_rows,
            report_type=rt,
            column_mapping=payload.column_mapping,
            locale=payload.locale,
            market=payload.market.upper(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    req = db.get(ResearchRequest, payload.research_request_id) if payload.research_request_id else None

    batch = ResearchBatch(
        project_id=project.id,
        research_request_id=req.id if req else upload.research_request_id,
        file_upload_id=upload.id,
        report_type=rt,
        market=payload.market.upper(),
        locale=payload.locale,
        column_mapping_json=json.dumps(payload.column_mapping, ensure_ascii=False),
        total_raw_rows=parsed.total_raw_rows,
        total_normalized_rows=parsed.total_normalized_rows,
        duplicate_rows_detected=parsed.duplicate_rows_detected,
        warnings_json=json.dumps(parsed.warnings, ensure_ascii=False),
        status="PROCESS_COMPLETED",  # Strictly technical completion, NEVER QUALITY_APPROVED!
    )
    db.add(batch)
    db.flush()

    source_kw_map = {
        sk.keyword_normalized: sk.id
        for sk in db.query(SourceKeyword).filter(SourceKeyword.project_id == project.id).all()
    }

    evidence_objs: list[EvidenceRow] = []
    for row in parsed.rows:
        ev = EvidenceRow(
            project_id=project.id,
            batch_id=batch.id,
            row_type=row["row_type"],
            source_row_number=row["source_row_number"],
            keyword=row["keyword"],
            keyword_normalized=row["keyword_normalized"],
            volume=row["volume"],
            kd=row["kd"],
            intent=row["intent"],
            cpc=row["cpc"],
            serp_features=row["serp_features"],
            organic_url=row["organic_url"],
            organic_position=row["organic_position"],
            organic_title=row["organic_title"],
            organic_page_type=row["organic_page_type"],
            market=row["market"],
            is_duplicate=row["is_duplicate"],
            raw_row_json=json.dumps(row["raw_row"], ensure_ascii=False, default=str),
            warnings_json=json.dumps(row["row_warnings"], ensure_ascii=False),
        )
        db.add(ev)
        evidence_objs.append(ev)

    db.flush()

    for ev in evidence_objs:
        if not ev.is_duplicate and ev.keyword_normalized in source_kw_map:
            db.add(
                KeywordEvidenceLink(
                    project_id=project.id,
                    source_keyword_id=source_kw_map[ev.keyword_normalized],
                    evidence_row_id=ev.id,
                    keyword_normalized=ev.keyword_normalized,
                    match_type="EXACT",
                )
            )

    upload.status = "CONFIRMED"
    upload.locale = payload.locale
    if req:
        req.status = "IMPORTED"

    db.add(
        ProjectEvent(
            project_id=project.id,
            level="SUCCESS",
            event_type="SEMRUSH_BATCH_IMPORTED",
            message=(
                f"Đã xác nhận import batch {batch.id} ({rt}): "
                f"{parsed.total_raw_rows} dòng thô → {parsed.total_normalized_rows} dòng chuẩn hóa "
                f"(phát hiện {parsed.duplicate_rows_detected} dòng trùng, không cộng dồn Volume)."
            ),
            details_json=json.dumps({"batch_id": batch.id, "warnings": parsed.warnings}, ensure_ascii=False),
        )
    )
    db.commit()

    return {
        "saved": True,
        "batch_id": batch.id,
        "status": "PROCESS_COMPLETED",
        "quality_approved": False,  # Explicit invariant: upload != SEO approved
        "navigation_eligible": True,
        "next_step_href": "/steps/05-evidence",
        "total_raw_rows": parsed.total_raw_rows,
        "total_normalized_rows": parsed.total_normalized_rows,
        "duplicate_rows_detected": parsed.duplicate_rows_detected,
        "warnings": parsed.warnings,
        "workflow": refresh_workflow_state(db, project),
    }


@router.get("/evidence")
def get_project_evidence(
    project_id: str,
    limit: int = 200,
    row_type: str | None = None,
    db: Session = Depends(get_db),
):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Không tìm thấy dự án.")

    batches = (
        db.query(ResearchBatch)
        .filter(ResearchBatch.project_id == project_id)
        .order_by(ResearchBatch.created_at.desc())
        .all()
    )
    q = db.query(EvidenceRow).filter(EvidenceRow.project_id == project_id)
    if row_type:
        q = q.filter(EvidenceRow.row_type == row_type.upper())
    total_rows = q.count()
    rows = q.order_by(EvidenceRow.batch_id.desc(), EvidenceRow.source_row_number.asc()).limit(min(limit, 1000)).all()
    critiques = (
        db.query(Critique)
        .filter(Critique.project_id == project_id, Critique.stage == "POST_SEMRUSH")
        .order_by(Critique.created_at.desc())
        .all()
    )
    gates = evaluate_all_gates(db, project)

    return {
        "batches": [
            {
                "id": b.id,
                "report_type": b.report_type,
                "market": b.market,
                "locale": b.locale,
                "total_raw_rows": b.total_raw_rows,
                "total_normalized_rows": b.total_normalized_rows,
                "duplicate_rows_detected": b.duplicate_rows_detected,
                "warnings": json.loads(b.warnings_json or "[]"),
                "status": b.status,
                "source_timestamp": b.source_timestamp.isoformat() if b.source_timestamp else None,
            }
            for b in batches
        ],
        "total_evidence_rows": total_rows,
        "rows": [
            {
                "id": r.id,
                "batch_id": r.batch_id,
                "row_type": r.row_type,
                "source_row_number": r.source_row_number,
                "keyword": r.keyword,
                "volume": r.volume,
                "kd": r.kd,
                "intent": r.intent,
                "cpc": r.cpc,
                "serp_features": r.serp_features,
                "organic_url": r.organic_url,
                "organic_position": r.organic_position,
                "organic_title": r.organic_title,
                "organic_page_type": r.organic_page_type,
                "market": r.market,
                "is_duplicate": r.is_duplicate,
                "warnings": json.loads(r.warnings_json or "[]"),
            }
            for r in rows
        ],
        "post_critiques": [
            {
                "id": c.id,
                "research_cycle": c.research_cycle,
                "round_number": c.round_number,
                "supporting_evidence": json.loads(c.supporting_evidence_json or "[]"),
                "counterarguments": json.loads(c.counterarguments_json or "[]"),
                "missing_data": json.loads(c.missing_data_json or "[]"),
                "changes_from_evidence": json.loads(c.changes_from_evidence_json or "[]"),
                "followup_requests": json.loads(c.followup_requests_json or "[]"),
                "next_action": c.next_action,
                "decision_status": c.decision_status,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in critiques
        ],
        "research_cycle": project.research_cycle,
        "max_critique_rounds_per_cycle": settings.max_critique_rounds_per_cycle,
        "quality_gates": gates["gates"],
        "summary": gates["summary"],
    }


@router.post("/evidence/validate")
def validate_evidence(project_id: str, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Không tìm thấy dự án.")

    gates = evaluate_all_gates(db, project)
    wf = refresh_workflow_state(db, project)
    return {
        "ok": True,
        "quality_gates": gates["gates"],
        "summary": gates["summary"],
        "workflow": wf,
    }


@router.post("/ai/critic")
def run_ai_critic(project_id: str, payload: CriticRunRequest, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Không tìm thấy dự án.")

    stage = payload.stage.upper().strip()
    if stage not in {"PRE_SEMRUSH", "POST_SEMRUSH"}:
        raise HTTPException(status_code=400, detail="Stage phải là PRE_SEMRUSH hoặc POST_SEMRUSH.")

    # Enforce max 2 critique rounds per research cycle to prevent infinite loops (Section 5.6)
    existing_rounds = (
        db.query(Critique)
        .filter(
            Critique.project_id == project.id,
            Critique.stage == stage,
            Critique.research_cycle == project.research_cycle,
        )
        .count()
    )
    if existing_rounds >= settings.max_critique_rounds_per_cycle:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "CRITIQUE_ROUND_LIMIT_REACHED",
                "reason": f"Đã đạt giới hạn tối đa {settings.max_critique_rounds_per_cycle} lượt AI Critic trong chu kỳ nghiên cứu #{project.research_cycle}.",
                "impact": "Hệ thống dừng tự động phản biện để tránh vòng lặp vô hạn.",
                "solution": "Upload thêm file bằng chứng Semrush mới và bấm 'Mở chu kỳ nghiên cứu mới', hoặc chuyển sang Bước 06 lập kế hoạch.",
                "next_action": "Mở chu kỳ nghiên cứu mới sau khi bổ sung evidence hoặc chuyển sang Bước 06.",
                "cta_label": "Mở Bước 06",
                "cta_href": "/steps/06-mapping",
            },
        )

    gates = evaluate_all_gates(db, project)
    summary = gates["summary"]
    dgs = db.query(DemandGroup).filter(DemandGroup.project_id == project.id).all()

    critic_ctx = {
        "task": "CRITIC_POST" if stage == "POST_SEMRUSH" else "CRITIC_PRE",
        "project_code": project.code,
        "primary_keyword": project.primary_keyword_current or project.primary_keyword_original,
        "business_goal": project.business_goal,
        "demand_groups": [{"name": g.name, "page_type": g.assumed_page_type, "status": g.status} for g in dgs],
        **summary,
        "gates": gates["gates"],
    }

    try:
        res, ai_run = gateway.generate_structured(
            db,
            project_id=project.id,
            role="CRITIC_POST" if stage == "POST_SEMRUSH" else "CRITIC_PRE",
            system_prompt=CRITIC_POST_SYSTEM_PROMPT,
            user_prompt=build_critic_user_prompt(critic_ctx, stage),
            context=critic_ctx,
            research_cycle=project.research_cycle,
        )
    except AIProviderError as exc:
        raise HTTPException(status_code=400, detail=exc.error.to_dict())

    # Guardrail: Critic can NEVER output READY_FOR_BRIEF by itself
    decision = str(res.data.get("decision_status") or "REVIEW_REQUIRED").upper()
    if decision == "READY_FOR_BRIEF":
        decision = "REVIEW_REQUIRED"

    critique = Critique(
        project_id=project.id,
        ai_run_id=ai_run.id,
        stage=stage,
        research_cycle=project.research_cycle,
        round_number=existing_rounds + 1,
        supporting_evidence_json=json.dumps(res.data.get("supporting_evidence") or [], ensure_ascii=False),
        counterarguments_json=json.dumps(res.data.get("counterarguments") or [], ensure_ascii=False),
        missing_data_json=json.dumps(res.data.get("missing_data") or [], ensure_ascii=False),
        changes_from_evidence_json=json.dumps(res.data.get("changes_from_evidence") or [], ensure_ascii=False),
        followup_requests_json=json.dumps(res.data.get("followup_requests") or [], ensure_ascii=False),
        next_action=str(res.data.get("next_action") or ""),
        decision_status=decision,
    )
    db.add(critique)

    # Record change history on demand groups
    changes = res.data.get("changes_from_evidence") or []
    if changes:
        for dg in dgs:
            hist = json.loads(dg.critique_history_json or "[]")
            hist.append({"stage": f"CRITIC_POST_C{project.research_cycle}_R{existing_rounds + 1}", "note": changes[0]})
            dg.critique_history_json = json.dumps(hist, ensure_ascii=False)

    db.add(
        ProjectEvent(
            project_id=project.id,
            level="INFO",
            event_type="AI_CRITIC_COMPLETED",
            message=f"AI Critic ({res.provider}/{res.actual_model}) hoàn thành lượt {existing_rounds + 1} chu kỳ #{project.research_cycle}.",
        )
    )
    db.commit()
    db.refresh(critique)

    # Popup rule (Section 09): Do NOT auto-navigate when Critic demands follow-up / review!
    nav_eligible = decision == "PROCESS_COMPLETED" and not (res.data.get("followup_requests") or [])
    return {
        "ok": True,
        "saved": True,
        "provider": res.provider,
        "actual_model": res.actual_model,
        "fallback_events": [e.__dict__ for e in res.fallback_events],
        "navigation_eligible": nav_eligible,
        "next_step_href": "/steps/06-mapping",
        "critique": {
            "id": critique.id,
            "research_cycle": critique.research_cycle,
            "round_number": critique.round_number,
            "supporting_evidence": json.loads(critique.supporting_evidence_json),
            "counterarguments": json.loads(critique.counterarguments_json),
            "missing_data": json.loads(critique.missing_data_json),
            "changes_from_evidence": json.loads(critique.changes_from_evidence_json),
            "followup_requests": json.loads(critique.followup_requests_json),
            "next_action": critique.next_action,
            "decision_status": critique.decision_status,
        },
        "workflow": refresh_workflow_state(db, project),
    }


@router.post("/research/followups", status_code=201)
def create_followup_research_requests(
    project_id: str,
    payload: FollowupApproveRequest,
    db: Session = Depends(get_db),
):
    """Turn AI Critic's followup_requests into actionable Semrush ResearchRequests after user approval."""
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Không tìm thấy dự án.")

    items_to_create: list[dict[str, str]] = []
    if payload.critique_id:
        critique = db.get(Critique, payload.critique_id)
        if not critique or critique.project_id != project.id:
            raise HTTPException(status_code=404, detail="Không tìm thấy bản phản biện AI Critic.")
        raw_followups = json.loads(critique.followup_requests_json or "[]")
        for idx, fu in enumerate(raw_followups):
            if payload.selected_indices is None or idx in payload.selected_indices:
                items_to_create.append(
                    {
                        "seed_keyword": str(fu.get("seed_keyword") or project.primary_keyword_current or project.primary_keyword_original),
                        "report_type": str(fu.get("report_type") or "KEYWORD_OVERVIEW").upper(),
                        "purpose": str(fu.get("purpose") or "Nghiên cứu bổ sung theo đề xuất AI Critic."),
                    }
                )

    for custom in payload.custom_items:
        items_to_create.append(
            {
                "seed_keyword": custom.seed_keyword,
                "report_type": custom.report_type.upper(),
                "purpose": custom.purpose,
            }
        )

    if not items_to_create:
        raise HTTPException(status_code=400, detail="Chưa có yêu cầu nghiên cứu bổ sung nào được chọn.")

    created: list[ResearchRequest] = []
    for item in items_to_create:
        rt = item["report_type"] if item["report_type"] in VALID_REPORT_TYPES else "KEYWORD_OVERVIEW"
        guide = SEMRUSH_REPORT_GUIDES[rt]
        req = ResearchRequest(
            project_id=project.id,
            seed_keyword=item["seed_keyword"].strip(),
            report_type=rt,
            market=project.market or "VN",
            purpose=item["purpose"],
            expected_columns_json=json.dumps(guide["columns"], ensure_ascii=False),
            semrush_steps_json=json.dumps(guide["steps"], ensure_ascii=False),
            research_cycle=project.research_cycle,
            origin="CRITIC_FOLLOWUP",
            status="WAITING_USER",
        )
        db.add(req)
        created.append(req)

    db.add(
        ProjectEvent(
            project_id=project.id,
            level="SUCCESS",
            event_type="FOLLOWUP_REQUESTS_APPROVED",
            message=f"Người dùng đã duyệt tạo {len(created)} phiếu Yêu cầu Semrush bổ sung từ AI Critic.",
        )
    )
    db.commit()
    for r in created:
        db.refresh(r)

    return {
        "saved": True,
        "navigation_eligible": True,
        "next_step_href": "/steps/03-semrush",
        "created_requests": [_serialize_request(r) for r in created],
        "workflow": refresh_workflow_state(db, project),
    }


@router.post("/research/reopen-cycle")
def reopen_research_cycle(project_id: str, db: Session = Depends(get_db)):
    """Explicitly open a new research cycle when fresh Semrush evidence has been uploaded."""
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Không tìm thấy dự án.")
    project.research_cycle += 1
    db.add(
        ProjectEvent(
            project_id=project.id,
            level="INFO",
            event_type="RESEARCH_CYCLE_REOPENED",
            message=f"Đã mở chu kỳ nghiên cứu mới #{project.research_cycle} (tối đa {settings.max_critique_rounds_per_cycle} lượt Critic/chu kỳ).",
        )
    )
    db.commit()
    return {"ok": True, "research_cycle": project.research_cycle}
