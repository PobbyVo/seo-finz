from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.ai.errors import AIProviderError
from app.ai.gateway import gateway
from app.ai.prompts import (
    ANALYST_SYSTEM_PROMPT,
    CRITIC_PRE_SYSTEM_PROMPT,
    build_analyst_user_prompt,
    build_critic_user_prompt,
)
from app.db import get_db
from app.domain.quality_gates import valid_source_refs_for_project
from app.domain.taxonomy_parser import normalize_text
from app.domain.workflow import refresh_workflow_state
from app.models import (
    Approval,
    Critique,
    DemandGroup,
    KeywordCandidate,
    Project,
    ProjectEvent,
)
from app.schemas import CandidatePromoteRequest

router = APIRouter(prefix="/projects/{project_id}", tags=["demand-map"])


def _serialize_demand_group(dg: DemandGroup) -> dict[str, Any]:
    return {
        "id": dg.id,
        "name": dg.name,
        "user_need": dg.user_need,
        "coverage_type": dg.coverage_type,
        "assumed_page_type": dg.assumed_page_type,
        "assumed_intent": dg.assumed_intent,
        "seed_keywords": json.loads(dg.seed_keywords_json or "[]"),
        "related_keywords": json.loads(dg.related_keywords_json or "[]"),
        "supporting_evidence": json.loads(dg.supporting_evidence_json or "[]"),
        "source_refs": json.loads(dg.source_refs_json or "[]"),
        "strongest_counterargument": dg.strongest_counterargument,
        "missing_data": json.loads(dg.missing_data_json or "[]"),
        "next_action": dg.next_action,
        "recommended_semrush_report": dg.recommended_semrush_report,
        "boundary_note": dg.boundary_note,
        "business_relevance_note": dg.business_relevance_note,
        "critique_history": json.loads(dg.critique_history_json or "[]"),
        "status": dg.status,
        "is_promoted": dg.is_promoted,
        "ai_run_id": dg.ai_run_id,
    }


