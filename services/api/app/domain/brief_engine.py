from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.domain.quality_gates import evaluate_all_gates
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


def _select_writing_strategy(mapping: KeywordMapping, project: Project) -> dict[str, Any]:
    """
    Build whole-article Writing Strategy:
    - 1 primary formula + up to 2 supporting formulas
    - Rationale
    - 1-2 opening hook ideas
    - 3-6 reader engagement tactics at WHOLE-ARTICLE level (NOT forced per H2/H3!).
    """
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
        f"Tình huống thực tế: Khi xử lý '{kw}', nhiều đội ngũ dễ bỏ sót điểm mấu chốt gây tốn thời gian — dưới đây là hướng dẫn có kiểm chứng từng bước.",
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
    Generate Content Briefs strictly enforcing quality gates:
    - OFFICIAL brief ONLY if mapping.is_approved AND SERP verified AND metrics exist.
    - DRAFT allowed when allow_draft=True, explicitly stamped SERP_NOT_VERIFIED / DRAFT.
    - Never hardcodes any demo project name.
    """
    gate_eval = evaluate_all_gates(db, project)
    summary = gate_eval["summary"]

    query = db.query(KeywordMapping).filter(KeywordMapping.project_id == project.id)
    if mapping_ids:
        query = query.filter(KeywordMapping.id.in_(mapping_ids))
    mappings = query.order_by(KeywordMapping.priority.asc(), KeywordMapping.created_at.asc()).all()

    if not mappings:
        raise ValueError("Chưa có Keyword Mapping nào. Vui lòng hoàn thành Bước 06 trước khi tạo Content Brief.")

    if not allow_draft and not summary["can_generate_official_brief"]:
        raise ValueError(
            "Chưa đạt đủ Quality Gates để tạo Content Brief CHÍNH THỨC (cần Keyword Mapping đã phê duyệt, có bằng chứng Semrush và ORGANIC_RESULTS)."
        )

    created_or_updated: list[ContentBrief] = []
    project_tag = (project.topic_pillar_code or project.code or "PRJ").upper()

    for idx, km in enumerate(mappings, start=1):
        is_official = bool(km.is_approved and summary["serp_verified"] and km.volume is not None)
        if not is_official and not allow_draft:
            continue

        brief_mode = "OFFICIAL" if is_official else "DRAFT"
        status = "READY_FOR_BRIEF" if is_official else ("SERP_NOT_VERIFIED" if not summary["serp_verified"] else "PENDING_APPROVAL")
        br_code = f"BR-{project_tag}-{idx:02d}"
        secondary_kws = json.loads(km.secondary_keywords_json or "[]")
        writing_strategy = _select_writing_strategy(km, project)

        metrics_obj = {
            "volume": km.volume,
            "kd": km.kd,
            "intent": km.intent,
            "metrics_source": km.metrics_source,
            "serp_status": km.serp_status,
            "market": project.market,
        }

        intent_status = "VERIFIED" if (km.intent and summary["serp_verified"]) else "ASSUMED"
        intent_summary = (
            f"{km.intent} (đã đối chiếu ORGANIC_RESULTS)"
            if intent_status == "VERIFIED"
            else f"{km.intent or 'Informational'} — GIẢ ĐỊNH (SERP_NOT_VERIFIED, chưa kiểm chứng URL top đầu)"
        )

        audience = project.target_audience or "Chưa khai báo đối tượng độc giả ở Bước 01 (cần bổ sung)."
        goal = (
            f"Giải quyết triệt để nhu cầu tìm kiếm quanh '{km.primary_keyword}' và phục vụ mục tiêu: {project.business_goal}."
            if project.business_goal
            else f"Giải quyết nhu cầu tìm kiếm cốt lõi quanh '{km.primary_keyword}' dựa trên bằng chứng đã thu thập."
        )

        title_variants = [
            f"{km.primary_keyword.capitalize()}: Hướng Dẫn Chi Tiết & Lưu Ý Thực Tế ({project_tag})",
            f"Cách Áp Dụng {km.primary_keyword.capitalize()} Đúng Chuẩn Cho {project.target_audience or 'Người Mới'}",
        ]

        outline = [
            {
                "level": "H2",
                "heading": f"Tổng quan nhanh về {km.primary_keyword}",
                "notes": "Trả lời trực diện câu hỏi cốt lõi ngay phần đầu, trình bày rõ phạm vi bài viết.",
                "children": [
                    {"level": "H3", "heading": f"Bản chất và khi nào cần áp dụng {km.primary_keyword}"},
                    {"level": "H3", "heading": "Những hiểu nhầm thường gặp cần tránh"},
                ],
            },
            {
                "level": "H2",
                "heading": f"Quy trình / Hướng dẫn triển khai {km.primary_keyword} từng bước",
                "notes": "Minh họa bằng bảng tóm tắt hoặc ví dụ thực tế có nguồn xác thực (không bịa số liệu).",
                "children": [
                    {"level": "H3", "heading": "Chuẩn bị thông tin & điều kiện đầu vào"},
                    {"level": "H3", "heading": "Các bước thực hiện và điểm cần kiểm tra"},
                ],
            },
            {
                "level": "H2",
                "heading": f"Tình huống thực tế & câu hỏi thường gặp về {km.primary_keyword}",
                "notes": "Lồng ghép tự nhiên các từ khóa phụ liên quan theo ngữ cảnh.",
                "children": [
                    {"level": "H3", "heading": f"Giải đáp vướng mắc phổ biến ({', '.join(secondary_kws[:2]) or km.primary_keyword})"},
                ],
            },
        ]

        checklist = [
            f"Từ khóa chính '{km.primary_keyword}' xuất hiện tự nhiên ở Title, H1, URL và đoạn mở đầu.",
            "Không bịa số liệu thống kê, quy định hoặc case study chưa có nguồn kiểm chứng.",
            "Biến thể từ khóa phụ được lồng ghép tự nhiên theo ngữ nghĩa, không nhồi nhét.",
            "Bố cục rõ ràng, câu ngắn chủ động, có bảng/ví dụ ngắt nhịp khi thực sự hữu ích.",
            "CTA cuối bài phù hợp mục tiêu kinh doanh và trạng thái nhận thức của người đọc.",
            (
                "Đã xác minh dạng trang qua ORGANIC_RESULTS."
                if summary["serp_verified"]
                else "LƯU Ý DỰ THẢO (SERP_NOT_VERIFIED): Rà soát lại dạng trang thực tế trước khi xuất bản."
            ),
        ]

        internal_links = [
            {
                "anchor": project.topic_pillar_name or project.main_topic or project.name,
                "target_url": f"/{project.topic_pillar_code.lower() or 'topic-pillar'}",
                "reason": "Điều hướng về trang Topic Pillar trung tâm để củng cố cấu trúc cụm chủ đề.",
            }
        ]

        existing = (
            db.query(ContentBrief)
            .filter(ContentBrief.project_id == project.id, ContentBrief.br_code == br_code)
            .first()
        )
        if existing:
            brief = existing
            brief.version += 1
        else:
            brief = ContentBrief(project_id=project.id, br_code=br_code, version=1)
            db.add(brief)

        brief.keyword_mapping_id = km.id
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
        brief.h1 = f"{km.primary_keyword.capitalize()}: Hướng Dẫn Thực Tế & Checklist Áp Dụng"
        brief.meta_description = (
            f"Tìm hiểu {km.primary_keyword} rõ ràng, dễ áp dụng kèm ví dụ thực tế và checklist kiểm tra. "
            f"Phù hợp cho {project.target_audience or 'độc giả cần hướng dẫn có kiểm chứng'}."
        )
        brief.cta = (
            f"Đăng ký nhận tư vấn / tài nguyên chuyên sâu gắn với mục tiêu: {project.business_goal}."
            if project.business_goal
            else f"Tải checklist hoặc xem thêm các bài liên quan trong nhóm {project.topic_pillar_name or project.name}."
        )
        brief.internal_links_json = json.dumps(internal_links, ensure_ascii=False)
        brief.outline_json = json.dumps(outline, ensure_ascii=False)
        brief.seo_checklist_json = json.dumps(checklist, ensure_ascii=False)
        brief.writing_strategy_json = json.dumps(
            {**writing_strategy, "title_variants": title_variants}, ensure_ascii=False
        )
        db.flush()

        # Save version snapshot
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
        "briefs": [serialize_brief(b) for b in created_or_updated],
        "official_count": len([b for b in created_or_updated if b.brief_mode == "OFFICIAL"]),
        "draft_count": len([b for b in created_or_updated if b.brief_mode != "OFFICIAL"]),
        "serp_verified": summary["serp_verified"],
    }


def serialize_brief(b: ContentBrief) -> dict[str, Any]:
    return {
        "id": b.id,
        "project_id": b.project_id,
        "keyword_mapping_id": b.keyword_mapping_id,
        "br_code": b.br_code,
        "content_type": b.content_type,
        "priority": b.priority,
        "brief_mode": b.brief_mode,
        "status": b.status,
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
