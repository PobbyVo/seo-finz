"""Bàn giao BRIEF_WRITER và F7 nghiệp vụ, đặt trên lớp eligibility hiện có."""

from __future__ import annotations
import json
import re
from typing import Any
from pydantic import BaseModel, Field
from app.domain.taxonomy_parser import normalize_text


class Heading(BaseModel):
    level: str = "H2"
    heading: str
    notes: str = ""
    children: list[dict[str, str]] = Field(default_factory=list)


class InternalLink(BaseModel):
    anchor: str
    target_url: str
    reason: str


class WriterOutput(BaseModel):
    content_type: str = "ARTICLE"
    article_goal: str
    target_audience: str
    cta: str
    title_variants: list[str] = Field(min_length=2, max_length=2)
    h1: str
    meta_description: str
    word_count_reference: str
    internal_links: list[InternalLink]
    outline: list[Heading] = Field(min_length=1)
    faq: list[str]
    serp_references: list[dict[str, str]]
    legal_sources: list[str]
    checklist: list[str]
    primary_formula: str = "APP"
    tactic_codes: list[str] = Field(
        default_factory=lambda: ["T04", "T07", "T12", "T14"]
    )


def mock_brief(ctx: dict[str, Any]) -> dict[str, Any]:
    """Nội dung minh họa offline từ keyword nguồn; không sinh bằng chứng hay tỷ lệ."""
    kw = ctx["primary_keyword"]
    secondary = ctx.get("secondary_keywords", [])
    stage = ctx.get("funnel_stage", "TOFU")
    legal = any(
        k in normalize_text(kw + " " + " ".join(secondary))
        for k in ("lương", "thuế", "bhxh", "lãi suất", "vay", "bảo hiểm")
    )
    headings = [
        {
            "heading": kw[0].upper() + kw[1:],
            "notes": f'Trả lời ngay câu hỏi “{kw}”. Làm rõ {ctx.get("content_title") or "phạm vi và tình huống của bạn"}; phân biệt định nghĩa với nhận định.',
        }
    ]
    for keyword in secondary:
        headings.append(
            {
                "heading": keyword[0].upper() + keyword[1:],
                "notes": f"Giải đáp “{keyword}” trong phạm vi {kw}; minh họa bằng tiền Việt, nêu rõ giả định. Nếu thiếu dữ liệu, ghi chưa xác minh; không tự thêm tỷ lệ.",
            }
        )
    if legal:
        headings.append(
            {
                "heading": "Nguồn pháp lý và giả định cần kiểm chứng",
                "notes": "Tra văn bản gốc về thuế TNCN, BHXH và nghĩa vụ liên quan; ghi số hiệu, ngày hiệu lực, cơ quan ban hành. Không ghi tỷ lệ từ trí nhớ.",
            }
        )
    return WriterOutput(
        article_goal=f"Giúp bạn hiểu và xử lý {kw} trong tình huống thực tế.",
        target_audience=ctx.get("target_audience") or "Người trẻ đi làm",
        cta={
            "TOFU": "Đọc tiếp bài chuyên sâu có liên quan.",
            "MOFU": "Lưu bài và tham khảo khóa học tài chính cá nhân miễn phí.",
            "BOFU": "Đăng ký khóa học tài chính cá nhân miễn phí.",
        }.get(stage, "Đọc tiếp bài liên quan."),
        title_variants=[
            kw[0].upper() + kw[1:],
            (
                (kw[0].upper() + kw[1:] + " — Giải đáp")
                if len(kw) + 11 <= 60
                else kw[0].upper() + kw[1:] + "?"
            ),
        ],
        h1=kw[0].upper() + kw[1:],
        meta_description=f"Hiểu {kw}. Xem hướng dẫn, ví dụ có giả định và những điểm bạn cần kiểm tra trước khi áp dụng."[
            :160
        ],
        word_count_reference="Chưa xác minh độ dài từ các bài SERP đã đọc.",
        internal_links=[
            InternalLink(
                anchor=m["primary_keyword"],
                target_url=m["proposed_url"],
                reason="Đọc sâu nhu cầu liên quan trong cùng chủ đề.",
            )
            for m in ctx.get("other_mappings", [])
            if m.get("page_type") == "ARTICLE"
        ],
        outline=[Heading(**h) for h in headings],
        faq=secondary,
        serp_references=[],
        legal_sources=(
            [
                "Cần kiểm văn bản gốc: số hiệu, ngày hiệu lực, thuế TNCN/BHXH hoặc quy định liên quan; chưa xác minh."
            ]
            if legal
            else []
        ),
        checklist=[
            f"Mở bài trả lời ngay {kw}.",
            "Ví dụ tiền Việt phải nêu giả định; kiểm nguồn và ngày hiệu lực.",
            "Rà soát heading, mobile, alt ảnh và internal link.",
        ],
    ).model_dump()


