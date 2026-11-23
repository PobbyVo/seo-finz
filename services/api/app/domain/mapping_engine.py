from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

from sqlalchemy.orm import Session

from app.domain.eligibility_policy import (
    POLICY_VERSION,
    compute_mapping_fingerprint,
    compute_metrics_evidence_hash,
    evaluate_mapping_eligibility,
    evaluate_serp_for_keyword,
    load_project_policy_context,
    select_effective_metrics_row,
)
from app.domain.taxonomy_parser import normalize_text
from app.knowledge import priority_for
from app.models import (
    Approval,
    ArticleOpportunity,
    ContentBrief,
    DemandGroup,
    EvidenceRow,
    ExportRecord,
    KeywordMapping,
    MappingRevision,
    Project,
    ProjectEvent,
    SourceKeyword,
)


def slugify_vi(text: str) -> str:
    s = unicodedata.normalize("NFD", text.lower())
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = s.replace("đ", "d")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "bai-viet-seo"


def _record_mapping_revision(db: Session, km: KeywordMapping) -> None:
    payload = {
        "id": km.id,
        "logical_key": km.logical_key,
        "revision": km.revision,
        "content_fingerprint": km.content_fingerprint,
        "primary_keyword": km.primary_keyword,
        "secondary_keywords": json.loads(km.secondary_keywords_json or "[]"),
        "page_type": km.page_type,
        "proposed_url": km.proposed_url,
        "volume": km.volume,
        "kd": km.kd,
        "intent": km.intent,
        "metrics_source": km.metrics_source,
        "metrics_evidence_id": km.metrics_evidence_id,
        "priority": km.priority,
        "business_value": km.business_value,
        "effort": km.effort,
        "serp_status": km.serp_status,
        "merge_split_proposal": km.merge_split_proposal,
    }
    db.add(
        MappingRevision(
            project_id=km.project_id,
            keyword_mapping_id=km.id,
            revision=km.revision,
            content_fingerprint=km.content_fingerprint,
            payload_json=json.dumps(payload, ensure_ascii=False),
        )
    )


def _propose_url(page_type: str, primary_kw: str) -> str:
    url_prefix = {
        "ARTICLE": "/blog/",
        "TOOL": "/cong-cu/",
        "DOWNLOAD": "/tai-nguyen/",
        "SERVICE": "/dich-vu/",
        "PRODUCT": "/san-pham/",
    }.get(page_type, "/noi-dung/")
    return f"{url_prefix}{slugify_vi(primary_kw)}"


def _ensure_pending_approval_for_mapping(
    db: Session,
    project: Project,
    km: KeywordMapping,
    *,
    coverage_type: str,
    serp_eval: dict[str, Any],
    material_changed: bool,
    reason_suffix: str = "",
) -> bool:
    """Create exact ONE PENDING approval for `(km.id, km.revision, km.content_fingerprint)` if needed."""
    has_current_decision = (
        db.query(Approval)
        .filter(
            Approval.project_id == project.id,
            Approval.target_ref == km.id,
            Approval.scope == "BRIEF_ELIGIBILITY",
            Approval.target_revision == km.revision,
            Approval.target_fingerprint == km.content_fingerprint,
            Approval.status.in_(["PENDING", "APPROVED"]),
        )
        .first()
    )
    if km.is_approved or has_current_decision:
        return False

    orig_pk = project.primary_keyword_original or ""
    is_new_topic = coverage_type == "GAP"
    is_overlap = coverage_type == "OVERLAP"
    apr_type = (
        "OVERLAP_MERGE_SPLIT"
        if is_overlap
        else ("NEW_TOPIC_PROPOSAL" if is_new_topic else "FINAL_MAPPING")
    )
    reapproval_tag = f" [CẦN DUYỆT LẠI{reason_suffix}]" if (material_changed and km.revision > 1) else ""
    serp_sufficient = bool(serp_eval.get("serp_sufficient"))
    serp_tier = serp_eval.get("serp_tier", "SERP_NOT_VERIFIED")

    db.add(
        Approval(
            project_id=project.id,
            approval_type=apr_type,
            target_ref=km.id,
            target_revision=km.revision,
            target_fingerprint=km.content_fingerprint,
            title=f"Phê duyệt Mapping rev #{km.revision} ({km.page_type}): {km.primary_keyword}{reapproval_tag}",
            original_value=orig_pk or "(chưa có mapping trước đó)",
            proposed_value=f"{km.page_type} | {km.primary_keyword} -> {km.proposed_url} (fp:{km.content_fingerprint[:10]})",
            rationale=km.merge_split_proposal,
            evidence_json=km.evidence_json,
            impact=(
                f"Phê duyệt đúng phiên bản rev #{km.revision} cho '{km.primary_keyword}'. "
                + (
                    "Đủ điều kiện xem xét xuất Brief chính thức sau khi hoàn tất tất cả Quality Gates."
                    if serp_sufficient
                    else f"Lưu ý: hiện tại là {serp_tier}, vẫn cần bổ sung SERP trước khi xuất Brief chính thức."
                )
            ),
            scope="BRIEF_ELIGIBILITY",
            status="PENDING",
            version=km.revision,
        )
    )
    return True