@router.get("/demand-map")
def get_demand_map(project_id: str, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Không tìm thấy dự án.")

    groups = db.query(DemandGroup).filter(DemandGroup.project_id == project_id).order_by(DemandGroup.created_at.asc()).all()
    candidates = db.query(KeywordCandidate).filter(KeywordCandidate.project_id == project_id).all()
    critiques = (
        db.query(Critique)
        .filter(Critique.project_id == project_id, Critique.stage == "PRE_SEMRUSH")
        .order_by(Critique.created_at.desc())
        .all()
    )
    return {
        "demand_groups": [_serialize_demand_group(g) for g in groups],
        "candidates": [
            {
                "id": c.id,
                "keyword": c.keyword,
                "candidate_type": c.candidate_type,
                "assumed_page_type": c.assumed_page_type,
                "source_refs": json.loads(c.source_refs_json or "[]"),
                "source_ref_valid": c.source_ref_valid,
                "rationale": c.rationale,
                "status": c.status,
            }
            for c in candidates
        ],
        "pre_critiques": [
            {
                "id": c.id,
                "round_number": c.round_number,
                "supporting_evidence": json.loads(c.supporting_evidence_json or "[]"),
                "counterarguments": json.loads(c.counterarguments_json or "[]"),
                "missing_data": json.loads(c.missing_data_json or "[]"),
                "followup_requests": json.loads(c.followup_requests_json or "[]"),
                "next_action": c.next_action,
                "decision_status": c.decision_status,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in critiques
        ],
        "workflow": refresh_workflow_state(db, project),
    }


@router.post("/analyze-topic")
def analyze_topic(project_id: str, db: Session = Depends(get_db)):
    """
    Step 02: Run AI Topic Analyst + Pre-Semrush SEO Critic reading from SQLite.
    - Verifies every AI source_ref against real SQLite taxonomy; unverified refs become UNCERTAIN.
    - Never fabricates Volume/KD/SERP or modifies original primary keyword.
    """
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Không tìm thấy dự án.")

    if not (project.primary_keyword_original or project.primary_keyword_current):
        raise HTTPException(
            status_code=400,
            detail={
                "code": "TOPIC_NOT_CONFIGURED",
                "reason": "Dự án chưa có Keyword chính nguồn trong SQLite.",
                "impact": "AI Topic Analyst không có dữ liệu đầu vào hợp lệ.",
                "solution": "Hoàn thành Bước 01 (nhập Topic Pillar & Keyword chính) trước khi chạy AI.",
                "next_action": "Mở Bước 01 — Thiết lập chủ đề.",
                "cta_label": "Mở Bước 01",
                "cta_href": "/steps/01-topic",
            },
        )

    valid_refs = sorted(valid_source_refs_for_project(db, project))
    secondary_kws = json.loads(project.secondary_keywords_json or "[]")
    analyst_ctx = {
        "task": "ANALYST",
        "project_code": project.code,
        "project_name": project.name,
        "pillar_name": project.pillar_name,
        "topic_pillar_code": project.topic_pillar_code,
        "topic_pillar_name": project.topic_pillar_name,
        "topic_type": project.topic_type,
        "split_axis": project.split_axis,
        "main_topic": project.main_topic,
        "content_code": project.content_code,
        "content_title": project.content_title,
        "primary_keyword": project.primary_keyword_current or project.primary_keyword_original,
        "secondary_keywords": secondary_kws,
        "business_goal": project.business_goal,
        "target_audience": project.target_audience,
        "market": project.market,
        "language": project.language,
        "valid_source_refs": valid_refs,
    }

    try:
        analyst_res, analyst_run = gateway.generate_structured(
            db,
            project_id=project.id,
            role="ANALYST",
            system_prompt=ANALYST_SYSTEM_PROMPT,
            user_prompt=build_analyst_user_prompt(analyst_ctx),
            context=analyst_ctx,
            research_cycle=project.research_cycle,
            source_refs=valid_refs,
        )
    except AIProviderError as exc:
        raise HTTPException(status_code=400, detail=exc.error.to_dict())

    raw_groups = analyst_res.data.get("demand_groups") or []
    raw_candidates = analyst_res.data.get("proposed_candidates") or []

    # Replace previous un-researched draft demand groups cleanly
    db.query(KeywordCandidate).filter(KeywordCandidate.project_id == project.id).delete()
    db.query(DemandGroup).filter(DemandGroup.project_id == project.id).delete()

    valid_ref_set = set(valid_refs)
    saved_groups: list[DemandGroup] = []

    for g in raw_groups:
        refs = [str(r).strip() for r in (g.get("source_refs") or []) if str(r).strip()]
        all_refs_valid = bool(refs) and all(r in valid_ref_set for r in refs)
        status = str(g.get("status") or "RESEARCH_CANDIDATE")
        if not all_refs_valid:
            # Rule T11: Invalid/unverified AI source_refs MUST be flagged UNCERTAIN!
            status = "UNCERTAIN"

        counter = str(g.get("strongest_counterargument") or "").strip()
        if not counter:
            counter = "Chưa có bằng chứng Semrush và SERP thực tế; giả định cần được phản biện trước khi chốt bài."

        dg = DemandGroup(
            project_id=project.id,
            name=str(g.get("name") or "Nhóm nhu cầu chưa đặt tên")[:250],
            user_need=str(g.get("user_need") or ""),
            coverage_type=str(g.get("coverage_type") or "COVERED").upper(),
            assumed_page_type=str(g.get("assumed_page_type") or "UNKNOWN").upper(),
            assumed_intent=str(g.get("assumed_intent") or "Giả định (chưa kiểm chứng SERP)"),
            seed_keywords_json=json.dumps(g.get("seed_keywords") or [], ensure_ascii=False),
            related_keywords_json=json.dumps(g.get("related_keywords") or [], ensure_ascii=False),
            supporting_evidence_json=json.dumps(g.get("supporting_evidence") or [], ensure_ascii=False),
            source_refs_json=json.dumps(refs, ensure_ascii=False),
            strongest_counterargument=counter,
            missing_data_json=json.dumps(g.get("missing_data") or [], ensure_ascii=False),
            next_action=str(g.get("next_action") or "Tạo phiếu Yêu cầu Semrush để lấy bằng chứng."),
            recommended_semrush_report=str(g.get("recommended_semrush_report") or "KEYWORD_OVERVIEW").upper(),
            boundary_note=str(g.get("boundary_note") or ""),
            business_relevance_note=str(g.get("business_relevance_note") or ""),
            critique_history_json=json.dumps(
                [
                    {
                        "stage": "ANALYST_INITIAL",
                        "note": (
                            "Đối chiếu source_refs hợp lệ với SQLite."
                            if all_refs_valid
                            else f"Cảnh báo E0: source_refs {refs} không khớp nguồn SQLite -> gắn UNCERTAIN."
                        ),
                    }
                ],
                ensure_ascii=False,
            ),
            status=status,
            is_promoted=True,
            ai_run_id=analyst_run.id,
        )
        db.add(dg)
        saved_groups.append(dg)

    for c in raw_candidates:
        kw = str(c.get("keyword") or "").strip()
        if not kw:
            continue
        refs = [str(r).strip() for r in (c.get("source_refs") or []) if str(r).strip()]
        ref_valid = bool(refs) and all(r in valid_ref_set for r in refs)
        db.add(
            KeywordCandidate(
                project_id=project.id,
                keyword=kw,
                keyword_normalized=normalize_text(kw),
                candidate_type=str(c.get("candidate_type") or "SEED_PROPOSAL").upper(),
                assumed_page_type=str(c.get("assumed_page_type") or "UNKNOWN").upper(),
                source_refs_json=json.dumps(refs, ensure_ascii=False),
                source_ref_valid=ref_valid,
                rationale=str(c.get("rationale") or ""),
                status="RESEARCH_CANDIDATE" if ref_valid else "UNCERTAIN",
            )
        )

    db.flush()

    # Run Pre-Semrush Critic automatically right after Analyst
    critic_ctx = {
        "task": "CRITIC_PRE",
        "primary_keyword": project.primary_keyword_current or project.primary_keyword_original,
        "topic_pillar_code": project.topic_pillar_code,
        "business_goal": project.business_goal,
        "demand_groups": [_serialize_demand_group(g) for g in saved_groups],
    }
    critic_res, critic_run = gateway.generate_structured(
        db,
        project_id=project.id,
        role="CRITIC_PRE",
        system_prompt=CRITIC_PRE_SYSTEM_PROMPT,
        user_prompt=build_critic_user_prompt(critic_ctx, "PRE_SEMRUSH"),
        context=critic_ctx,
        research_cycle=project.research_cycle,
        source_refs=valid_refs,
    )
    critique = Critique(
        project_id=project.id,
        ai_run_id=critic_run.id,
        stage="PRE_SEMRUSH",
        research_cycle=project.research_cycle,
        round_number=1,
        supporting_evidence_json=json.dumps(critic_res.data.get("supporting_evidence") or [], ensure_ascii=False),
        counterarguments_json=json.dumps(critic_res.data.get("counterarguments") or [], ensure_ascii=False),
        missing_data_json=json.dumps(critic_res.data.get("missing_data") or [], ensure_ascii=False),
        changes_from_evidence_json=json.dumps(critic_res.data.get("changes_from_evidence") or [], ensure_ascii=False),
        followup_requests_json=json.dumps(critic_res.data.get("followup_requests") or [], ensure_ascii=False),
        next_action=str(critic_res.data.get("next_action") or ""),
        decision_status=str(critic_res.data.get("decision_status") or "WAITING_USER"),
    )
    db.add(critique)

    # Append pre-critic note into each demand group's critique_history
    pre_counters = critic_res.data.get("counterarguments") or []
    if pre_counters:
        for dg in saved_groups:
            hist = json.loads(dg.critique_history_json or "[]")
            hist.append({"stage": "CRITIC_PRE", "note": pre_counters[0]})
            dg.critique_history_json = json.dumps(hist, ensure_ascii=False)

    db.add(
        ProjectEvent(
            project_id=project.id,
            level="SUCCESS",
            event_type="TOPIC_ANALYZED",
            message=(
                f"AI Topic Analyst & Critic ({analyst_res.provider}/{analyst_res.actual_model}) "
                f"đã tạo {len(saved_groups)} nhóm nhu cầu vào SQLite."
            ),
            details_json=json.dumps(
                {
                    "provider": analyst_res.provider,
                    "actual_model": analyst_res.actual_model,
                    "fallback_events": [e.__dict__ for e in analyst_res.fallback_events],
                },
                ensure_ascii=False,
            ),
        )
    )
    db.commit()

    return {
        "ok": True,
        "saved": True,
        "navigation_eligible": True,
        "next_step_href": "/steps/03-semrush",
        "provider": analyst_res.provider,
        "actual_model": analyst_res.actual_model,
        "fallback_events": [e.__dict__ for e in analyst_res.fallback_events],
        "summary": analyst_res.data.get("summary", ""),
        "demand_groups": [_serialize_demand_group(g) for g in saved_groups],
        "recommended_requests": analyst_res.data.get("recommended_requests") or [],
        "pre_critique": {
            "id": critique.id,
            "supporting_evidence": json.loads(critique.supporting_evidence_json),
            "counterarguments": json.loads(critique.counterarguments_json),
            "missing_data": json.loads(critique.missing_data_json),
            "followup_requests": json.loads(critique.followup_requests_json),
            "next_action": critique.next_action,
            "decision_status": critique.decision_status,
        },
        "workflow": refresh_workflow_state(db, project),
    }


@router.post("/demand-map/candidates/{candidate_id}/promote")
def promote_candidate(
    project_id: str,
    candidate_id: str,
    payload: CandidatePromoteRequest,
    db: Session = Depends(get_db),
):
    project = db.get(Project, project_id)
    cand = db.get(KeywordCandidate, candidate_id)
    if not project or not cand or cand.project_id != project.id:
        raise HTTPException(status_code=404, detail="Không tìm thấy ứng viên keyword.")

    if payload.action == "OUT_OF_SCOPE":
        cand.status = "OUT_OF_SCOPE"
        db.commit()
        return {"ok": True, "status": cand.status}

    if payload.action == "REQUEST_APPROVAL" or not cand.source_ref_valid:
        cand.status = "PENDING_APPROVAL"
        db.add(
            Approval(
                project_id=project.id,
                approval_type="NEW_TOPIC_PROPOSAL",
                target_ref=cand.id,
                title=f"Đề xuất mở rộng keyword: {cand.keyword}",
                original_value=project.primary_keyword_original,
                proposed_value=cand.keyword,
                rationale=cand.rationale or "Đưa từ khóa đề xuất mới vào Bản đồ nhu cầu.",
                evidence_json=cand.source_refs_json,
                impact="Mở rộng phạm vi nghiên cứu từ khóa ngoài danh sách gốc.",
                scope="RESEARCH_ONLY",
                status="PENDING",
                version=project.version,
            )
        )
        db.commit()
        return {"ok": True, "status": cand.status, "approval_created": True}

    # PROMOTE into DemandGroup
    dg = DemandGroup(
        project_id=project.id,
        name=f"Nhu cầu mở rộng: {cand.keyword}",
        user_need=cand.rationale or f"Nhu cầu liên quan tới '{cand.keyword}'.",
        coverage_type="GAP",
        assumed_page_type=cand.assumed_page_type,
        assumed_intent="Giả định (chưa kiểm chứng SERP)",
        seed_keywords_json=json.dumps([cand.keyword], ensure_ascii=False),
        related_keywords_json="[]",
        supporting_evidence_json=json.dumps([cand.rationale or "Ứng viên hợp lệ từ taxonomy."], ensure_ascii=False),
        source_refs_json=cand.source_refs_json,
        strongest_counterargument="Cần dữ liệu Semrush để xác nhận đây là nhu cầu độc lập, không trùng chủ đề gốc.",
        missing_data_json=json.dumps(["Volume, KD, Intent từ Semrush."], ensure_ascii=False),
        next_action=f"Tạo phiếu KEYWORD_OVERVIEW trên Semrush cho '{cand.keyword}'.",
        recommended_semrush_report="KEYWORD_OVERVIEW",
        status="RESEARCH_CANDIDATE",
        is_promoted=True,
    )
    db.add(dg)
    cand.status = "PROMOTED"
    db.commit()
    db.refresh(dg)
    return {"ok": True, "demand_group": _serialize_demand_group(dg)}
