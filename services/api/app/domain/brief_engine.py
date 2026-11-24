from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.domain.eligibility_policy import (
    POLICY_VERSION,
    evaluate_mapping_eligibility,
    load_project_policy_context,
)
from app.domain.brief_writer import write_brief, mock_brief
from app.knowledge import load_thresholds
from app.models import BriefVersion, ContentBrief, KeywordMapping, Project

# Exact 13 Writing Formulas from V1.6 Section 5.8
WRITING_FORMULAS: list[dict[str, str]] = [
    {"id": "AIDA", "name": "AIDA", "description": "Attention – Interest – Desire – Action: dẫn dắt người đọc từ chú ý tới hành động."},
    {"id": "PAS", "name": "PAS", "description": "Problem – Agitate – Solution: đánh trúng nỗi đau thực tế rồi đưa giải pháp cụ thể."},
    {"id": "BAB", "name": "BAB", "description": "Before – After – Bridge: đối chiếu trạng thái trước/sau và cầu nối giải pháp."},
    {"id": "FAB", "name": "FAB", "description": "Features – Advantages – Benefits: chuyển đổi tính năng thành lợi ích trực tiếp."},
    {"id": "4P", "name": "4P", "description": "Picture – Promise – Prove – Push: phác họa bối cảnh, cam kết, chứng minh bằng chứng và thúc đẩy."},
    {"id": "APP", "name": "APP", "description": "Agree – Promise – Preview: đồng cảm nhanh, hứa hẹn giá trị, xem trước bố cục bài."},
    {"id": "QUEST", "name": "QUEST", "description": "Qualify – Understand – Educate – Stimulate – Transition: lọc đúng độc giả và giáo dục có chiều sâu."},
    {"id": "ACC", "name": "ACC", "description": "Awareness – Comprehension – Conviction: xây dựng nhận thức tới niềm tin dựa trên bằng chứng."},
    {"id": "SLAP", "name": "SLAP", "description": "Stop – Look – Act – Purchase: dừng chú ý, làm rõ giá trị, dẫn tới hành động."},
    {"id": "4U", "name": "4U", "description": "Useful – Urgent – Unique – Ultra-specific: tối ưu tiêu đề và lời mở bài sắc bén."},
    {"id": "Checklist", "name": "Checklist", "description": "Cấu trúc danh mục kiểm tra từng bước rõ ràng, dễ rà soát và áp dụng ngay."},
    {"id": "Q&A", "name": "Q&A", "description": "Hỏi – Đáp trực diện các thắc mắc phổ biến theo đúng Search Intent."},
    {"id": "Storytelling", "name": "Storytelling", "description": "Mở đầu và dẫn dắt bằng tình huống thực tế giúp người đọc dễ liên hệ."},
]

# Exact 16 Reader Engagement Tactics from V1.6 Section 5.8
ENGAGEMENT_TACTICS: list[dict[str, Any]] = [
    {"number": 1, "code": "T01", "text": "Mở đầu bằng câu hỏi phù hợp nhu cầu."},
    {"number": 2, "code": "T02", "text": "Tiêu đề gợi tò mò/có số liệu cụ thể khi có căn cứ."},
    {"number": 3, "code": "T03", "text": "Gợi ý các phiên bản tiêu đề để biên tập lựa chọn."},
    {"number": 4, "code": "T04", "text": "Đưa thông tin quan trọng lên trước khi phù hợp Search Intent."},
    {"number": 5, "code": "T05", "text": "Giới thiệu trước những vấn đề bài sẽ giải quyết."},
    {"number": 6, "code": "T06", "text": "Mở bài bằng tình huống/câu chuyện có liên hệ thực tế."},
    {"number": 7, "code": "T07", "text": "Ngôn ngữ đơn giản, dễ hiểu, không lạm dụng thuật ngữ."},
    {"number": 8, "code": "T08", "text": "Câu ngắn, chủ động, dễ quét nội dung."},
    {"number": 9, "code": "T09", "text": "Từ ngữ nhấn mạnh có kiểm soát; không thổi phồng."},
    {"number": 10, "code": "T10", "text": "Heading tập trung vào lợi ích và vấn đề người đọc."},
    {"number": 11, "code": "T11", "text": "Biến thể từ khóa/ngữ nghĩa tự nhiên, không nhồi nhét."},
    {"number": 12, "code": "T12", "text": "Ví dụ, dữ liệu, case có nguồn đáng tin; không bịa số."},
    {"number": 13, "code": "T13", "text": "Hình ảnh/video/bảng minh họa khi thật sự hữu ích."},
    {"number": 14, "code": "T14", "text": "Internal link liên quan và có lý do điều hướng."},
    {"number": 15, "code": "T15", "text": "Ngắt nhịp bằng bảng, câu hỏi, ví dụ hoặc visual phù hợp."},
    {"number": 16, "code": "T16", "text": "CTA cuối bài rõ ràng, đúng mục tiêu và không gây hiểu nhầm."},
]


