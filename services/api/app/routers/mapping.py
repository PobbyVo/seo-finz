from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.domain.eligibility_policy import (
    POLICY_VERSION,
    evaluate_mapping_eligibility,
    load_project_policy_context,
)
from app.domain.mapping_engine import build_keyword_mapping_preview
from app.domain.quality_gates import evaluate_all_gates
from app.domain.workflow import refresh_workflow_state
from app.models import (
    Approval,
    ArticleOpportunity,
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
        .filter(KeywordMapping.project_id == project_id, KeywordMapping.is_archived == False)  # noqa: E712
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
    elig_map = gates["mapping_eligibilities"]

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
        "policy_version": POLICY_VERSION,
        "serp_verified": gates["summary"]["serp_verified"],
        "serp_status": gates["summary"]["serp_status"],
        "eligible_official_count": gates["summary"]["eligible_official_count"],
        "plan_mode": (
            "VERIFIED_CANDIDATE"
            if gates["summary"]["serp_status"] in ("SERP_VERIFIED", "TOP_10_VERIFIED")
            else "DRAFT_SERP_NOT_VERIFIED"
        ),
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
                "logical_key": m.logical_key,
                "revision": m.revision,
                "content_fingerprint": m.content_fingerprint,
                "primary_keyword": m.primary_keyword,
                "secondary_keywords": json.loads(m.secondary_keywords_json or "[]"),
                "page_type": m.page_type,
                "proposed_url": m.proposed_url,
                "volume": m.volume,
                "kd": m.kd,
                "intent": m.intent,
                "metrics_source": m.metrics_source,
                "metrics_evidence_id": m.metrics_evidence_id,
                "priority": m.priority,
                "business_value": m.business_value,
                "effort": m.effort,
                "merge_split_proposal": m.merge_split_proposal,
                "serp_status": elig_map[m.id]["serp_tier"],
                "content_status": elig_map[m.id]["recommended_content_status"],
                "evidence": json.loads(m.evidence_json or "[]"),
                "is_approved": elig_map[m.id]["approval_state"] == "APPROVED_CURRENT",
                "approved_revision": m.approved_revision,
                "approved_fingerprint": m.approved_fingerprint,
                "approved_at": m.approved_at.isoformat() if m.approved_at else None,
                "eligibility": elig_map[m.id],
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
                f"Đã lập Keyword Mapping rev #{result['revision']} "
                f"({result['mappings_count']} dòng, {result['serp_status']}; "
                f"tạo {result['approvals_created']} mục chờ duyệt, "
                f"{result['approvals_superseded']} mục cũ hết hiệu lực, "
                f"{result['briefs_marked_stale']} brief cũ chuyển stale)."
            ),
        )
    )
    db.commit()
    wf = refresh_workflow_state(db, project)
    pending_count = wf["counts"]["pending_approvals"]
    return {
        "saved": True,
        "navigation_eligible": result["approvals_created"] == 0 and pending_count == 0,
        "next_step_href": "/approvals" if pending_count > 0 else "/steps/07-brief",
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
                "target_revision": a.target_revision,
                "target_fingerprint": a.target_fingerprint,
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
    """
    Deterministic, revision-bound human approval endpoint:
    - Enforces project ownership (rejects cross-project approval IDs).
    - Rejects non-PENDING / replayed / superseded approvals with HTTP 409 Conflict.
    - Verifies exact KeywordMapping revision & content_fingerprint before approving.
    - RESEARCH_ONLY approvals NEVER unlock BRIEF_ELIGIBILITY.
    """
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Không tìm thấy dự án.")

    approval = db.get(Approval, approval_id)
    if not approval or approval.project_id != project.id:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "APPROVAL_NOT_FOUND",
                "reason": "Không tìm thấy mục phê duyệt này trong dự án hiện tại.",
                "impact": "Không thể ghi nhận quyết định cho mục thuộc dự án khác hoặc không tồn tại.",
                "solution": "Tải lại danh sách Chờ phê duyệt của đúng dự án đang chọn.",
                "next_action": "Mở màn hình Chờ phê duyệt.",
                "cta_label": "Mở Chờ phê duyệt",
                "cta_href": "/approvals",
            },
        )

    decision = payload.decision.upper().strip()
    if decision not in {"APPROVED", "REJECTED", "NEED_MORE_EVIDENCE"}:
        raise HTTPException(status_code=400, detail="Quyết định phải là APPROVED, REJECTED hoặc NEED_MORE_EVIDENCE.")

    if approval.status != "PENDING":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "APPROVAL_ALREADY_FINALIZED" if approval.status != "SUPERSEDED" else "APPROVAL_SUPERSEDED",
                "reason": f"Yêu cầu phê duyệt '{approval.title}' không còn ở trạng thái PENDING (hiện tại: {approval.status}).",
                "impact": "Hệ thống từ chối ghi đè hoặc dùng lại quyết định cũ để bảo vệ lịch sử kiểm toán.",
                "solution": "Kiểm tra danh sách Chờ phê duyệt để thao tác trên phiên bản PENDING mới nhất.",
                "next_action": "Làm mới danh sách Chờ phê duyệt.",
                "cta_label": "Xem Chờ phê duyệt",
                "cta_href": "/approvals",
            },
        )

    # Validate target mapping exact revision & fingerprint for BRIEF_ELIGIBILITY mapping approvals
    target_km: KeywordMapping | None = None
    if approval.scope == "BRIEF_ELIGIBILITY" and approval.approval_type != "PRIMARY_KEYWORD_CHANGE" and approval.target_ref:
        target_km = db.get(KeywordMapping, approval.target_ref)
        if not target_km or target_km.project_id != project.id or target_km.is_archived:
            approval.status = "SUPERSEDED"
            approval.decision_note = "Mapping mục tiêu đã bị lưu trữ hoặc không còn tồn tại."
            db.commit()
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "APPROVAL_TARGET_OBSOLETE",
                    "reason": "Keyword Mapping gắn với yêu cầu phê duyệt này không còn hoạt động hoặc đã thay thế.",
                    "impact": "Không thể áp dụng phê duyệt cũ cho dữ liệu không còn khớp.",
                    "solution": "Vào Bước 06 lập lại Keyword Mapping và duyệt phiên bản hiện hành.",
                    "next_action": "Mở Bước 06 để kiểm tra phiên bản Mapping mới nhất.",
                    "cta_label": "Mở Bước 06",
                    "cta_href": "/steps/06-mapping",
                },
            )
        if (
            approval.target_revision is not None
            and target_km.revision != approval.target_revision
        ) or (
            approval.target_fingerprint is not None
            and target_km.content_fingerprint != approval.target_fingerprint
        ):
            approval.status = "SUPERSEDED"
            approval.decision_note = (
                f"Hết hiệu lực: yêu cầu cho rev #{approval.target_revision} "
                f"nhưng Mapping đã lên rev #{target_km.revision}."
            )
            db.commit()
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "APPROVAL_REVISION_MISMATCH",
                    "reason": (
                        f"Yêu cầu phê duyệt cũ (rev #{approval.target_revision}) không còn khớp với "
                        f"Mapping hiện tại (rev #{target_km.revision})."
                    ),
                    "impact": "Không ghi thay đổi lên Mapping mới để tránh duyệt nhầm bằng chứng lỗi thời.",
                    "solution": "Tải lại Chờ phê duyệt và duyệt mục PENDING mới nhất khớp rev hiện hành.",
                    "next_action": "Duyệt lại phiên bản Mapping mới nhất.",
                    "cta_label": "Làm mới Chờ phê duyệt",
                    "cta_href": "/approvals",
                },
            )

    now = datetime.now(timezone.utc)
    approval.status = decision
    approval.decision_note = payload.decision_note.strip()
    approval.decided_by = payload.decided_by.strip() or "SEO Specialist"
    approval.decided_at = now
    approval.version += 1

    if decision == "APPROVED":
        if approval.approval_type == "PRIMARY_KEYWORD_CHANGE":
            # Original primary keyword remains immutable forever; only current keyword updates after approval!
            project.primary_keyword_current = approval.proposed_value
        elif approval.scope == "BRIEF_ELIGIBILITY" and target_km is not None:
            target_km.is_approved = True
            target_km.approved_revision = target_km.revision
            target_km.approved_fingerprint = target_km.content_fingerprint
            target_km.approved_at = now
            db.flush()
            ctx = load_project_policy_context(db, project)
            dec = evaluate_mapping_eligibility(project, target_km, ctx)
            target_km.content_status = dec["recommended_content_status"]
    elif target_km is not None:
        # REJECTED or NEED_MORE_EVIDENCE MUST keep mapping unapproved & blocked!
        target_km.is_approved = False
        target_km.content_status = "RESEARCH_REQUIRED" if decision == "NEED_MORE_EVIDENCE" else "HOLD"

    db.add(
        ProjectEvent(
            project_id=project.id,
            level="SUCCESS" if decision == "APPROVED" else "WARNING",
            event_type="APPROVAL_DECIDED",
            message=(
                f"[{decision}] {approval.title} "
                f"(scope={approval.scope}, rev={approval.target_revision}, bởi {approval.decided_by})."
            ),
            details_json=json.dumps(
                {
                    "approval_id": approval.id,
                    "target_ref": approval.target_ref,
                    "target_revision": approval.target_revision,
                    "target_fingerprint": approval.target_fingerprint,
                    "note": approval.decision_note,
                },
                ensure_ascii=False,
            ),
        )
    )
    db.commit()

    return {
        "saved": True,
        "approval_id": approval.id,
        "status": approval.status,
        "scope": approval.scope,
        "target_revision": approval.target_revision,
        "target_fingerprint": approval.target_fingerprint,
        "decided_at": now.isoformat(),
        "workflow": refresh_workflow_state(db, project),
    }