def business_quality(
    payload: dict,
    *,
    primary_keyword: str,
    secondary_keywords: list[str],
    allowed_urls: set[str],
    other_outlines: list | None = None,
) -> list[str]:
    errors = []
    from app.domain.brief_engine import WRITING_FORMULAS, ENGAGEMENT_TACTICS

    if payload.get("primary_formula") not in {r["id"] for r in WRITING_FORMULAS}:
        errors.append("F7-TITLE: Công thức viết không thuộc thư viện được duyệt.")
    tactic_codes = payload.get("tactic_codes", [])
    if not 3 <= len(tactic_codes) <= 6 or not set(tactic_codes).issubset(
        {t["code"] for t in ENGAGEMENT_TACTICS}
    ):
        errors.append("F7-TITLE: Cần 3–6 chiến thuật trong thư viện.")
    words = set(re.findall(r"\w+", normalize_text(primary_keyword)))
    for title in payload.get("title_variants", []):
        if (
            len(title) > 60
            or not words.issubset(set(re.findall(r"\w+", normalize_text(title))))
            or re.search(r"\bP\d{2}\b", title)
        ):
            errors.append("F7-TITLE: Title ≤60, đủ từ key chính và không mã nội bộ.")
    if len(payload.get("meta_description", "")) > 160:
        errors.append("F7-META: Meta quá 160 ký tự.")
    headings = (
        " ".join(
            h.get("heading", "")
            + " "
            + " ".join(c.get("heading", "") for c in h.get("children", []))
            for h in payload.get("outline", [])
        )
        + " "
        + " ".join(payload.get("faq", []))
    )
    for kw in secondary_keywords:
        if normalize_text(kw) not in normalize_text(headings):
            errors.append(f"F7-KEY-PHU: Chưa có vị trí cho {kw}.")
    for link in payload.get("internal_links", []):
        if link["target_url"] not in allowed_urls:
            errors.append("F7-LINK: Link không có trong mapping.")
    if any(
        k in normalize_text(primary_keyword + " " + " ".join(secondary_keywords))
        for k in ("lương", "thuế", "bhxh", "lãi suất", "vay")
    ):
        if not payload.get("legal_sources"):
            errors.append("F7-NGUON: Thiếu nguồn pháp lý cần kiểm.")
        text = json.dumps(payload, ensure_ascii=False)
        if re.search(r"\d+(?:[.,]\d+)?\s*%", text) and not any(
            re.search(r"\d+[/\-]\d+", source)
            for source in payload.get("legal_sources", [])
        ):
            errors.append("F7-NGUON: Tỷ lệ cụ thể chưa có văn bản dẫn nguồn.")
    current = {normalize_text(h.get("heading", "")) for h in payload.get("outline", [])}
    for outline in other_outlines or []:
        other = {normalize_text(h.get("heading", "")) for h in outline}
        if current and len(current & other) / len(current | other) > 0.8:
            errors.append("F7-TRUNG-OUTLINE: Outline quá giống bài khác.")
    if payload.get("content_type") != "ARTICLE":
        errors.append("F7-BACKLOG-LAN: Backlog không được sinh brief bài viết.")
    return list(dict.fromkeys(errors))


