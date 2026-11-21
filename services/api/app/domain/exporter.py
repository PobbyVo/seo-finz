from __future__ import annotations

import csv
import html
import io
import json
from datetime import datetime, timezone
from typing import Any

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from sqlalchemy.orm import Session

from app.config import ensure_data_dirs, settings
from app.domain.brief_engine import serialize_brief
from app.domain.eligibility_policy import (
    POLICY_VERSION,
    evaluate_mapping_eligibility,
    load_project_policy_context,
)
from app.domain.mapping_engine import slugify_vi
from app.models import ContentBrief, EvidenceRow, ExportRecord, KeywordMapping, Project


def _safe_project_prefix(project: Project) -> str:
    """Dynamic filename prefix from project code & topic pillar — NEVER hardcodes 'Luong'."""
    code = slugify_vi(project.topic_pillar_code or project.code or "project").upper()
    name_slug = slugify_vi(project.topic_pillar_name or project.name or "seo")[:32]
    return f"{code}_{name_slug}"


def _collect_export_datasets(db: Session, project: Project) -> dict[str, Any]:
    ctx = load_project_policy_context(db, project)
    evidence_rows = (
        db.query(EvidenceRow)
        .filter(
            EvidenceRow.project_id == project.id,
            EvidenceRow.row_type == "METRICS",
            EvidenceRow.is_duplicate == False,  # noqa: E712
        )
        .order_by(EvidenceRow.volume.desc().nullslast())
        .all()
    )
    mappings = (
        db.query(KeywordMapping)
        .filter(KeywordMapping.project_id == project.id, KeywordMapping.is_archived == False)  # noqa: E712
        .order_by(KeywordMapping.priority.asc(), KeywordMapping.created_at.asc())
        .all()
    )
    briefs = (
        db.query(ContentBrief)
        .filter(ContentBrief.project_id == project.id)
        .order_by(ContentBrief.br_code.asc())
        .all()
    )

    mapping_rows: list[dict[str, Any]] = []
    for m in mappings:
        dec = evaluate_mapping_eligibility(project, m, ctx)
        mapping_rows.append(
            {
                "id": m.id,
                "revision": m.revision,
                "content_fingerprint": m.content_fingerprint[:12],
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
                "serp_status": dec["serp_tier"],
                "top10_verified": dec["top10_verified"],
                "content_status": dec["recommended_content_status"],
                "eligible_official": dec["eligible_official"],
                "approval_state": dec["approval_state"],
                "is_approved": dec["approval_state"] == "APPROVED_CURRENT",
                "merge_split_proposal": m.merge_split_proposal,
            }
        )

    return {
        "policy_version": POLICY_VERSION,
        "contains_api_keys": False,
        "project": {
            "id": project.id,
            "code": project.code,
            "name": project.name,
            "pillar_name": project.pillar_name,
            "topic_pillar_code": project.topic_pillar_code,
            "topic_pillar_name": project.topic_pillar_name,
            "market": project.market,
            "language": project.language,
            "version": project.version,
        },
        "keyword_overview": [
            {
                "keyword": r.keyword,
                "volume": r.volume,
                "kd": r.kd,
                "intent": r.intent,
                "cpc": r.cpc,
                "serp_features": r.serp_features,
                "market": r.market,
                "batch_id": r.batch_id,
            }
            for r in evidence_rows
        ],
        "keyword_mapping": mapping_rows,
        "content_briefs": [serialize_brief(b) for b in briefs],
    }