class BriefEligibilityError(ValueError):
    def __init__(self, detail: dict[str, Any]):
        super().__init__(detail.get("reason", "Không đủ điều kiện tạo Content Brief chính thức."))
        self.detail = detail


def _select_writing_strategy(mapping: KeywordMapping) -> dict[str, Any]:
    kw = mapping.primary_keyword
    page_type = mapping.page_type or "ARTICLE"
    intent_low = (mapping.intent or "").lower()

    if page_type in ("TOOL", "DOWNLOAD"):
        primary = "FAB"
        supporting = ["4U", "Checklist"]
        rationale = f"Trang dạng {page_type} cần làm rõ lợi ích sử dụng ngay (FAB), thông điệp cụ thể (4U) và các bước thao tác ngắn gọn (Checklist)."
        tactics = [ENGAGEMENT_TACTICS[3], ENGAGEMENT_TACTICS[6], ENGAGEMENT_TACTICS[7], ENGAGEMENT_TACTICS[12], ENGAGEMENT_TACTICS[15]]
    elif "commercial" in intent_low or "transactional" in intent_low or page_type in ("SERVICE", "PRODUCT"):
        primary = "PAS"
        supporting = ["4P", "AIDA"]
        rationale = "Ý định tìm kiếm thiên về đánh giá/chuyển đổi: cần gọi đúng vấn đề thực tế (PAS) rồi chứng minh bằng chứng đáng tin trước CTA (4P/AIDA)."
        tactics = [ENGAGEMENT_TACTICS[0], ENGAGEMENT_TACTICS[5], ENGAGEMENT_TACTICS[8], ENGAGEMENT_TACTICS[11], ENGAGEMENT_TACTICS[13], ENGAGEMENT_TACTICS[15]]
    elif any(w in kw.lower() for w in ("là gì", "quy định", "cách", "hướng dẫn", "khi nào")):
        primary = "APP"
        supporting = ["Checklist", "Q&A"]
        rationale = "Người tìm kiếm muốn câu trả lời nhanh, chính xác và áp dụng được ngay: APP giữ chân từ đoạn mở bài, Checklist & Q&A giúp quét dễ."
        tactics = [ENGAGEMENT_TACTICS[3], ENGAGEMENT_TACTICS[4], ENGAGEMENT_TACTICS[6], ENGAGEMENT_TACTICS[9], ENGAGEMENT_TACTICS[10], ENGAGEMENT_TACTICS[14]]
    else:
        primary = "QUEST"
        supporting = ["PAS", "Storytelling"]
        rationale = "Chủ đề chuyên môn cần lọc đúng đối tượng độc giả, giáo dục có hệ thống (QUEST) kết hợp tình huống thực tế để tăng độ tin cậy."
        tactics = [ENGAGEMENT_TACTICS[0], ENGAGEMENT_TACTICS[4], ENGAGEMENT_TACTICS[5], ENGAGEMENT_TACTICS[9], ENGAGEMENT_TACTICS[11], ENGAGEMENT_TACTICS[15]]

    openings = [
        f"Tình huống thực tế: Khi xử lý '{kw}', nhiều bạn dễ bỏ sót điểm mấu chốt gây tốn thời gian — dưới đây là hướng dẫn có kiểm chứng từng bước.",
        f"Câu hỏi trực diện: Bạn cần giải quyết vấn đề gì về '{kw}' trước tiên? Hãy xem tóm tắt nhanh 3 điểm cốt lõi ngay bên dưới.",
    ]

    return {
        "scope": "WHOLE_ARTICLE",
        "per_heading_enforcement": False,
        "editor_autonomy_note": "Chiến thuật viết áp dụng ở cấp TOÀN BÀI; Content Writer chủ động trình bày từng mục H2/H3 tự nhiên, không ép gán công thức cho từng heading.",
        "primary_formula": primary,
        "supporting_formulas": supporting[:2],
        "rationale": rationale,
        "opening_ideas": openings,
        "engagement_tactics": tactics,
        "available_formulas_count": len(WRITING_FORMULAS),
        "available_tactics_count": len(ENGAGEMENT_TACTICS),
    }