def write_brief(db, project, mapping, mappings, *, secondary_keywords, serp_evidence):
    from app.ai.gateway import gateway
    from app.ai.prompts import BRIEF_WRITER_SYSTEM_PROMPT
    from app.knowledge import ROOT, load_thresholds
    from app.models import SourceKeyword, EvidenceRow
    from app.ai.errors import AIProviderError

    source = (
        db.query(SourceKeyword)
        .filter_by(
            project_id=project.id,
            keyword_normalized=normalize_text(mapping.primary_keyword),
        )
        .first()
    )
    rows = (
        db.query(EvidenceRow)
        .filter_by(
            project_id=project.id,
            keyword_normalized=normalize_text(mapping.primary_keyword),
        )
        .all()
    )
    ctx = {
        "task": "BRIEF_WRITER",
        "primary_keyword": mapping.primary_keyword,
        "secondary_keywords": secondary_keywords,
        "content_title": source.content_title if source else "",
        "funnel_stage": source.funnel_stage if source else "TOFU",
        "target_audience": project.target_audience,
        "mapping": {
            "page_type": mapping.page_type,
            "volume": mapping.volume,
            "kd": mapping.kd,
            "intent": mapping.intent,
            "priority": mapping.priority,
            "url": mapping.proposed_url,
        },
        "serp_evidence": serp_evidence,
        "evidence_rows": [
            {
                "id": r.id,
                "source_row": r.source_row_number,
                "url": r.organic_url,
                "title": r.organic_title,
                "raw": json.loads(r.raw_row_json or "{}"),
            }
            for r in rows
        ],
        "other_mappings": [
            {
                "primary_keyword": m.primary_keyword,
                "proposed_url": m.proposed_url,
                "page_type": m.page_type,
            }
            for m in mappings
            if m.id != mapping.id
        ],
        "schema": WriterOutput.model_json_schema(),
    }
    from app.domain.research_business import mapping_handoff

    ctx["handoff"] = mapping_handoff(db, project, mapping)
    from app.domain.brief_engine import WRITING_FORMULAS, ENGAGEMENT_TACTICS
    ctx["writing_formulas"] = WRITING_FORMULAS
    ctx["engagement_tactics"] = ENGAGEMENT_TACTICS
    allowed = {m.proposed_url for m in mappings}
    prompt = (
        BRIEF_WRITER_SYSTEM_PROMPT
        + "\nVí dụ tham khảo cấu trúc; số liệu chỉ là ví dụ, cấm sao chép sang dự án:\n"
        + (ROOT / "brief_example.md").read_text()
    )
    errors = []
    payload = None
    invalid_responses = 0
    for attempt in range(load_thresholds()["brief_repair_attempts"] + 1):
        ctx["repair_errors"] = errors
        try:
            result, _ = gateway.generate_structured(
                db,
                project_id=project.id,
                role="BRIEF_WRITER",
                system_prompt=prompt,
                user_prompt=json.dumps(ctx, ensure_ascii=False),
                context=ctx,
                research_cycle=project.research_cycle,
            )
            payload = WriterOutput.model_validate(result.data).model_dump()
        except (AIProviderError, ValueError) as exc:
            errors = ["Phản hồi AI không hợp lệ: " + str(exc)]
            invalid_responses += 1
            if invalid_responses >= 2:
                break
            continue
        errors = business_quality(
            payload,
            primary_keyword=mapping.primary_keyword,
            secondary_keywords=secondary_keywords,
            allowed_urls=allowed,
        )
        urls = [m.proposed_url for m in mappings]
        if len(urls) != len(set(urls)):
            errors.append("F7-LINK: Hai mapping dùng chung URL; sửa ở bước mapping.")
        from app.models import ContentBrief

        other_outlines = [
            json.loads(b.outline_json or "[]")
            for b in db.query(ContentBrief)
            .filter(
                ContentBrief.project_id == project.id,
                ContentBrief.keyword_mapping_id != mapping.id,
            )
            .all()
        ]
        errors += business_quality(
            payload,
            primary_keyword=mapping.primary_keyword,
            secondary_keywords=secondary_keywords,
            allowed_urls=allowed,
            other_outlines=other_outlines,
        )
        errors = list(dict.fromkeys(errors))
        from app.domain.research_business import record_decision

        for message in errors:
            reason = message.split(":", 1)[0]
            if reason.startswith("F7-"):
                record_decision(
                    db,
                    project.id,
                    reason,
                    message,
                    needs_review=True,
                    mapping_id=mapping.id,
                    attempt=attempt + 1,
                )
        if not errors:
            return payload, []
    if payload is None:
        payload = mock_brief(ctx)
    return payload, errors