def _invalidate_linked_briefs_and_exports(
    db: Session,
    project: Project,
    km: KeywordMapping,
    *,
    reason: str,
) -> tuple[int, int]:
    """
    Mark linked ContentBriefs stale & downgrade OFFICIAL -> DRAFT (preserving IDs & BriefVersion history),
    and tag historical ExportRecords referencing this mapping/brief as superseded (preserving original files!).
    """
    stale_briefs_count = 0
    superseded_exports_count = 0

    linked_briefs = (
        db.query(ContentBrief)
        .filter(
            ContentBrief.project_id == project.id,
            ContentBrief.keyword_mapping_id == km.id,
        )
        .all()
    )
    affected_brief_ids: set[str] = set()
    for lb in linked_briefs:
        if lb.mapping_fingerprint != km.content_fingerprint or lb.mapping_revision != km.revision:
            affected_brief_ids.add(lb.id)
            if not lb.is_stale or lb.brief_mode == "OFFICIAL" or lb.status != "STALE_NEEDS_REGENERATION":
                lb.is_stale = True
                if lb.brief_mode == "OFFICIAL":
                    lb.brief_mode = "DRAFT"
                lb.status = "STALE_NEEDS_REGENERATION"
                stale_briefs_count += 1

    # Mark affected historical ExportRecords as superseded without altering original files on disk!
    exports = (
        db.query(ExportRecord)
        .filter(ExportRecord.project_id == project.id, ExportRecord.is_superseded == False)  # noqa: E712
        .all()
    )
    for exp in exports:
        bf_map = json.loads(getattr(exp, "brief_fingerprints_json", "{}") or "{}")
        mentions_mapping = any(
            (meta.get("mapping_id") == km.id or bid in affected_brief_ids)
            for bid, meta in bf_map.items()
            if isinstance(meta, dict)
        )
        # Also supersede legacy OFFICIAL exports lacking brief_fingerprints_json when any mapping changes
        if mentions_mapping or (exp.brief_mode == "OFFICIAL" and not bf_map):
            exp.is_superseded = True
            exp.superseded_reason = reason
            superseded_exports_count += 1

    return stale_briefs_count, superseded_exports_count