def generate_content_briefs(
    db: Session,
    project: Project,
    *,
    allow_draft: bool = True,
    mapping_ids: list[str] | None = None,
) -> dict[str, Any]:
    """
    Generate Content Briefs strictly enforcing the authoritative per-mapping eligibility policy:
    - ZERO BYPASS: Even when `allow_draft=True`, a mapping receives `OFFICIAL` ONLY if
      `evaluate_mapping_eligibility(...)["eligible_official"]` is True!
    - When `allow_draft=False`, ALL selected mappings (or at least 1 if none specified) MUST
      pass full Phase 1 eligibility; if an explicit ineligible mapping_id is requested or
      zero eligible mappings exist, raises `BriefEligibilityError` (HTTP 400).
    - Preserves existing ContentBrief IDs and BriefVersion audit history.
    """
    ctx = load_project_policy_context(db, project)

    query = db.query(KeywordMapping).filter(
        KeywordMapping.project_id == project.id,
        KeywordMapping.is_archived == False,  # noqa: E712
    )
    if mapping_ids:
        query = query.filter(KeywordMapping.id.in_(mapping_ids))
    from app.domain.keyword_expansion import enabled
    if enabled(project):query=query.filter(KeywordMapping.volume > 0)
    mappings = query.order_by(KeywordMapping.priority.asc(), KeywordMapping.created_at.asc()).all()

    if not mappings:
        raise BriefEligibilityError(
            {
                "code": "NO_KEYWORD_MAPPINGS",
                "reason": "Chưa có Keyword Mapping hợp lệ nào để tạo Content Brief.",
                "impact": "Không thể sinh Content Brief khi chưa lập kế hoạch từ khóa.",
                "solution": "Hoàn thành Bước 06 (Lập Keyword Mapping) trước khi tạo Brief.",
                "next_action": "Mở Bước 06 để lập Keyword Mapping.",
                "cta_label": "Mở Bước 06",
                "cta_href": "/steps/06-mapping",
            }
        )

    decisions = {km.id: evaluate_mapping_eligibility(project, km, ctx) for km in mappings}
    from app.domain.research_business import mapping_handoff, record_decision
    for mapping in mappings:
        handoff=mapping_handoff(db,project,mapping)
        if not mapping.is_approved:record_decision(db,project.id,"V-CHUA-DUYET",f"{mapping.primary_keyword}: chưa duyệt mapping hiện hành.",needs_review=True,mapping_id=mapping.id)
        analysis=handoff.get("analysis",{})
        if (handoff.get("funnel_stage") or enabled(project)) and (analysis.get("decision") != "ARTICLE" or analysis.get("selected_batch_id") != decisions[mapping.id]["serp_evidence"].get("selected_batch_id")):
            record_decision(db,project.id,"V-THIEU-DU-LIEU",f"{mapping.primary_keyword}: cần phân tích SERP hiện hành trước khi viết chính thức.",needs_review=True,mapping_id=mapping.id)
            decisions[mapping.id] = {**decisions[mapping.id], "eligible_official":False, "recommended_content_status":"RESEARCH_REQUIRED", "blockers":[*decisions[mapping.id]["blockers"], {"code":"V-THIEU-DU-LIEU", "reason":"Cổng nghiệp vụ V2: cần phân tích SERP hiện hành kết luận đủ điều kiện bài viết.", "impact":"Chỉ được tạo bản nháp.", "solution":"Chạy F5 và duyệt mapping hiện hành."}]}
    eligible_list = [km for km in mappings if decisions[km.id]["eligible_official"]]
    ineligible_list = [km for km in mappings if not decisions[km.id]["eligible_official"]]

    if not allow_draft:
        # Strict mode: if explicit mapping_ids included any ineligible item OR none are eligible -> FAIL CLOSED!
        if (mapping_ids and ineligible_list) or not eligible_list:
            first_bad = ineligible_list[0] if ineligible_list else mappings[0]
            first_blockers = decisions[first_bad.id]["blockers"]
            primary_blocker = first_blockers[0] if first_blockers else {
                "code": "BRIEF_NOT_ELIGIBLE",
                "reason": f"Mapping '{first_bad.primary_keyword}' chưa đạt đủ Quality Gates để tạo Brief CHÍNH THỨC.",
                "impact": "Không được phép phát hành Brief chính thức khi còn gate chưa đạt.",
                "solution": "Hoàn thiện bằng chứng SERP, chỉ số Semrush và phê duyệt phiên bản Mapping hiện tại.",
                "next_action": "Xem chi tiết điểm nghẽn từng Mapping tại Bước 06.",
                "cta_label": "Mở Bước 06",
                "cta_href": "/steps/06-mapping",
            }
            raise BriefEligibilityError(
                {
                    **primary_blocker,
                    "ineligible_mappings": [
                        {
                            "mapping_id": km.id,
                            "primary_keyword": km.primary_keyword,
                            "blockers": decisions[km.id]["blockers"],
                        }
                        for km in ineligible_list
                    ],
                }
            )

    created_or_updated: list[ContentBrief] = []
    project_tag = (project.topic_pillar_code or project.code or "PRJ").upper()

    for idx, km in enumerate(mappings, start=1):
        if km.page_type != "ARTICLE":
            continue
        if allow_draft and not km.is_approved and not load_thresholds()["allow_pending_drafts"]:
            continue
        dec = decisions[km.id]
        is_official = bool(dec["eligible_official"])
        if not is_official and not allow_draft:
            continue

        brief_mode = "OFFICIAL" if is_official else "DRAFT"
        status = "READY_FOR_BRIEF" if is_official else dec["recommended_content_status"]
        from app.domain.research_business import article_code_for
        br_code = article_code_for(db, project.id, km.id)
        secondary_kws = json.loads(km.secondary_keywords_json or "[]")
        writing_strategy = _select_writing_strategy(km)
        serp_ev = dec["serp_evidence"]

        metrics_obj = {
            "volume": km.volume,
            "kd": km.kd,
            "intent": km.intent,
            "metrics_source": km.metrics_source,
            "metrics_evidence_id": km.metrics_evidence_id,
            "serp_tier": dec["serp_tier"],
            "top10_verified": dec["top10_verified"],
            "valid_organic_urls": serp_ev["valid_organic_count"],
            "selected_serp_batch_id": serp_ev.get("selected_batch_id"),
            "serp_batch_ids": serp_ev["batch_ids"],
            "snapshot_identity": serp_ev.get("snapshot_identity"),
            "market": project.market,
            "policy_version": POLICY_VERSION,
        }

        if serp_ev["serp_sufficient"]:
            intent_status = "VERIFIED"
            if dec["top10_verified"]:
                intent_summary = (
                    f"{km.intent or 'Đối chiếu SERP'} — Top 10 SERP đã kiểm chứng đầy đủ "
                    f"({serp_ev['valid_organic_count']} URL organic hợp lệ, thị trường {project.market})."
                )
            else:
                intent_summary = (
                    f"{km.intent or 'Đối chiếu SERP'} — Đã kiểm chứng {serp_ev['valid_organic_count']} URL organic "
                    f"(chưa đủ Top 10 hoàn chỉnh; thiếu vị trí {serp_ev['top10_positions_missing']})."
                )
        else:
            intent_status = "ASSUMED"
            intent_summary = (
                f"{km.intent or 'Informational'} — GIẢ ĐỊNH ({dec['serp_tier']}: {serp_ev['sufficiency_reason']})"
            )

        audience = project.target_audience or "Chưa khai báo đối tượng độc giả ở Bước 01 (cần bổ sung)."
        goal = (
            f"Giải quyết triệt để nhu cầu tìm kiếm quanh '{km.primary_keyword}' và phục vụ mục tiêu: {project.business_goal}."
            if project.business_goal
            else f"Giải quyết nhu cầu tìm kiếm cốt lõi quanh '{km.primary_keyword}' dựa trên bằng chứng đã thu thập."
        )

        # Seed dự phòng theo keyword nguồn, chỉ xuất bản dự phòng nếu AI thất bại.
        seed = mock_brief({"primary_keyword":km.primary_keyword,"secondary_keywords":secondary_kws,"target_audience":audience,"other_mappings":[]})
        title_variants = seed["title_variants"]
        outline = seed["outline"]

        serp_check_note = (
            f"Đã xác minh Top 10 SERP đầy đủ ({serp_ev['valid_organic_count']} URL organic)."
            if dec["top10_verified"]
            else (
                f"Đã đối chiếu {serp_ev['valid_organic_count']} URL organic (chưa đủ Top 10 hoàn chỉnh)."
                if serp_ev["serp_sufficient"]
                else f"LƯU Ý DỰ THẢO ({dec['serp_tier']}): Chưa đủ bằng chứng SERP — không tuyên bố đã kiểm tra Top 10."
            )
        )
        checklist = [
            f"Từ khóa chính '{km.primary_keyword}' xuất hiện tự nhiên ở Title, H1, URL và đoạn mở đầu.",
            "Không bịa số liệu thống kê, quy định hoặc case study chưa có nguồn kiểm chứng.",
            "Biến thể từ khóa phụ được lồng ghép tự nhiên theo ngữ nghĩa, không nhồi nhét.",
            "Bố cục rõ ràng, câu ngắn chủ động, có bảng/ví dụ ngắt nhịp khi thực sự hữu ích.",
            "CTA cuối bài phù hợp mục tiêu kinh doanh và trạng thái nhận thức của người đọc.",
            serp_check_note,
        ]

        internal_links = []

        # Match existing brief by stable keyword_mapping_id first, then fallback to br_code
        existing = (
            db.query(ContentBrief)
            .filter(ContentBrief.project_id == project.id, ContentBrief.keyword_mapping_id == km.id)
            .first()
        )

        if existing:
            brief = existing
            brief.version += 1
        else:
            brief = ContentBrief(project_id=project.id, br_code=br_code, version=1)
            db.add(brief)

        brief.keyword_mapping_id = km.id
        brief.mapping_revision = km.revision
        brief.mapping_fingerprint = dec.get("live_fingerprint") or km.content_fingerprint
        brief.is_stale = False
        brief.eligibility_snapshot_json = json.dumps(
            {
                "policy_version": POLICY_VERSION,
                "eligible_official": is_official,
                "serp_tier": dec["serp_tier"],
                "top10_verified": dec["top10_verified"],
                "approval_state": dec["approval_state"],
                "evidence_refs": dec["evidence_refs"],
                "blockers": dec["blockers"],
                "warnings": dec["warnings"],
            },
            ensure_ascii=False,
        )
        brief.content_type = km.page_type
        brief.priority = km.priority
        brief.brief_mode = brief_mode
        brief.status = status
        brief.primary_keyword = km.primary_keyword
        brief.secondary_keywords_json = json.dumps(secondary_kws, ensure_ascii=False)
        brief.metrics_json = json.dumps(metrics_obj, ensure_ascii=False)
        brief.proposed_url = km.proposed_url
        brief.target_audience = audience
        brief.search_intent_status = intent_status
        brief.search_intent_summary = intent_summary
        brief.article_goal = goal
        brief.seo_title = title_variants[0]
        brief.h1 = seed["h1"]
        brief.meta_description = seed["meta_description"]
        brief.cta = seed["cta"]
        brief.internal_links_json = json.dumps(internal_links, ensure_ascii=False)
        brief.outline_json = json.dumps(outline, ensure_ascii=False)
        brief.seo_checklist_json = json.dumps(checklist, ensure_ascii=False)
        brief.writing_strategy_json = json.dumps(
            {**writing_strategy, "title_variants": title_variants}, ensure_ascii=False
        )
        payload, writer_errors = write_brief(db, project, km, db.query(KeywordMapping).filter_by(project_id=project.id, is_archived=False).all(), secondary_keywords=secondary_kws, serp_evidence=serp_ev)
        brief.seo_title = payload["title_variants"][0]
        brief.h1 = payload["h1"]
        brief.meta_description = payload["meta_description"]
        brief.article_goal = payload["article_goal"]
        brief.target_audience = payload["target_audience"]
        brief.cta = payload["cta"]
        brief.outline_json = json.dumps(payload["outline"], ensure_ascii=False)
        brief.internal_links_json = json.dumps(payload["internal_links"], ensure_ascii=False)
        brief.seo_checklist_json = json.dumps(payload["checklist"] + payload["legal_sources"], ensure_ascii=False)
        if payload.get("primary_formula") in {f["id"] for f in WRITING_FORMULAS}:writing_strategy["primary_formula"]=payload["primary_formula"]
        selected_tactics=[t for t in ENGAGEMENT_TACTICS if t["code"] in payload.get("tactic_codes",[])]
        if 3 <= len(selected_tactics) <= 6:writing_strategy["engagement_tactics"]=selected_tactics
        writing_strategy.update({"title_variants":payload["title_variants"], "faq":payload["faq"], "legal_sources":payload["legal_sources"], "word_count_reference":payload["word_count_reference"], "serp_references":payload["serp_references"], "generation_source":"AI" if not writer_errors else "FALLBACK", "quality_errors":writer_errors})
        brief.writing_strategy_json = json.dumps(writing_strategy, ensure_ascii=False)
        if writer_errors:
            brief.brief_mode = "DRAFT"
            brief.status = "NEEDS_HUMAN_EDIT"
        db.flush()

        db.add(
            BriefVersion(
                brief_id=brief.id,
                version=brief.version,
                payload_json=json.dumps(serialize_brief(brief), ensure_ascii=False),
            )
        )
        created_or_updated.append(brief)

    db.commit()
    return {
        "policy_version": POLICY_VERSION,
        "backlog": [{"id": m.id, "primary_keyword": m.primary_keyword, "page_type": m.page_type} for m in mappings if m.page_type != "ARTICLE"],
        "briefs": [serialize_brief(b) for b in created_or_updated],
        "official_count": len([b for b in created_or_updated if b.brief_mode == "OFFICIAL"]),
        "draft_count": len([b for b in created_or_updated if b.brief_mode != "OFFICIAL"]),
        "serp_verified": any(decisions[km.id]["serp_evidence"]["serp_sufficient"] for km in mappings),
    }


