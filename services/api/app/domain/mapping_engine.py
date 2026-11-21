from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

from sqlalchemy.orm import Session

from app.domain.eligibility_policy import (
    POLICY_VERSION,
    compute_mapping_fingerprint,
    evaluate_mapping_eligibility,
    evaluate_serp_for_keyword,
    load_project_policy_context,
)
from app.domain.taxonomy_parser import normalize_text
from app.models import (
    Approval,
    ArticleOpportunity,
    ContentBrief,
    DemandGroup,
    EvidenceRow,
    KeywordMapping,
    MappingRevision,
    Project,
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


def build_keyword_mapping_preview(db: Session, project: Project, *, create_approvals: bool = True) -> dict[str, Any]:
    """
    Non-destructive, idempotent Keyword Mapping & Article Opportunities builder.
    Invariants enforced:
    - NEVER mass-deletes existing KeywordMapping rows (preserves stable IDs, FK references,
      ContentBrief lineage, and Approval audit history).
    - Exact-keyword, exact-market metrics & SERP provenance (NEVER leaks keyword A's SERP to keyword B).
    - Canonical content_fingerprint binds approvals to exact mapping state & evidence.
    - Material change increments revision, invalidates old approval, marks old PENDING approvals
      as SUPERSEDED, creates ONE fresh PENDING approval, and flags outdated OFFICIAL briefs stale!
    - Idempotent rerun with unchanged inputs creates ZERO duplicate approvals and keeps stable IDs/revisions.
    - TOOL / DOWNLOAD / SERVICE / PRODUCT never count toward the soft 5-7 ARTICLE quota.
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

    # Exact-market, non-duplicate metrics indexed by normalized keyword
    metrics_by_kw: dict[str, EvidenceRow] = {}
    for r in evidence_rows:
        if r.row_type == "METRICS" and not r.is_duplicate and (r.market or proj_market).upper() == proj_market:
            metrics_by_kw[r.keyword_normalized] = r

    organic_rows = [r for r in evidence_rows if r.row_type == "ORGANIC_RESULTS"]

    # Load existing mappings cleanly (NEVER mass delete!)
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

    seen_logical_keys: set[str] = set()
    active_mappings: list[KeywordMapping] = []
    new_approvals_count = 0
    superseded_approvals_count = 0
    stale_briefs_count = 0
    article_count = 0
    non_article_count = 0
    gap_count = 0

    # Rebuild derived opportunities view non-destructively after mappings are updated
    db.query(ArticleOpportunity).filter(ArticleOpportunity.project_id == project.id).delete()

    for idx, unit in enumerate(source_units):
        lkey = unit["logical_key"]
        seen_logical_keys.add(lkey)

        seeds = [s for s in unit["seeds"] if s]
        related = [r for r in unit["related"] if r]
        primary_kw = seeds[0] if seeds else (project.primary_keyword_original or unit["name"])
        pk_norm = normalize_text(primary_kw)
        secondary_kws = [k for k in (seeds[1:] + related) if normalize_text(k) != pk_norm]

        # STRICT exact primary keyword metrics in matching market (NEVER silently borrow keyword B's metrics!)
        m_row = metrics_by_kw.get(pk_norm)

        # STRICT per-keyword, per-market SERP provenance (NEVER fallback to project-global SERP!)
        serp_eval = evaluate_serp_for_keyword(project, primary_kw, organic_rows, batches_by_id, uploads_by_id)
        serp_sufficient = serp_eval["serp_sufficient"]
        serp_tier = serp_eval["serp_tier"]

        page_type = unit["page_type"]
        if serp_sufficient and serp_eval["dominant_page_type_hypothesis"] in {"ARTICLE", "TOOL", "DOWNLOAD", "SERVICE", "PRODUCT"}:
            page_type = serp_eval["dominant_page_type_hypothesis"]

        counts_for_article = page_type == "ARTICLE"

        has_biz = bool((project.business_goal or "").strip() or (unit["business_note"] or "").strip())
        if idx == 0 or (m_row and m_row.volume is not None and m_row.volume >= 500 and has_biz):
            priority = "P1"
            biz_val = "HIGH"
        elif has_biz or (m_row and m_row.volume is not None and m_row.volume >= 100):
            priority = "P2"
            biz_val = "HIGH" if has_biz else "MEDIUM"
        else:
            priority = "P3"
            biz_val = "MEDIUM"

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
                "Cần bằng chứng ORGANIC_RESULTS cho đúng từ khóa này trước khi chốt tách bài."
            )
        else:
            merge_split = (
                f"{serp_eval['sufficiency_reason']} Đề xuất giữ trang riêng dạng {page_type} và chờ người dùng phê duyệt."
            )

        url_prefix = {
            "ARTICLE": "/blog/",
            "TOOL": "/cong-cu/",
            "DOWNLOAD": "/tai-nguyen/",
            "SERVICE": "/dich-vu/",
            "PRODUCT": "/san-pham/",
        }.get(page_type, "/noi-dung/")
        proposed_url = f"{url_prefix}{slugify_vi(primary_kw)}"

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
            metrics_evidence_id=m_row.id if m_row else None,
            metrics_batch_id=m_row.batch_id if m_row else None,
            serp_evidence_hash=serp_eval["serp_evidence_hash"],
            priority=priority,
            business_value=biz_val,
            effort=effort,
            merge_split_proposal=merge_split,
        )

        existing = by_logical_key.get(lkey)
        # Fallback match by normalized primary keyword for pre-0002 legacy rows missing logical_key
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
                # Material change -> increment revision, invalidate stale approval & mark outdated briefs stale!
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
                # Invalidate old approval explicitly (preserving approved_fingerprint audit column if any)
                km.is_approved = False
                db.flush()
                _record_mapping_revision(db, km)

                # Mark any older PENDING approvals for this mapping as SUPERSEDED
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

                # Mark existing ContentBriefs tied to this mapping as STALE & downgrade OFFICIAL -> DRAFT!
                linked_briefs = (
                    db.query(ContentBrief)
                    .filter(
                        ContentBrief.project_id == project.id,
                        ContentBrief.keyword_mapping_id == km.id,
                    )
                    .all()
                )
                for lb in linked_briefs:
                    if lb.mapping_fingerprint != km.content_fingerprint:
                        lb.is_stale = True
                        if lb.brief_mode == "OFFICIAL":
                            lb.brief_mode = "DRAFT"
                        lb.status = "STALE_NEEDS_REGENERATION"
                        stale_briefs_count += 1
            else:
                # Idempotent: keep ID, revision, approval intact; refresh non-material display diagnostics only
                km.serp_status = serp_tier
                km.serp_evidence_summary_json = json.dumps(serp_eval, ensure_ascii=False)

        # Ensure exact ONE pending approval exists for current fingerprint when not approved
        if create_approvals:
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
            if not km.is_approved and not has_current_decision:
                orig_pk = project.primary_keyword_original or ""
                is_new_topic = unit["coverage_type"] == "GAP"
                is_overlap = unit["coverage_type"] == "OVERLAP"
                apr_type = (
                    "OVERLAP_MERGE_SPLIT"
                    if is_overlap
                    else ("NEW_TOPIC_PROPOSAL" if is_new_topic else "FINAL_MAPPING")
                )
                reapproval_tag = " [CẦN DUYỆT LẠI]" if (material_changed and km.revision > 1) else ""
                db.add(
                    Approval(
                        project_id=project.id,
                        approval_type=apr_type,
                        target_ref=km.id,
                        target_revision=km.revision,
                        target_fingerprint=km.content_fingerprint,
                        title=f"Phê duyệt Mapping rev #{km.revision} ({page_type}): {primary_kw}{reapproval_tag}",
                        original_value=orig_pk or "(chưa có mapping trước đó)",
                        proposed_value=f"{page_type} | {primary_kw} -> {proposed_url} (fp:{km.content_fingerprint[:10]})",
                        rationale=merge_split,
                        evidence_json=km.evidence_json,
                        impact=(
                            f"Phê duyệt đúng phiên bản rev #{km.revision} cho '{primary_kw}'. "
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
                new_approvals_count += 1

        db.flush()

        # Re-evaluate authoritative eligibility to keep content_status 100% consistent
        fresh_ctx = load_project_policy_context(db, project)
        decision = evaluate_mapping_eligibility(project, km, fresh_ctx)
        km.content_status = decision["recommended_content_status"]
        active_mappings.append(km)

        if m_row is None:
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

    # Archive any removed mappings non-destructively (NEVER hard-delete!)
    for em in existing_mappings:
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