def reconcile_project_freshness(
    db: Session,
    project: Project,
    *,
    trigger_batch_id: str | None = None,
    create_approvals: bool = True,
) -> dict[str, Any]:
    """
    Transactional, idempotent import-time freshness reconciler (runs BEFORE caller's db.commit()!).
    - Re-evaluates every active KeywordMapping against the latest coherent metrics & SERP snapshots.
    - When semantic evidence changes for mapping M:
      * Increments M.revision, updates M.content_fingerprint & metrics/SERP summary, records MappingRevision.
      * Revokes M.is_approved (preserving approved_revision/approved_fingerprint audit trail!).
      * Marks old PENDING approvals for M as SUPERSEDED and opens ONE fresh PENDING approval for new rev.
      * Marks linked ContentBriefs stale & downgrades OFFICIAL -> DRAFT (preserving BriefVersion history).
      * Marks affected historical ExportRecords `is_superseded=True` (preserving original immutable files).
    - When semantic evidence for mapping M is UNCHANGED (e.g. unrelated keyword import or identical file re-import):
      * Leaves M, its approval, its revision, and its OFFICIAL brief 100% untouched!
    """
    active_mappings = (
        db.query(KeywordMapping)
        .filter(KeywordMapping.project_id == project.id, KeywordMapping.is_archived == False)  # noqa: E712
        .order_by(KeywordMapping.priority.asc(), KeywordMapping.created_at.asc())
        .all()
    )
    if not active_mappings:
        return {
            "affected_mapping_ids": [],
            "invalidated_approvals": 0,
            "new_pending_approvals": 0,
            "stale_briefs": 0,
            "superseded_exports": 0,
        }

    ctx = load_project_policy_context(db, project)
    proj_market = (project.market or "VN").upper()
    evidence_rows: list[EvidenceRow] = ctx["evidence_rows"]
    batches_by_id = ctx["batches_by_id"]
    uploads_by_id = ctx["uploads_by_id"]
    batch_integrity_by_id = ctx["batch_integrity_by_id"]
    demand_groups_by_id = ctx["demand_groups_by_id"]
    organic_rows = [r for r in evidence_rows if r.row_type == "ORGANIC_RESULTS"]

    affected_ids: list[str] = []
    superseded_approvals_count = 0
    new_approvals_count = 0
    stale_briefs_count = 0
    superseded_exports_count = 0

    for km in active_mappings:
        dg = demand_groups_by_id.get(km.demand_group_id) if km.demand_group_id else None
        m_row, m_batch, _all_m = select_effective_metrics_row(project, km.primary_keyword, evidence_rows, batches_by_id)
        metrics_hash = compute_metrics_evidence_hash(m_row, m_batch, proj_market)
        serp_eval = evaluate_serp_for_keyword(
            project,
            km.primary_keyword,
            organic_rows,
            batches_by_id,
            uploads_by_id,
            batch_integrity_by_id=batch_integrity_by_id,
        )

        # Keep base page_type unless latest valid SERP snapshot explicitly indicates a dominant type
        base_page_type = (dg.assumed_page_type or "ARTICLE").upper() if dg else (km.page_type or "ARTICLE").upper()
        new_page_type = base_page_type
        if serp_eval["serp_sufficient"] and serp_eval["dominant_page_type_hypothesis"] in {"ARTICLE", "TOOL", "DOWNLOAD", "SERVICE", "PRODUCT"}:
            new_page_type = serp_eval["dominant_page_type_hypothesis"]
        new_url = _propose_url(new_page_type, km.primary_keyword) if new_page_type != km.page_type else km.proposed_url
        new_effort = "HIGH" if new_page_type in ("TOOL", "PRODUCT") else ("LOW" if new_page_type == "DOWNLOAD" else "MEDIUM")

        secondary_kws = json.loads(km.secondary_keywords_json or "[]")
        live_fp = compute_mapping_fingerprint(
            primary_keyword=km.primary_keyword,
            secondary_keywords=secondary_kws,
            demand_group_id=km.demand_group_id,
            proposed_url=new_url,
            page_type=new_page_type,
            market=proj_market,
            metrics_evidence_hash=metrics_hash,
            serp_evidence_hash=serp_eval["serp_evidence_hash"],
            priority=km.priority,
            business_value=km.business_value,
            effort=new_effort,
        )

        if live_fp == km.content_fingerprint:
            # Semantically identical -> idempotent no-op (zero approval churn!)
            continue

        affected_ids.append(km.id)
        km.revision = (km.revision or 0) + 1
        km.content_fingerprint = live_fp
        km.page_type = new_page_type
        km.proposed_url = new_url
        km.effort = new_effort
        km.volume = m_row.volume if m_row else None
        km.kd = m_row.kd if m_row else None
        km.intent = m_row.intent if m_row else None
        km.metrics_source = f"Semrush Batch {m_row.batch_id}" if m_row else "Chưa có dữ liệu Semrush"
        km.metrics_evidence_id = m_row.id if m_row else None
        km.serp_status = serp_eval["serp_tier"]
        km.serp_evidence_summary_json = json.dumps(serp_eval, ensure_ascii=False)
        km.is_approved = False

        ev_list = list(json.loads(dg.supporting_evidence_json or "[]")) if dg else [f"Từ dữ liệu nguồn dự án {project.code}."]
        if m_row:
            ev_list.append(
                f"Semrush batch {m_row.batch_id} ({proj_market}): Volume={m_row.volume if m_row.volume is not None else 'thiếu'}, "
                f"KD={m_row.kd if m_row.kd is not None else 'thiếu'}, Intent={m_row.intent or 'thiếu'}."
            )
        ev_list.append(serp_eval["sufficiency_reason"])
        if serp_eval["sample_urls"]:
            ev_list.append(f"URL organic mẫu ({serp_eval['serp_tier']}): {serp_eval['sample_urls'][0]}")
        km.evidence_json = json.dumps(ev_list, ensure_ascii=False)

        db.flush()
        _record_mapping_revision(db, km)

        # Mark old PENDING approvals for this mapping as SUPERSEDED (preserving past APPROVED rows as audit history!)
        old_pendings = (
            db.query(Approval)
            .filter(
                Approval.project_id == project.id,
                Approval.target_ref == km.id,
                Approval.status == "PENDING",
            )
            .all()
        )
        for oa in old_pendings:
            oa.status = "SUPERSEDED"
            oa.decision_note = (
                f"Hết hiệu lực do bằng chứng mới (batch {trigger_batch_id or 'import'}) cập nhật Mapping sang rev #{km.revision}."
            )
            superseded_approvals_count += 1

        if create_approvals:
            created_apr = _ensure_pending_approval_for_mapping(
                db,
                project,
                km,
                coverage_type=dg.coverage_type if dg else "COVERED",
                serp_eval=serp_eval,
                material_changed=True,
                reason_suffix=" — BẰNG CHỨNG MỚI",
            )
            if created_apr:
                new_approvals_count += 1

        stale_reason = (
            f"Bằng chứng cho '{km.primary_keyword}' thay đổi bởi batch {trigger_batch_id or 'import'} (rev #{km.revision})."
        )
        sb, se = _invalidate_linked_briefs_and_exports(db, project, km, reason=stale_reason)
        stale_briefs_count += sb
        superseded_exports_count += se

    if affected_ids:
        db.flush()
        fresh_ctx = load_project_policy_context(db, project)
        opps_by_km = {
            o.keyword_mapping_id: o
            for o in db.query(ArticleOpportunity).filter(ArticleOpportunity.project_id == project.id).all()
            if o.keyword_mapping_id
        }
        for km in active_mappings:
            if km.id in affected_ids:
                dec = evaluate_mapping_eligibility(project, km, fresh_ctx)
                km.content_status = dec["recommended_content_status"]
                if km.id in opps_by_km:
                    opps_by_km[km.id].status = km.content_status
                    opps_by_km[km.id].page_type = km.page_type
        db.flush()

    return {
        "affected_mapping_ids": affected_ids,
        "invalidated_approvals": superseded_approvals_count,
        "new_pending_approvals": new_approvals_count,
        "stale_briefs": stale_briefs_count,
        "superseded_exports": superseded_exports_count,
    }