def serialize_brief(b: ContentBrief, *, freshness: dict[str, Any] | None = None) -> dict[str, Any]:
    eff_stale = freshness["effective_is_stale"] if freshness is not None else bool(b.is_stale)
    eff_mode = freshness["effective_brief_mode"] if freshness is not None else b.brief_mode
    eff_status = freshness["effective_status"] if freshness is not None else b.status
    stale_reasons = freshness["stale_reasons"] if freshness is not None else ([] if not b.is_stale else ["Brief đã cũ do thay đổi Mapping hoặc bằng chứng."])
    return {
        "id": b.id,
        "project_id": b.project_id,
        "keyword_mapping_id": b.keyword_mapping_id,
        "mapping_revision": b.mapping_revision,
        "mapping_fingerprint": b.mapping_fingerprint,
        "is_stale": bool(eff_stale),
        "stale_reasons": stale_reasons,
        "recorded_brief_mode": b.brief_mode,
        "eligibility_snapshot": json.loads(b.eligibility_snapshot_json or "{}"),
        "br_code": b.br_code,
        "content_type": b.content_type,
        "priority": b.priority,
        "brief_mode": eff_mode,
        "status": eff_status,
        "primary_keyword": b.primary_keyword,
        "secondary_keywords": json.loads(b.secondary_keywords_json or "[]"),
        "metrics": json.loads(b.metrics_json or "{}"),
        "proposed_url": b.proposed_url,
        "target_audience": b.target_audience,
        "search_intent_status": b.search_intent_status,
        "search_intent_summary": b.search_intent_summary,
        "article_goal": b.article_goal,
        "seo_title": b.seo_title,
        "h1": b.h1,
        "meta_description": b.meta_description,
        "cta": b.cta,
        "internal_links": json.loads(b.internal_links_json or "[]"),
        "outline": json.loads(b.outline_json or "[]"),
        "seo_checklist": json.loads(b.seo_checklist_json or "[]"),
        "writing_strategy": json.loads(b.writing_strategy_json or "{}"),
        "version": b.version,
        "created_at": b.created_at.isoformat() if b.created_at else None,
        "updated_at": b.updated_at.isoformat() if b.updated_at else None,
    }