def export_project_bundle(db: Session, project: Project, fmt: str) -> tuple[bytes, str, str, ExportRecord]:
    """
    Export SEO deliverables in XLSX (3 logical sheets), CSV, JSON, or printable HTML.
    Includes truthful verification/staleness labels and NEVER includes API keys or secret refs.
    """
    ensure_data_dirs()
    fmt_clean = fmt.lower().strip()
    if fmt_clean not in {"xlsx", "csv", "json", "html"}:
        raise ValueError("Định dạng xuất phải là xlsx, csv, json hoặc html.")

    data = _collect_export_datasets(db, project)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    prefix = _safe_project_prefix(project)
    briefs = data["content_briefs"]
    mode = (
        "OFFICIAL"
        if (briefs and all(b["brief_mode"] == "OFFICIAL" and not b["is_stale"] for b in briefs))
        else "DRAFT"
    )

    if fmt_clean == "xlsx":
        content = _build_xlsx(data)
        filename = f"{prefix}_SEO_Brief_{mode}_{ts}.xlsx"
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    elif fmt_clean == "csv":
        content = _build_csv(data)
        filename = f"{prefix}_SEO_Brief_{mode}_{ts}.csv"
        media_type = "text/csv; charset=utf-8"
    elif fmt_clean == "json":
        content = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        filename = f"{prefix}_SEO_Brief_{mode}_{ts}.json"
        media_type = "application/json; charset=utf-8"
    else:
        content = _build_printable_html(data).encode("utf-8")
        filename = f"{prefix}_SEO_Brief_{mode}_{ts}.html"
        media_type = "text/html; charset=utf-8"

    out_path = settings.exports_dir / filename
    out_path.write_bytes(content)

    record = ExportRecord(
        project_id=project.id,
        export_format=fmt_clean,
        filename=filename,
        stored_path=str(out_path),
        brief_mode=mode,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return content, filename, media_type, record


def _style_header(ws, headers: list[str]) -> None:
    ws.append(headers)
    header_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
    header_font = Font(bold=True, color="F8FAFC", size=11)
    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(vertical="center", horizontal="left", wrap_text=True)
        ws.column_dimensions[openpyxl.utils.get_column_letter(col_idx)].width = 24


def _build_xlsx(data: dict[str, Any]) -> bytes:
    """Build workbook with exact 3 logical tables: Keyword Overview, Keyword Mapping, SEO Content Brief."""
    wb = openpyxl.Workbook()

    ws1 = wb.active
    ws1.title = "Keyword Overview"
    _style_header(ws1, ["Keyword", "Volume", "KD", "Intent", "CPC", "SERP Features", "Market", "Batch ID"])
    for r in data["keyword_overview"]:
        ws1.append([r["keyword"], r["volume"], r["kd"], r["intent"], r["cpc"], r["serp_features"], r["market"], r["batch_id"]])

    ws2 = wb.create_sheet(title="Keyword Mapping")
    _style_header(
        ws2,
        [
            "Revision",
            "Fingerprint",
            "Primary Keyword",
            "Secondary Keywords",
            "Page Type",
            "Proposed URL",
            "Volume",
            "KD",
            "Intent",
            "Metrics Source",
            "Priority",
            "Business Value",
            "Effort",
            "SERP Tier",
            "Top 10 Verified",
            "Content Status",
            "Approval State",
            "Eligible Official",
            "Merge/Split Proposal",
        ],
    )
    for m in data["keyword_mapping"]:
        ws2.append(
            [
                m["revision"],
                m["content_fingerprint"],
                m["primary_keyword"],
                ", ".join(m["secondary_keywords"]),
                m["page_type"],
                m["proposed_url"],
                m["volume"],
                m["kd"],
                m["intent"],
                m["metrics_source"],
                m["priority"],
                m["business_value"],
                m["effort"],
                m["serp_status"],
                "YES" if m["top10_verified"] else "NO",
                m["content_status"],
                m["approval_state"],
                "YES" if m["eligible_official"] else "NO",
                m["merge_split_proposal"],
            ]
        )

    ws3 = wb.create_sheet(title="SEO Content Brief")
    _style_header(
        ws3,
        [
            "BR ID",
            "Mode",
            "Stale",
            "Mapping Rev",
            "Content Type",
            "Priority",
            "Status",
            "Primary Keyword",
            "Secondary Keywords",
            "Metrics & Source",
            "Proposed URL",
            "Target Audience",
            "Search Intent",
            "Article Goal",
            "SEO Title",
            "H1",
            "Meta Description",
            "CTA",
            "Internal Links",
            "Outline H2/H3",
            "SEO Checklist",
            "Writing Strategy (Whole Article)",
        ],
    )
    for b in data["content_briefs"]:
        ws = b["writing_strategy"]
        ws_summary = (
            f"Chính: {ws.get('primary_formula', '')} | Bổ trợ: {', '.join(ws.get('supporting_formulas', []))} | "
            f"Lý do: {ws.get('rationale', '')} | "
            f"Chiến thuật (toàn bài): {'; '.join(t.get('text', '') for t in ws.get('engagement_tactics', []))}"
        )
        outline_txt = "\n".join(
            f"- {h['level']}: {h['heading']}"
            + (
                "\n" + "\n".join(f"    - {c['level']}: {c['heading']}" for c in h.get("children", []))
                if h.get("children")
                else ""
            )
            for h in b.get("outline", [])
        )
        ws3.append(
            [
                b["br_code"],
                b["brief_mode"],
                "STALE" if b["is_stale"] else "CURRENT",
                b.get("mapping_revision") or "",
                b["content_type"],
                b["priority"],
                b["status"],
                b["primary_keyword"],
                ", ".join(b["secondary_keywords"]),
                json.dumps(b["metrics"], ensure_ascii=False),
                b["proposed_url"],
                b["target_audience"],
                f"[{b['search_intent_status']}] {b['search_intent_summary']}",
                b["article_goal"],
                b["seo_title"],
                b["h1"],
                b["meta_description"],
                b["cta"],
                "; ".join(f"{l['anchor']} -> {l['target_url']}" for l in b.get("internal_links", [])),
                outline_txt,
                "\n".join(b.get("seo_checklist", [])),
                ws_summary,
            ]
        )

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _build_csv(data: dict[str, Any]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "BR ID",
            "Mode",
            "Freshness",
            "Content Type",
            "Priority",
            "Status",
            "Primary Keyword",
            "Secondary Keywords",
            "Proposed URL",
            "Search Intent",
            "SEO Title",
            "H1",
            "Meta Description",
            "Primary Formula",
            "Supporting Formulas",
            "Engagement Tactics (Whole Article)",
        ]
    )
    for b in data["content_briefs"]:
        ws = b["writing_strategy"]
        writer.writerow(
            [
                b["br_code"],
                b["brief_mode"],
                "STALE" if b["is_stale"] else "CURRENT",
                b["content_type"],
                b["priority"],
                b["status"],
                b["primary_keyword"],
                "; ".join(b["secondary_keywords"]),
                b["proposed_url"],
                f"[{b['search_intent_status']}] {b['search_intent_summary']}",
                b["seo_title"],
                b["h1"],
                b["meta_description"],
                ws.get("primary_formula", ""),
                ", ".join(ws.get("supporting_formulas", [])),
                " | ".join(t.get("text", "") for t in ws.get("engagement_tactics", [])),
            ]
        )
    return buf.getvalue().encode("utf-8-sig")