def build_keyword_mapping_preview(db: Session, project: Project, *, create_approvals: bool = True, target_mapping_id: str | None = None) -> dict[str, Any]:
    """
    Non-destructive, idempotent Keyword Mapping & Article Opportunities builder.
    Consumes the EXACT same single-snapshot SERP & semantic metrics fingerprint policy as `eligibility_policy.py`.
    """
    ctx = load_project_policy_context(db, project)
    proj_market = (project.market or "VN").upper()

    demand_groups = (
        db.query(DemandGroup)
        .filter(DemandGroup.project_id == project.id, DemandGroup.is_promoted == True)  # noqa: E712
        .order_by(DemandGroup.created_at.asc())
        .all()
    )
    evidence_rows: list[EvidenceRow] = ctx["evidence_rows"]
    batches_by_id = ctx["batches_by_id"]
    uploads_by_id = ctx["uploads_by_id"]
    batch_integrity_by_id = ctx["batch_integrity_by_id"]
    organic_rows = [r for r in evidence_rows if r.row_type == "ORGANIC_RESULTS"]

    existing_mappings = (
        db.query(KeywordMapping)
        .filter(KeywordMapping.project_id == project.id)
        .all()
    )
    by_logical_key: dict[str, KeywordMapping] = {}
    for em in existing_mappings:
        key = em.logical_key or (f"dg:{em.demand_group_id}" if em.demand_group_id else f"kw:{normalize_text(em.primary_keyword)}")
        by_logical_key[key] = em

    source_units: list[dict[str, Any]] = []
    if demand_groups:
        for dg in demand_groups:
            seeds = json.loads(dg.seed_keywords_json or "[]")
            related = json.loads(dg.related_keywords_json or "[]")
            source_units.append(
                {
                    "logical_key": f"dg:{dg.id}",
                    "dg": dg,
                    "name": dg.name,
                    "seeds": seeds,
                    "related": related,
                    "page_type": (dg.assumed_page_type or "ARTICLE").upper(),
                    "coverage_type": dg.coverage_type,
                    "evidence": json.loads(dg.supporting_evidence_json or "[]"),
                    "missing": json.loads(dg.missing_data_json or "[]"),
                    "business_note": dg.business_relevance_note,
                }
            )
    else:
        pk = project.primary_keyword_current or project.primary_keyword_original
        if pk:
            source_units.append(
                {
                    "logical_key": f"kw:{normalize_text(pk)}",
                    "dg": None,
                    "name": project.topic_pillar_name or project.name,
                    "seeds": [pk],
                    "related": json.loads(project.secondary_keywords_json or "[]"),
                    "page_type": "ARTICLE",
                    "coverage_type": "COVERED",
                    "evidence": [f"Từ dữ liệu nguồn dự án {project.code}."],
                    "missing": ["Chưa chạy AI Topic Analyst (Bước 02)."],
                    "business_note": project.business_goal,
                }
            )

    if not project.content_code:
        source_rows = db.query(SourceKeyword).filter_by(project_id=project.id).all()
        primaries = [r for r in source_rows if r.role == "PRIMARY"]
        if len(primaries) > 1:
            source_units = [{"logical_key": f"source:{r.content_code}", "dg": None, "name": r.content_title or r.keyword, "seeds": [r.keyword], "related": [s.keyword for s in source_rows if s.content_code == r.content_code and s.role != "PRIMARY"], "page_type": "ARTICLE", "coverage_type": "COVERED", "evidence": [r.source_ref], "missing": [], "business_note": ""} for r in primaries]

    # Tài nguyên rõ loại được đưa vào backlog riêng, không tăng quota ARTICLE.
    if not project.content_code:
        source_rows = db.query(SourceKeyword).filter_by(project_id=project.id).all()
        from app.domain.research_business import infer_query_asset as _guess_page_type
        existing_seeds = {normalize_text(k) for unit in source_units for k in unit["seeds"]}
        for source in source_rows:
            kind = _guess_page_type(source.keyword)
            if kind in {"TOOL", "DOWNLOAD", "UNKNOWN"} and source.keyword_normalized not in existing_seeds:
                source_units.append({"logical_key":f"asset:{source.keyword_normalized}","dg":None,"name":source.keyword,"seeds":[source.keyword],"related":[],"page_type":kind,"coverage_type":"GAP","evidence":[source.source_ref],"missing":[],"business_note":"Backlog tài nguyên; FinZ hiện chỉ sản xuất bài viết."})

    latest_analysis = {}
    for event in db.query(ProjectEvent).filter_by(project_id=project.id).order_by(ProjectEvent.created_at.asc()).all():
        analysis = json.loads(event.details_json or "{}").get("serp_analysis")
        if analysis:latest_analysis[normalize_text(analysis["keyword"])]=analysis
    for unit in source_units:
        analysis=latest_analysis.get(normalize_text(unit["seeds"][0]),{}) if unit["seeds"] else {}
        if analysis.get("decision")=="BACKLOG" and analysis.get("distribution"):
            unit["page_type"]=max(analysis["distribution"],key=analysis["distribution"].get)

    target_mapping = next((m for m in existing_mappings if m.id == target_mapping_id), None) if target_mapping_id else None
    if target_mapping_id and target_mapping is None:
        raise ValueError("Không tìm thấy dòng mapping cần chạy lại.")
    if target_mapping:
        source_units = [u for u in source_units if u["logical_key"] == target_mapping.logical_key or (u["seeds"] and normalize_text(u["seeds"][0]) == normalize_text(target_mapping.primary_keyword))]

    seen_logical_keys: set[str] = set()
    active_mappings: list[KeywordMapping] = []
    new_approvals_count = 0
    superseded_approvals_count = 0
    stale_briefs_count = 0
    article_count = 0
    non_article_count = 0
    gap_count = 0

    # Rebuild derived opportunities view cleanly (KeywordMapping & BriefVersion history are NEVER deleted)
    opportunity_query = db.query(ArticleOpportunity).filter(ArticleOpportunity.project_id == project.id)
    if target_mapping_id:opportunity_query=opportunity_query.filter(ArticleOpportunity.keyword_mapping_id==target_mapping_id)
    opportunity_query.delete()

    for idx, unit in enumerate(source_units):
        lkey = unit["logical_key"]
        seen_logical_keys.add(lkey)

        seeds = [s for s in unit["seeds"] if s]
        related = [r for r in unit["related"] if r]
        primary_kw = seeds[0] if seeds else (project.primary_keyword_original or unit["name"])
        pk_norm = normalize_text(primary_kw)
        secondary_kws = [k for k in (seeds[1:] + related) if normalize_text(k) != pk_norm]

        # Deterministic exact-keyword, exact-market metrics & single-snapshot SERP evaluation
        m_row, m_batch, _all_m = select_effective_metrics_row(project, primary_kw, evidence_rows, batches_by_id)
        metrics_hash = compute_metrics_evidence_hash(m_row, m_batch, proj_market)

        serp_eval = evaluate_serp_for_keyword(
            project,
            primary_kw,
            organic_rows,
            batches_by_id,
            uploads_by_id,
            batch_integrity_by_id=batch_integrity_by_id,
        )
        serp_sufficient = serp_eval["serp_sufficient"]
        serp_tier = serp_eval["serp_tier"]

        page_type = unit["page_type"]
        if serp_sufficient and serp_eval["dominant_page_type_hypothesis"] in {"ARTICLE", "TOOL", "DOWNLOAD", "SERVICE", "PRODUCT"}:
            page_type = serp_eval["dominant_page_type_hypothesis"]

        analysis = latest_analysis.get(pk_norm, {})
        if analysis.get("selected_batch_id") == serp_eval.get("selected_batch_id") and analysis.get("decision") == "BACKLOG" and analysis.get("distribution"):
            dominant_ai=max(analysis["distribution"], key=analysis["distribution"].get)
            page_type="UNKNOWN" if dominant_ai=="DATA" else dominant_ai
        counts_for_article = page_type == "ARTICLE"

        priority, priority_reason = priority_for(m_row.volume if m_row else None, m_row.kd if m_row else None)
        biz_val = "HIGH" if priority == "P1" else "MEDIUM"
        unit["business_note"] = priority_reason

        effort = "HIGH" if page_type in ("TOOL", "PRODUCT") else ("LOW" if page_type == "DOWNLOAD" else "MEDIUM")

        if unit["coverage_type"] == "OVERLAP":
            merge_split = (
                "ĐỀ XUẤT GỘP/TÁCH CẦN BẰNG CHỨNG: Nhóm có dấu hiệu giao thoa ý định tìm kiếm. "
                + (
                    f"{serp_eval['sufficiency_reason']} Cần người dùng phê duyệt quyết định gộp hoặc tách bài."
                    if serp_sufficient
                    else "Chưa đủ bằng chứng SERP cho từ khóa này — KHÔNG tự kết luận tách bài."
                )
            )
        elif not serp_sufficient:
            merge_split = (
                f"ĐỀ XUẤT DỰ THẢO ({serp_tier}): {serp_eval['sufficiency_reason']} "
                "Cần bằng chứng ORGANIC_RESULTS trong 1 snapshot thống nhất cho đúng từ khóa này trước khi chốt tách bài."
            )
        else:
            merge_split = (
                f"{serp_eval['sufficiency_reason']} Đề xuất giữ trang riêng dạng {page_type} và chờ người dùng phê duyệt."
            )

        proposed_url = _propose_url(page_type, primary_kw)

        ev_list = list(unit["evidence"])
        if m_row:
            ev_list.append(
                f"Semrush batch {m_row.batch_id} ({proj_market}): Volume={m_row.volume if m_row.volume is not None else 'thiếu'}, "
                f"KD={m_row.kd if m_row.kd is not None else 'thiếu'}, Intent={m_row.intent or 'thiếu'}."
            )
        else:
            ev_list.append(f"Chưa có dòng metrics khớp chính xác '{primary_kw}' tại thị trường {proj_market}.")
        ev_list.append(serp_eval["sufficiency_reason"])
        if serp_eval["sample_urls"]:
            ev_list.append(f"URL organic mẫu ({serp_tier}): {serp_eval['sample_urls'][0]}")

        new_fp = compute_mapping_fingerprint(
            primary_keyword=primary_kw,
            secondary_keywords=secondary_kws,
            demand_group_id=unit["dg"].id if unit["dg"] else None,
            proposed_url=proposed_url,
            page_type=page_type,
            market=proj_market,
            metrics_evidence_hash=metrics_hash,
            serp_evidence_hash=serp_eval["serp_evidence_hash"],
            priority=priority,
            business_value=biz_val,
            effort=effort,
        )

        existing = by_logical_key.get(lkey)
        if existing is None:
            existing = next(
                (em for em in existing_mappings if not em.is_archived and normalize_text(em.primary_keyword) == pk_norm),
                None,
            )

        material_changed = False
        if existing is None:
            km = KeywordMapping(
                project_id=project.id,
                demand_group_id=unit["dg"].id if unit["dg"] else None,
                logical_key=lkey,
                revision=1,
                content_fingerprint=new_fp,
                primary_keyword=primary_kw,
                secondary_keywords_json=json.dumps(secondary_kws, ensure_ascii=False),
                page_type=page_type,
                proposed_url=proposed_url,
                volume=m_row.volume if m_row else None,
                kd=m_row.kd if m_row else None,
                intent=m_row.intent if m_row else None,
                metrics_source=(f"Semrush Batch {m_row.batch_id}" if m_row else "Chưa có dữ liệu Semrush"),
                metrics_evidence_id=m_row.id if m_row else None,
                priority=priority,
                business_value=biz_val,
                effort=effort,
                merge_split_proposal=merge_split,
                serp_status=serp_tier,
                serp_evidence_summary_json=json.dumps(serp_eval, ensure_ascii=False),
                content_status="SERP_NOT_VERIFIED",
                evidence_json=json.dumps(ev_list, ensure_ascii=False),
                is_approved=False,
                approved_revision=None,
                approved_fingerprint=None,
                approved_at=None,
                is_archived=False,
            )
            db.add(km)
            db.flush()
            _record_mapping_revision(db, km)
            material_changed = True
        else:
            km = existing
            km.is_archived = False
            km.logical_key = lkey
            if km.content_fingerprint != new_fp:
                material_changed = True
                km.revision = (km.revision or 0) + 1
                km.content_fingerprint = new_fp
                km.demand_group_id = unit["dg"].id if unit["dg"] else km.demand_group_id
                km.primary_keyword = primary_kw
                km.secondary_keywords_json = json.dumps(secondary_kws, ensure_ascii=False)
                km.page_type = page_type
                km.proposed_url = proposed_url
                km.volume = m_row.volume if m_row else None
                km.kd = m_row.kd if m_row else None
                km.intent = m_row.intent if m_row else None
                km.metrics_source = f"Semrush Batch {m_row.batch_id}" if m_row else "Chưa có dữ liệu Semrush"
                km.metrics_evidence_id = m_row.id if m_row else None
                km.priority = priority
                km.business_value = biz_val
                km.effort = effort
                km.merge_split_proposal = merge_split
                km.serp_status = serp_tier
                km.serp_evidence_summary_json = json.dumps(serp_eval, ensure_ascii=False)
                km.evidence_json = json.dumps(ev_list, ensure_ascii=False)
                km.is_approved = False
                db.flush()
                _record_mapping_revision(db, km)

                old_pendings = (
                    db.query(Approval)
                    .filter(
                        Approval.project_id == project.id,
                        Approval.target_ref == km.id,
                        Approval.status == "PENDING",
                    )
                    .all()
                )
                for oa in old_pendings:
                    oa.status = "SUPERSEDED"
                    oa.decision_note = f"Hết hiệu lực do Mapping cập nhật sang rev #{km.revision}."
                    superseded_approvals_count += 1

                sb, _se = _invalidate_linked_briefs_and_exports(
                    db, project, km, reason=f"Keyword Mapping '{km.primary_keyword}' cập nhật sang rev #{km.revision}."
                )
                stale_briefs_count += sb
            else:
                km.serp_status = serp_tier
                km.serp_evidence_summary_json = json.dumps(serp_eval, ensure_ascii=False)

        if create_approvals:
            if _ensure_pending_approval_for_mapping(
                db,
                project,
                km,
                coverage_type=unit["coverage_type"],
                serp_eval=serp_eval,
                material_changed=material_changed,
            ):
                new_approvals_count += 1

        db.flush()

        fresh_ctx = load_project_policy_context(db, project)
        decision = evaluate_mapping_eligibility(project, km, fresh_ctx)
        km.content_status = decision["recommended_content_status"]
        active_mappings.append(km)

        if not counts_for_article:
            opp_kind = "NON_ARTICLE_ASSET"
            non_article_count += 1
        elif m_row is None:
            opp_kind = "RESEARCH_GAP"
            gap_count += 1
        elif counts_for_article:
            opp_kind = "ARTICLE_OPPORTUNITY"
            article_count += 1
        else:
            opp_kind = "NON_ARTICLE_ASSET"
            non_article_count += 1

        db.add(
            ArticleOpportunity(
                project_id=project.id,
                keyword_mapping_id=km.id,
                demand_group_name=unit["name"],
                opportunity_kind=opp_kind,
                page_type=page_type,
                counts_toward_article_quota=counts_for_article and m_row is not None,
                title_suggestion=f"{unit['name']} ({primary_kw})",
                primary_keyword=primary_kw,
                priority=priority,
                status=km.content_status,
                rationale=merge_split,
                evidence_json=km.evidence_json,
            )
        )

    for em in existing_mappings:
        if target_mapping_id and em.id != target_mapping_id:
            continue
        em_key = em.logical_key or (f"dg:{em.demand_group_id}" if em.demand_group_id else f"kw:{normalize_text(em.primary_keyword)}")
        if em_key not in seen_logical_keys and not em.is_archived:
            em.is_archived = True
            em.is_approved = False
            for oa in (
                db.query(Approval)
                .filter(Approval.project_id == project.id, Approval.target_ref == em.id, Approval.status == "PENDING")
                .all()
            ):
                oa.status = "SUPERSEDED"
                superseded_approvals_count += 1

    db.commit()

    max_rev = max((m.revision for m in active_mappings), default=1)
    serp_verified_count = sum(1 for m in active_mappings if m.serp_status in ("SERP_VERIFIED", "TOP_10_VERIFIED"))
    all_serp_verified = bool(active_mappings) and serp_verified_count == len(active_mappings)
    plan_serp_status = (
        "SERP_VERIFIED"
        if all_serp_verified
        else ("PARTIAL_SERP_EVIDENCE" if serp_verified_count > 0 else "SERP_NOT_VERIFIED")
    )

    quota_note = (
        f"Đang có {article_count} cơ hội bài ARTICLE (mục tiêu mềm: {project.soft_article_min}–{project.soft_article_max} bài; "
        f"{non_article_count} tài nguyên TOOL/DOWNLOAD/SERVICE không tính vào quota; {gap_count} khoảng trống nghiên cứu). "
        "Hệ thống không ép tạo đủ 5–7 bài nếu chưa đủ nhu cầu độc lập và bằng chứng."
    )

    return {
        "policy_version": POLICY_VERSION,
        "revision": max_rev,
        "plan_mode": "VERIFIED_CANDIDATE" if all_serp_verified else "DRAFT_SERP_NOT_VERIFIED",
        "serp_status": plan_serp_status,
        "article_quota": {
            "soft_min": project.soft_article_min,
            "soft_max": project.soft_article_max,
            "current_articles": article_count,
            "non_article_assets_excluded": non_article_count,
            "research_gaps": gap_count,
            "note": quota_note,
        },
        "mappings_count": len(active_mappings),
        "opportunities_count": len(active_mappings),
        "approvals_created": new_approvals_count,
        "approvals_superseded": superseded_approvals_count,
        "briefs_marked_stale": stale_briefs_count,
    }
