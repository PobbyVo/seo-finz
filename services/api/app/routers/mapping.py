from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.domain.mapping_engine import build_keyword_mapping_preview
from app.domain.quality_gates import evaluate_all_gates
from app.domain.workflow import refresh_workflow_state
from app.models import (
    Approval,
    ArticleOpportunity,
    EvidenceRow,
    KeywordMapping,
    Project,
    ProjectEvent,
)
from app.schemas import ApprovalDecisionRequest

router = APIRouter(prefix="/projects/{project_id}", tags=["mapping-approvals"])


@router.get("/opportunities")
def get_opportunities_and_mappings(project_id: str, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Không tìm thấy dự án.")

    mappings = (
        db.query(KeywordMapping)
        .filter(KeywordMapping.project_id == project_id)
        .order_by(KeywordMapping.priority.asc(), KeywordMapping.created_at.asc())
        .all()
    )
    opportunities = (
        db.query(ArticleOpportunity)
        .filter(ArticleOpportunity.project_id == project_id)
        .order_by(ArticleOpportunity.priority.asc())
        .all()
    )
    gates = evaluate_all_gates(db, project)

    article_opps = [o for o in opportunities if o.opportunity_kind == "ARTICLE_OPPORTUNITY"]
    non_article_assets = [o for o in opportunities if o.opportunity_kind == "NON_ARTICLE_ASSET"]
    research_gaps = [o for o in opportunities if o.opportunity_kind == "RESEARCH_GAP"]

    def ser_opp(o: ArticleOpportunity):
        return {
            "id": o.id,
            "keyword_mapping_id": o.keyword_mapping_id,
            "demand_group_name": o.demand_group_name,
            "opportunity_kind": o.opportunity_kind,
            "page_type": o.page_type,
            "counts_toward_article_quota": o.counts_toward_article_quota,
            "title_suggestion": o.title_suggestion,
            "primary_keyword": o.primary_keyword,
            "priority": o.priority,
            "status": o.status,
            "rationale": o.rationale,
            "evidence": json.loads(o.evidence_json or "[]"),
        }

    return {
        "serp_verified": gates["summary"]["serp_verified"],
        "serp_status": gates["summary"]["serp_status"],
        "plan_mode": "VERIFIED_CANDIDATE" if gates["summary"]["serp_verified"] else "DRAFT_SERP_NOT_VERIFIED",
        "article_quota": {
            "soft_min": project.soft_article_min,
            "soft_max": project.soft_article_max,
            "current_articles": len(article_opps),
            "non_article_assets_excluded": len(non_article_assets),
            "research_gaps": len(research_gaps),
        },
        "mappings": [
            {
                "id": m.id,
                "revision": m.revision,
                "primary_keyword": m.primary_keyword,
                "secondary_keywords": json.loads(m.secondary_keywords_json or "[]"),
                "page_type": m.page_type,
                "proposed_url": m.proposed_url,
                "volume": m.volume,
                "kd": m.kd,
                "intent": m.intent,
                "metrics_source": m.metrics_source,
                "priority": m.priority,
                "business_value": m.business_value,
                "effort": m.effort,
                "merge_split_proposal": m.merge_split_proposal,
                "serp_status": m.serp_status,
                "content_status": m.content_status,
                "evidence": json.loads(m.evidence_json or "[]"),
                "is_approved": m.is_approved,
                "approved_at": m.approved_at.isoformat() if m.approved_at else None,
            }
            for m in mappings
        ],
        "article_opportunities": [ser_opp(o) for o in article_opps],
        "non_article_assets": [ser_opp(o) for o in non_article_assets],
        "research_gaps": [ser_opp(o) for o in research_gaps],
        "workflow": refresh_workflow_state(db, project),
    }


@router.post("/mapping/preview")
def generate_mapping_preview(project_id: str, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Không tìm thấy dự án.")

    result = build_keyword_mapping_preview(db, project, create_approvals=True)
    db.add(
        ProjectEvent(
            project_id=project.id,
            level="SUCCESS",
            event_type="KEYWORD_MAPPING_GENERATED",
            message=(
                f"Đã lập Keyword Mapping revision #{result['revision']} "
                f"({result['mappings_count']} dòng, {result['serp_status']}; tạo {result['approvals_created']} mục chờ duyệt)."
            ),
        )
    )
    db.commit()
    wf = refresh_workflow_state(db, project)
    # Popup rule: If pending approvals were created, hold auto-navigation so user reviews approvals!
    return {
        "saved": True,
        "navigation_eligible": result["approvals_created"] == 0,
        "next_step_href": "/approvals" if result["approvals_created"] > 0 else "/steps/07-brief",
        **result,
        "workflow": wf,
    }


@router.get("/approvals")
def list_approvals(project_id: str, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Không tìm thấy dự án.")
    items = (
        db.query(Approval)
        .filter(Approval.project_id == project_id)
        .order_by(Approval.created_at.desc())
        .all()
    )
    return {
        "approvals": [
            {
                "id": a.id,
                "approval_type": a.approval_type,
                "target_ref": a.target_ref,
                "title": a.title,
                "original_value": a.original_value,
                "proposed_value": a.proposed_value,
                "rationale": a.rationale,
                "evidence": json.loads(a.evidence_json or "[]"),
                "impact": a.impact,
                "scope": a.scope,
                "status": a.status,
                "decision_note": a.decision_note,
                "decided_by": a.decided_by,
                "version": a.version,
                "created_at": a.created_at.isoformat() if a.created_at else None,
                "decided_at": a.decided_at.isoformat() if a.decided_at else None,
            }
            for a in items
        ],
        "workflow": refresh_workflow_state(db, project),
    }


@router.post("/approvals/{approval_id}")
def decide_approval(
    project_id: str,
    approval_id: str,
    payload: ApprovalDecisionRequest,
    db: Session = Depends(get_db),
):
    project = db.get(Project, project_id)
    approval = db.get(Approval, approval_id)
    if not project or not approval or approval.project_id != project.id:
        raise HTTPException(status_code=404, detail="Không tìm thấy mục phê duyệt.")

    decision = payload.decision.upper().strip()
    if decision not in {"APPROVED", "REJECTED", "NEED_MORE_EVIDENCE"}:
        raise HTTPException(status_code=400, detail="Quyết định phải là APPROVED, REJECTED hoặc NEED_MORE_EVIDENCE.")

    now = datetime.now(timezone.utc)
    approval.status = decision
    approval.decision_note = payload.decision_note.strip()
    approval.decided_by = payload.decided_by.strip() or "SEO Specialist"
    approval.decided_at = now
    approval.version += 1

    # Apply approved decision cleanly to target entity
    if decision == "APPROVED":
        if approval.approval_type == "PRIMARY_KEYWORD_CHANGE":
            # Only update current keyword; original remains preserved forever for provenance!
            project.primary_keyword_current = approval.proposed_value
        elif approval.scope == "BRIEF_ELIGIBILITY" and approval.target_ref:
            km = db.get(KeywordMapping, approval.target_ref)
            if km and km.project_id == project.id:
                km.is_approved = True
                km.approved_at = now
                has_organic = (
                    db.query(EvidenceRow)
                    .filter(
                        EvidenceRow.project_id == project.id,
                        EvidenceRow.row_type == "ORGANIC_RESULTS",
                        EvidenceRow.is_duplicate == False,  # noqa: E712
                    )
                    .count()
                    > 0
                )
                # Only READY_FOR_BRIEF if SERP verified AND metrics exist!
                km.content_status = "READY_FOR_BRIEF" if (has_organic and km.volume is not None) else "SERP_NOT_VERIFIED"

    db.add(
        ProjectEvent(
            project_id=project.id,
            level="SUCCESS" if decision == "APPROVED" else "WARNING",
            event_type="APPROVAL_DECIDED",
            message=f"[{decision}] {approval.title} (scope: {approval.scope}, bởi {approval.decided_by}).",
            details_json=json.dumps({"approval_id": approval.id, "note": approval.decision_note}, ensure_ascii=False),
        )
    )
    db.commit()

    return {
        "saved": True,
        "approval_id": approval.id,
        "status": approval.status,
        "scope": approval.scope,
        "decided_at": now.isoformat(),
        "workflow": refresh_workflow_state(db, project),
    }
