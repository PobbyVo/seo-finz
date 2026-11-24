from __future__ import annotations

import csv
import hashlib
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
    compute_effective_brief_freshness,
    evaluate_mapping_eligibility,
    load_project_policy_context,
)
from app.domain.mapping_engine import slugify_vi
from app.models import ContentBrief, EvidenceRow, ExportRecord, KeywordMapping, Project, ProjectEvent


def _safe_project_prefix(project: Project) -> str:
    """Dynamic filename prefix from project code & topic pillar — NEVER hardcodes 'Luong'."""
    code = slugify_vi(project.topic_pillar_code or project.code or "project").upper()
    name_slug = slugify_vi(project.topic_pillar_name or project.name or "seo")[:32]
    return f"{code}_{name_slug}"


def compute_project_export_state(
    db: Session,
    project: Project,
) -> dict[str, Any]:
    """Compute live mapping decisions, live brief freshness, and canonical evidence_state_hash."""
    ctx = load_project_policy_context(db, project)
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
    mappings_by_id = {m.id: m for m in mappings}
    decisions_by_id = {m.id: evaluate_mapping_eligibility(project, m, ctx) for m in mappings}

    live_briefs: list[dict[str, Any]] = []
    brief_fingerprints: dict[str, dict[str, Any]] = {}
    for b in briefs:
        m = mappings_by_id.get(b.keyword_mapping_id) if b.keyword_mapping_id else None
        dec = decisions_by_id.get(b.keyword_mapping_id) if b.keyword_mapping_id else None
        fresh = compute_effective_brief_freshness(b, m, dec)
        sb = serialize_brief(b, freshness=fresh)
        live_briefs.append(sb)
        brief_fingerprints[b.id] = {
            "mapping_id": b.keyword_mapping_id,
            "mapping_revision": b.mapping_revision,
            "mapping_fingerprint": b.mapping_fingerprint,
            "live_fingerprint": dec["live_fingerprint"] if dec else "",
            "brief_mode": sb["brief_mode"],
            "is_stale": sb["is_stale"],
        }

    state_payload = {
        "policy_version": POLICY_VERSION,
        "mappings": [
            {
                "id": m.id,
                "rev": m.revision,
                "live_fp": decisions_by_id[m.id]["live_fingerprint"],
                "eligible": decisions_by_id[m.id]["eligible_official"],
            }
            for m in mappings
        ],
        "briefs": brief_fingerprints,
    }
    state_hash = hashlib.sha256(
        json.dumps(state_payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()

    return {
        "ctx": ctx,
        "mappings": mappings,
        "decisions_by_id": decisions_by_id,
        "live_briefs": live_briefs,
        "brief_fingerprints": brief_fingerprints,
        "evidence_state_hash": state_hash,
    }


def evaluate_export_record_freshness(
    record: ExportRecord,
    live_state: dict[str, Any],
) -> dict[str, Any]:
    """
    Truthfully classify an immutable historical ExportRecord as CURRENT vs OUTDATED_SUPERSEDED.
    NEVER mutates stored export file bytes!
    """
    reasons: list[str] = []
    if getattr(record, "is_superseded", False):
        reasons.append(getattr(record, "superseded_reason", "") or "Bản xuất đã bị thay thế do bằng chứng/Mapping cập nhật.")

    rec_hash = getattr(record, "evidence_state_hash", "") or ""
    if rec_hash and rec_hash != live_state["evidence_state_hash"]:
        reasons.append("Trạng thái bằng chứng/Mapping hiện tại đã thay đổi so với thời điểm xuất tệp này.")

    bf_map = json.loads(getattr(record, "brief_fingerprints_json", "{}") or "{}")
    decisions_by_id = live_state["decisions_by_id"]
    for _bid, meta in bf_map.items():
        if not isinstance(meta, dict):
            continue
        mid = meta.get("mapping_id")
        if mid and mid in decisions_by_id:
            dec = decisions_by_id[mid]
            if meta.get("live_fingerprint") and meta["live_fingerprint"] != dec["live_fingerprint"]:
                reasons.append(f"Bằng chứng cho '{dec['primary_keyword']}' đã thay đổi sau khi xuất.")
            elif meta.get("brief_mode") == "OFFICIAL" and not dec["eligible_official"]:
                reasons.append(f"Mapping '{dec['primary_keyword']}' không còn đủ điều kiện OFFICIAL.")

    is_superseded = len(reasons) > 0
    return {
        "is_superseded": is_superseded,
        "freshness_status": "OUTDATED_SUPERSEDED" if is_superseded else "CURRENT",
        "superseded_reason": " ".join(dict.fromkeys(r for r in reasons if r)),
    }


def _collect_export_datasets(db: Session, project: Project) -> dict[str, Any]:
    live_state = compute_project_export_state(db, project)
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
    mappings = live_state["mappings"]
    decisions_by_id = live_state["decisions_by_id"]

    mapping_rows: list[dict[str, Any]] = []
    for m in mappings:
        dec = decisions_by_id[m.id]
        from app.domain.research_business import mapping_handoff
        mapping_rows.append(
            {
                "handoff": mapping_handoff(db, project, m),
                "id": m.id,
                "revision": m.revision,
                "content_fingerprint": dec["live_fingerprint"][:12],
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

    from app.domain.keyword_expansion import enabled, source_review
    from app.models import KeywordCandidate
    volume_policy=enabled(project)
    page_labels={}
    for event in db.query(ProjectEvent).filter_by(project_id=project.id).order_by(ProjectEvent.created_at.asc()).all():
        details=json.loads(event.details_json or "{}")
        for label in details.get("serp_analysis",{}).get("analysis",{}).get("rows",[]):
            if label.get("evidence_id") and label.get("page_type"):page_labels[label["evidence_id"]]=label["page_type"]
        if event.event_type=="SERP_LABEL_CORRECTED" and details.get("evidence_id"):page_labels[details["evidence_id"]]=details["page_type"]
    expansion_candidates=db.query(KeywordCandidate).filter_by(project_id=project.id,candidate_type="RESEARCH_EXPANSION").all()
    return {
        "excluded_source_keywords": [r for r in source_review(db,project) if not r['included']] if volume_policy else [],
        "expansion_candidates": [{"keyword":c.keyword,"reason":c.rationale,"status":c.status} for c in expansion_candidates],
        "policy_version": POLICY_VERSION,
        "contains_api_keys": False,
        "evidence_state_hash": live_state["evidence_state_hash"],
        "brief_fingerprints": live_state["brief_fingerprints"],
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
            for r in evidence_rows if not volume_policy or (r.volume is not None and r.volume > 0)
        ],
        "serp_check": [{"keyword":r.keyword,"position":r.organic_position,"url":r.organic_url,"title":r.organic_title,"page_type":page_labels.get(r.id,r.organic_page_type),"result_type":r.serp_result_type,"valid":r.organic_valid,"duplicate":r.is_duplicate,"raw":json.loads(r.raw_row_json or "{}")} for r in db.query(EvidenceRow).filter_by(project_id=project.id,row_type="ORGANIC_RESULTS").all()],
        "events": [{"code":r.event_type,"message":r.message,"details":json.loads(r.details_json or "{}")} for r in db.query(ProjectEvent).filter_by(project_id=project.id).all()],
        "keyword_mapping": mapping_rows,
        "content_briefs": [b for b in live_state["live_briefs"] if b["content_type"] == "ARTICLE" and (not volume_policy or any(m.id==b["keyword_mapping_id"] and (m.volume or 0)>0 for m in mappings))],
        "backlog": [m for m in mapping_rows if m["page_type"] != "ARTICLE"],
    }


def export_project_bundle(db: Session, project: Project, fmt: str) -> tuple[bytes, str, str, ExportRecord]:
    """
    Export SEO deliverables in XLSX (SEO Content Brief only), CSV, JSON, or printable HTML.
    Dynamically recalculates live eligibility & staleness BEFORE constructing filename/content
    and NEVER includes API keys or secret refs.
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
        content = json.dumps({key: data[key] for key in ("project", "policy_version", "contains_api_keys", "content_briefs")}, ensure_ascii=False, indent=2).encode("utf-8")
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
        evidence_state_hash=data["evidence_state_hash"],
        brief_fingerprints_json=json.dumps(data["brief_fingerprints"], ensure_ascii=False),
        is_superseded=False,
        superseded_reason="",
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
    """Chỉ xuất SEO Content Brief; liên kết tính từ dòng thực tế."""
    topic = (
        slugify_vi(data["project"].get("topic_pillar_name") or data["project"]["name"])
        .replace("-", " ")
        .title()
        .replace(" ", "")[:11]
        or "ChuDe"
    )
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    sheet = wb.create_sheet(f"SEO Content Brief - {topic}")
    briefs = [b for b in data["content_briefs"] if b["content_type"] == "ARTICLE"]
    sheet.sheet_view.showGridLines=False
    sheet.append([None, f"SEO CONTENT BRIEF — BẢNG ĐIỀU HÀNH CHỦ ĐỀ {topic.upper()}"])
    sheet.merge_cells("B1:J1")
    sheet.append([None,"TỔNG QUAN QUẢN LÝ"]);sheet.merge_cells("B2:J2")
    sheet.append([None,"TỔNG SỐ BÀI VIẾT",None,"ƯU TIÊN P1",None,"TỔNG SEARCH VOLUME",None,"TIẾN ĐỘ"])
    sheet.append([None,len(briefs),None,sum(b["priority"]=="P1" for b in briefs),None,sum(b["metrics"].get("volume") or 0 for b in briefs),None,f"{sum(b['brief_mode']=='OFFICIAL' for b in briefs)}/{len(briefs)} chính thức"])
    sheet.append([])
    sheet.append([None,"Mã bài","Tên bài / Hạng mục","Loại nội dung","Ưu tiên","Trạng thái","Keyword chính","Volume/tháng","URL dự kiến","Chi tiết Brief"])
    overview=[]
    for b in briefs:
        sheet.append([None,b["br_code"],b["seo_title"],"Bài viết",b["priority"],b["status"],b["primary_keyword"],b["metrics"].get("volume"),b["proposed_url"]])
        overview.append(sheet.max_row)
    for idx, b in enumerate(briefs):
        sheet.append([])
        sheet.append([None,f"BRIEF {idx+1:02d}: {b['br_code']} — {b['primary_keyword']}"])
        sheet.merge_cells(start_row=sheet.max_row,start_column=2,end_row=sheet.max_row,end_column=9)
        start = sheet.max_row
        cell = sheet.cell(overview[idx], 10, "Xem Brief")
        cell.hyperlink = f"#'{sheet.title}'!B{start}"
        cell.style = "Hyperlink"
        cell = sheet.cell(start, 10, "Lên Overview")
        cell.hyperlink = f"#'{sheet.title}'!B6"
        cell.style = "Hyperlink"
        for label, key in [
            ("Trạng thái", "brief_mode"),
            ("Ưu tiên", "priority"),
            ("Keyword chính", "primary_keyword"),
            ("Độc giả", "target_audience"),
            ("Mục tiêu bài", "article_goal"),
            ("SEO Title", "seo_title"),
            ("H1", "h1"),
            ("Meta", "meta_description"),
            ("CTA", "cta"),
            ("URL dự kiến", "proposed_url"),
        ]:
            sheet.append([None, label, b[key]])
        strategy = b.get("writing_strategy", {})
        for label, value in [
            ("Volume / KD", f"{b['metrics'].get('volume') if b['metrics'].get('volume') is not None else 'Chưa có số'} / KD {b['metrics'].get('kd') if b['metrics'].get('kd') is not None else 'Chưa có số'}"),
            ("Keyword phụ", "; ".join(b.get("secondary_keywords",[]))),
            ("Độ dài tham khảo", strategy.get("word_count_reference", "Chưa xác minh")),
            ("Nguồn pháp lý cần kiểm", "; ".join(strategy.get("legal_sources", []))),
            (
                "Internal link",
                json.dumps(b.get("internal_links", []), ensure_ascii=False),
            ),
            ("Câu hỏi", "; ".join(strategy.get("faq", []))),
            ("Checklist", "; ".join(b.get("seo_checklist", []))),
        ]:
            sheet.append([None, label, value])
        sheet.append([None,"CẤU TRÚC OUTLINE H2",None,None,"HƯỚNG DẪN VIẾT & YÊU CẦU NỘI DUNG"])
        for heading in b.get("outline", []):
            sheet.append(
                [None, heading["heading"], None, None, heading.get("notes", "")]
            )
            for child in heading.get("children", []):
                sheet.append(
                    [None, "  " + child["heading"], None, None, child.get("notes", "")]
                )
    for ws in wb:
        ws.freeze_panes = "B5" if ws == sheet else "A2"
        for row in ws:
            for cell in row:
                cell.alignment = Alignment(vertical="top", wrap_text=True)
                # Source text must not become an Excel formula.
                if isinstance(cell.value, str) and cell.value.startswith(
                    ("=", "+", "-", "@")
                ):
                    cell.value = "'" + cell.value
        for col in ("B", "C", "E"):
            ws.column_dimensions[col].width = 45
    sheet.freeze_panes="G7"
    sheet.column_dimensions['A'].width=3
    for col,width in {'B':22,'C':45,'D':20,'E':20,'F':26,'G':35,'H':16,'I':34,'J':20}.items():sheet.column_dimensions[col].width=width
    for row in sheet:
        for cell in row:
            cell.font=Font(name='Arial',size=10,color='18202C')
            cell.fill=PatternFill('solid',fgColor='F8F8FB')
        sheet.row_dimensions[row[0].row].height=42
        if row[1].value:
            if str(row[1].value).startswith(('BRIEF ', 'TỔNG QUAN','CẤU TRÚC','BACKLOG')) or row[0].row==6:
                for cell in row[1:]:cell.fill=PatternFill('solid',fgColor='073763');cell.font=Font(name='Arial',size=11,bold=True,color='FFFFFF')
            elif row[0].row>6 and row[2].value and not row[4].value:
                row[1].fill=PatternFill('solid',fgColor='EEF3F9');row[1].font=Font(name='Arial',size=10,bold=True,color='1C3860')
    for row in range(7,sheet.max_row+1):
        if sheet.cell(row,2).value and sheet.cell(row,3).value is not None and sheet.cell(row,4).value is None and sheet.cell(row,5).value is None:
            sheet.merge_cells(start_row=row,start_column=3,end_row=row,end_column=10)
            sheet.row_dimensions[row].height=56
        if sheet.cell(row,2).value and sheet.cell(row,5).value and sheet.cell(row,3).value is None:
            sheet.merge_cells(start_row=row,start_column=2,end_row=row,end_column=4)
            sheet.merge_cells(start_row=row,start_column=5,end_row=row,end_column=10)
            sheet.row_dimensions[row].height=64
    sheet['B1'].font=Font(name='Arial',size=14,bold=True,color='073763')
    sheet.row_dimensions[1].height=48
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()

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
