from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

from sqlalchemy.orm import Session

from app.domain.taxonomy_parser import normalize_text
from app.models import (
    Approval,
    ArticleOpportunity,
    DemandGroup,
    EvidenceRow,
    KeywordMapping,
    Project,
)


def slugify_vi(text: str) -> str:
    s = unicodedata.normalize("NFD", text.lower())
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = s.replace("đ", "d")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "bai-viet-seo"


def build_keyword_mapping_preview(db: Session, project: Project, *, create_approvals: bool = True) -> dict[str, Any]:
    """
    Generate evidence-backed Keyword Mapping & Article Opportunities from SQLite state.
    Rules enforced:
    - No manual SERP entry step; if ORGANIC_RESULTS exist, verify page type; otherwise SERP_NOT_VERIFIED (DRAFT).
    - TOOL / DOWNLOAD / SERVICE / PRODUCT never count toward the soft 5-7 ARTICLE quota!
    - Never force 5-7 articles when independent demand groups/evidence are insufficient.
    - Merge/split suggestions are framed as proposals requiring evidence, never conclusions.
    - Primary keyword changes or new topic proposals create PENDING Approval records.
    """
    demand_groups = db.query(DemandGroup).filter(DemandGroup.project_id == project.id, DemandGroup.is_promoted == True).all()  # noqa: E712
    metrics_rows = (
        db.query(EvidenceRow)
        .filter(
            EvidenceRow.project_id == project.id,
            EvidenceRow.row_type == "METRICS",
            EvidenceRow.is_duplicate == False,  # noqa: E712
        )
        .all()
    )
    organic_rows = (
        db.query(EvidenceRow)
        .filter(
            EvidenceRow.project_id == project.id,
            EvidenceRow.row_type == "ORGANIC_RESULTS",
            EvidenceRow.is_duplicate == False,  # noqa: E712
        )
        .all()
    )

    metrics_by_kw: dict[str, EvidenceRow] = {r.keyword_normalized: r for r in metrics_rows}
    organic_by_kw: dict[str, list[EvidenceRow]] = {}
    for r in organic_rows:
        organic_by_kw.setdefault(r.keyword_normalized, []).append(r)

    has_global_organic = len(organic_rows) > 0

    # Compute next revision
    prev_rev = (
        db.query(KeywordMapping.revision)
        .filter(KeywordMapping.project_id == project.id)
        .order_by(KeywordMapping.revision.desc())
        .first()
    )
    next_rev = (prev_rev[0] + 1) if prev_rev else 1

    # Preserve existing approved flags per primary keyword if regenerating
    existing_approved = {
        normalize_text(m.primary_keyword): (m.is_approved, m.approved_at)
        for m in db.query(KeywordMapping).filter(KeywordMapping.project_id == project.id).all()
    }

    # Clear previous unapproved draft mappings & opportunities cleanly before writing new revision
    db.query(ArticleOpportunity).filter(ArticleOpportunity.project_id == project.id).delete()
    db.query(KeywordMapping).filter(KeywordMapping.project_id == project.id).delete()

    created_mappings: list[KeywordMapping] = []
    created_opportunities: list[ArticleOpportunity] = []
    new_approvals: list[Approval] = []

    # If user skipped Step 02 (rare) build a single seed demand unit from project primary keyword
    source_units: list[dict[str, Any]] = []
    if demand_groups:
        for dg in demand_groups:
            seeds = json.loads(dg.seed_keywords_json or "[]")
            related = json.loads(dg.related_keywords_json or "[]")
            source_units.append(
                {
                    "dg": dg,
                    "name": dg.name,
                    "seeds": seeds,
                    "related": related,
                    "page_type": dg.assumed_page_type or "ARTICLE",
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

    article_count = 0
    non_article_count = 0
    gap_count = 0

    for idx, unit in enumerate(source_units):
        seeds = [s for s in unit["seeds"] if s]
        related = [r for r in unit["related"] if r]
        primary_kw = seeds[0] if seeds else (project.primary_keyword_original or unit["name"])
        pk_norm = normalize_text(primary_kw)
        secondary_kws = [k for k in (seeds[1:] + related) if normalize_text(k) != pk_norm]

        # Lookup metric evidence for primary or best matching seed
        m_row = metrics_by_kw.get(pk_norm)
        if not m_row:
            for sk in secondary_kws:
                if normalize_text(sk) in metrics_by_kw:
                    m_row = metrics_by_kw[normalize_text(sk)]
                    break

        # Lookup organic SERP evidence for this keyword (or fallback project organic rows)
        kw_organics = organic_by_kw.get(pk_norm) or (organic_rows if idx == 0 and has_global_organic else [])
        serp_verified = len(kw_organics) > 0
        serp_status = "SERP_VERIFIED" if serp_verified else "SERP_NOT_VERIFIED"

        page_type = unit["page_type"]
        if serp_verified:
            # Let organic results refine page type when majority indicates TOOL/DOWNLOAD
            type_counts: dict[str, int] = {}
            for o in kw_organics:
                t = o.organic_page_type or "ARTICLE"
                type_counts[t] = type_counts.get(t, 0) + 1
            dominant = max(type_counts, key=lambda k: type_counts[k])
            if dominant in {"ARTICLE", "TOOL", "DOWNLOAD", "SERVICE", "PRODUCT"}:
                page_type = dominant

        counts_for_article = page_type == "ARTICLE"

        # Determine content status carefully (NEVER auto-promote READY_FOR_BRIEF!)
        if m_row is None:
            content_status = "RESEARCH_REQUIRED"
        elif m_row.volume is not None and m_row.volume < 100 and (project.business_goal or unit["business_note"]):
            content_status = "LOW_VOLUME_BUT_RELEVANT" if serp_verified else "SERP_NOT_VERIFIED"
        elif not serp_verified:
            content_status = "SERP_NOT_VERIFIED"
        else:
            content_status = "PENDING_APPROVAL"

        # Priority based on evidence & business relevance (NO hard KD cutoff!)
        has_biz = bool(project.business_goal or unit["business_note"])
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

        # Merge/split proposal framed strictly as a hypothesis requiring evidence
        if unit["coverage_type"] == "OVERLAP":
            merge_split = (
                "ĐỀ XUẤT GỘP/TÁCH CẦN BẰNG CHỨNG: Nhóm này có dấu hiệu giao thoa ý định tìm kiếm với chủ đề gốc. "
                + (
                    "Đối chiếu ORGANIC_RESULTS để quyết định tách trang độc lập hay gộp mục."
                    if serp_verified
                    else "Chưa có ORGANIC_RESULTS (SERP_NOT_VERIFIED) — KHÔNG tự kết luận tách bài cho tới khi có bằng chứng SERP."
                )
            )
        elif not serp_verified:
            merge_split = (
                "ĐỀ XUẤT DỰ THẢO (SERP_NOT_VERIFIED): Cần kiểm chứng trùng lặp URL top đầu qua báo cáo ORGANIC_RESULTS trước khi chốt tách bài."
            )
        else:
            merge_split = f"Đã đối chiếu {len(kw_organics)} URL từ ORGANIC_RESULTS; đề xuất giữ trang riêng dạng {page_type} và chờ người dùng duyệt."

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
                f"Semrush batch {m_row.batch_id}: Volume={m_row.volume if m_row.volume is not None else 'thiếu'}, "
                f"KD={m_row.kd if m_row.kd is not None else 'thiếu'}, Intent={m_row.intent or 'thiếu'}."
            )
        else:
            ev_list.append("Chưa có dòng metrics khớp chính xác trong Semrush batch — cần nghiên cứu bổ sung.")
        if serp_verified:
            ev_list.append(f"Đã có {len(kw_organics)} URL từ báo cáo ORGANIC_RESULTS (vd: {kw_organics[0].organic_url}).")
        else:
            ev_list.append("SERP_NOT_VERIFIED: chưa có file ORGANIC_RESULTS; không suy đoán đã kiểm tra Top 10 Google.")

        was_approved, approved_at = existing_approved.get(pk_norm, (False, None))

        km = KeywordMapping(
            project_id=project.id,
            demand_group_id=unit["dg"].id if unit["dg"] else None,
            revision=next_rev,
            primary_keyword=primary_kw,
            secondary_keywords_json=json.dumps(secondary_kws, ensure_ascii=False),
            page_type=page_type,
            proposed_url=proposed_url,
            volume=m_row.volume if m_row else None,
            kd=m_row.kd if m_row else None,
            intent=m_row.intent if m_row else None,
            metrics_source=(f"Semrush Batch {m_row.batch_id}" if m_row else "Chưa có dữ liệu Semrush"),
            priority=priority,
            business_value=biz_val,
            effort=effort,
            merge_split_proposal=merge_split,
            serp_status=serp_status,
            content_status=("READY_FOR_BRIEF" if (was_approved and serp_verified and m_row is not None) else content_status),
            evidence_json=json.dumps(ev_list, ensure_ascii=False),
            is_approved=was_approved,
            approved_at=approved_at,
        )
        db.add(km)
        db.flush()
        created_mappings.append(km)

        # Opportunity separation: ARTICLE_OPPORTUNITY vs NON_ARTICLE_ASSET vs RESEARCH_GAP
        if m_row is None:
            opp_kind = "RESEARCH_GAP"
            gap_count += 1
        elif counts_for_article:
            opp_kind = "ARTICLE_OPPORTUNITY"
            article_count += 1
        else:
            opp_kind = "NON_ARTICLE_ASSET"
            non_article_count += 1

        opp = ArticleOpportunity(
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
        db.add(opp)
        created_opportunities.append(opp)

        # Create Approval items for human-in-the-loop decisions
        if create_approvals and not was_approved:
            orig_pk = project.primary_keyword_original or ""
            is_new_topic = unit["coverage_type"] == "GAP"
            is_overlap = unit["coverage_type"] == "OVERLAP"
            existing_pending = (
                db.query(Approval)
                .filter(
                    Approval.project_id == project.id,
                    Approval.target_ref == km.id,
                    Approval.status == "PENDING",
                )
                .first()
            )
            if not existing_pending:
                apr_type = (
                    "OVERLAP_MERGE_SPLIT"
                    if is_overlap
                    else ("NEW_TOPIC_PROPOSAL" if is_new_topic else "FINAL_MAPPING")
                )
                apr = Approval(
                    project_id=project.id,
                    approval_type=apr_type,
                    target_ref=km.id,
                    title=f"Phê duyệt Mapping ({page_type}): {primary_kw}",
                    original_value=orig_pk or "(chưa có mapping trước đó)",
                    proposed_value=f"{page_type} | {primary_kw} -> {proposed_url}",
                    rationale=merge_split,
                    evidence_json=km.evidence_json,
                    impact=(
                        f"Cho phép đưa '{primary_kw}' vào danh sách xuất Content Brief "
                        + ("(chính thức sau khi đủ SERP)." if not serp_verified else "chính thức.")
                    ),
                    scope="BRIEF_ELIGIBILITY",
                    status="PENDING",
                    version=next_rev,
                )
                db.add(apr)
                new_approvals.append(apr)

    db.commit()

    quota_note = (
        f"Đang có {article_count} cơ hội bài ARTICLE (mục tiêu mềm: {project.soft_article_min}–{project.soft_article_max} bài; "
        f"{non_article_count} tài nguyên TOOL/DOWNLOAD/SERVICE không tính vào quota; {gap_count} khoảng trống nghiên cứu). "
        "Hệ thống không ép tạo đủ 5–7 bài nếu chưa đủ nhu cầu độc lập và bằng chứng."
    )

    return {
        "revision": next_rev,
        "plan_mode": "VERIFIED_CANDIDATE" if has_global_organic else "DRAFT_SERP_NOT_VERIFIED",
        "serp_status": "SERP_VERIFIED" if has_global_organic else "SERP_NOT_VERIFIED",
        "article_quota": {
            "soft_min": project.soft_article_min,
            "soft_max": project.soft_article_max,
            "current_articles": article_count,
            "non_article_assets_excluded": non_article_count,
            "research_gaps": gap_count,
            "note": quota_note,
        },
        "mappings_count": len(created_mappings),
        "opportunities_count": len(created_opportunities),
        "approvals_created": len(new_approvals),
    }