def _build_printable_html(data: dict[str, Any]) -> str:
    proj = data["project"]
    brief_blocks: list[str] = []
    for b in data["content_briefs"]:
        ws = b["writing_strategy"]
        tactics_li = "".join(f"<li>{html.escape(t.get('text', ''))}</li>" for t in ws.get("engagement_tactics", []))
        openings_li = "".join(f"<li>{html.escape(o)}</li>" for o in ws.get("opening_ideas", []))
        outline_li = ""
        for h in b.get("outline", []):
            children = "".join(f"<li><strong>{html.escape(c['level'])}:</strong> {html.escape(c['heading'])}</li>" for c in h.get("children", []))
            outline_li += f"<li><strong>{html.escape(h['level'])}:</strong> {html.escape(h['heading'])}<ul>{children}</ul></li>"
        checklist_li = "".join(f"<li>{html.escape(item)}</li>" for item in b.get("seo_checklist", []))
        stale_flag = " · STALE (CẦN TẠO LẠI)" if b["is_stale"] else ""

        brief_blocks.append(
            f"""
            <section class="brief-card">
              <div class="brief-head">
                <h2>{html.escape(b['br_code'])} — {html.escape(b['primary_keyword'])}</h2>
                <span class="badge">{html.escape(b['brief_mode'])}{html.escape(stale_flag)} · {html.escape(b['status'])} · {html.escape(b['content_type'])} · {html.escape(b['priority'])}</span>
              </div>
              <p><strong>URL đề xuất:</strong> {html.escape(b['proposed_url'])}</p>
              <p><strong>SEO Title:</strong> {html.escape(b['seo_title'])}</p>
              <p><strong>H1:</strong> {html.escape(b['h1'])}</p>
              <p><strong>Meta Description:</strong> {html.escape(b['meta_description'])}</p>
              <p><strong>Search Intent:</strong> [{html.escape(b['search_intent_status'])}] {html.escape(b['search_intent_summary'])}</p>
              <p><strong>Độc giả mục tiêu:</strong> {html.escape(b['target_audience'])}</p>
              <p><strong>Mục tiêu bài viết:</strong> {html.escape(b['article_goal'])}</p>
              <p><strong>CTA:</strong> {html.escape(b['cta'])}</p>
              <h3>Writing Strategy (Cấp toàn bài — không ép từng H2/H3)</h3>
              <p><strong>Công thức chính:</strong> {html.escape(str(ws.get('primary_formula', '')))} | <strong>Bổ trợ:</strong> {html.escape(', '.join(ws.get('supporting_formulas', [])))}</p>
              <p><strong>Lý do chọn:</strong> {html.escape(str(ws.get('rationale', '')))}</p>
              <p><strong>Ý tưởng mở bài:</strong></p><ul>{openings_li}</ul>
              <p><strong>Chiến thuật thu hút độc giả:</strong></p><ul>{tactics_li}</ul>
              <h3>Outline H2/H3</h3><ul>{outline_li}</ul>
              <h3>SEO Checklist</h3><ul>{checklist_li}</ul>
            </section>
            """
        )

    return f"""<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="utf-8" />
  <title>FinZ SEO Content Brief — {html.escape(proj['code'])} {html.escape(proj['name'])}</title>
  <style>
    body {{ font-family: system-ui, -apple-system, sans-serif; color: #0f172a; margin: 24px; line-height: 1.55; }}
    header {{ border-bottom: 2px solid #0f172a; padding-bottom: 12px; margin-bottom: 24px; }}
    .brief-card {{ border: 1px solid #cbd5e1; border-radius: 10px; padding: 18px; margin-bottom: 20px; page-break-inside: avoid; }}
    .brief-head {{ display: flex; justify-content: space-between; align-items: center; gap: 12px; }}
    .badge {{ background: #e2e8f0; padding: 4px 10px; border-radius: 999px; font-size: 12px; font-weight: 600; }}
    h3 {{ margin-top: 16px; border-top: 1px solid #e2e8f0; padding-top: 10px; }}
    @media print {{ body {{ margin: 12mm; }} }}
  </style>
</head>
<body>
  <header>
    <h1>FinZ SEO Content Brief — {html.escape(proj['code'])}: {html.escape(proj['name'])}</h1>
    <p>Topic Pillar: {html.escape(proj['topic_pillar_code'])} {html.escape(proj['topic_pillar_name'])} | Thị trường: {html.escape(proj['market'])} | Phiên bản: v{proj['version']} | Policy: v{html.escape(data['policy_version'])}</p>
  </header>
  {''.join(brief_blocks) or '<p>Chưa có Content Brief nào được tạo.</p>'}
</body>
</html>"""
