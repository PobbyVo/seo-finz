from __future__ import annotations

import csv
import io
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import openpyxl


def normalize_text(text: str | None) -> str:
    if not text:
        return ""
    s = unicodedata.normalize("NFC", str(text)).strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s


def strip_accents_key(text: str) -> str:
    s = unicodedata.normalize("NFD", text.lower())
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = s.replace("đ", "d")
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return s


TOPIC_PILLAR_ALIASES: dict[str, set[str]] = {
    "pillar": {"pillar", "nhom_pillar", "truc_lon", "taxonomy_pillar", "pillar_name", "ten_pillar", "nhom_chu_de"},
    "topic_pillar_code": {
        "topic_pillar_code",
        "ma_topic_pillar",
        "ma_topic",
        "ma_chu_de",
        "topic_code",
        "code",
        "id_topic",
        "ma_tp",
    },
    "topic_pillar_name": {
        "topic_pillar_name",
        "ten_topic_pillar",
        "topic_pillar",
        "ten_topic",
        "ten_chu_de",
        "topic_name",
    },
    "topic_type": {"topic_type", "loai_topic", "loai_chu_de", "type", "phan_loai"},
    "split_axis": {"split_axis", "truc_chia", "chieu_tach", "axis"},
    "main_topic": {"main_topic", "chu_de_chinh", "core_topic", "main_subject", "noi_dung_chinh"},
}

KEYWORD_TABLE_ALIASES: dict[str, set[str]] = {
    "topic_pillar_code": {"topic_pillar_code", "ma_topic_pillar", "ma_topic", "ma_chu_de", "topic_code", "ma_tp"},
    "content_code": {"content_code", "ma_noi_dung", "ma_bai", "article_code", "ma_nd", "content_id"},
    "content_title": {"content_title", "tieu_de", "ten_bai", "title", "tieu_de_bai_viet", "tieu_de_du_kien"},
    "primary_keyword": {"primary_keyword", "keyword_chinh", "tu_khoa_chinh", "main_keyword", "primary_kw"},
    "secondary_keywords": {
        "secondary_keywords",
        "keyword_phu",
        "tu_khoa_phu",
        "secondary_kw",
        "sub_keywords",
        "keywords_phu",
    },
    "keyword": {"keyword", "tu_khoa", "kw"},
    "role": {"role", "vai_tro", "loai_tu_khoa", "keyword_type"},
}


# Header gốc của Bộ key FinZ; giữ alias cũ để tương thích dữ liệu V1.6.
for canonical, aliases in {
    "topic_pillar_code": {"ma"}, "split_axis": {"truc_chia_cua_pillar"},
    "main_topic": {"chu_de_chinh_ben_trong"}, "notes": {"ghi_chu"},
    "legacy_code": {"ma_cu_20_pillar"},
}.items():
    TOPIC_PILLAR_ALIASES.setdefault(canonical, set()).update(aliases | {canonical})
for canonical, aliases in {
    "keyword": {"key"}, "role": {"loai"}, "content_code": {"ma_noi_dung_goc"},
    "content_title": {"noi_dung_goc"}, "funnel_stage": {"giai_doan"},
    "title_match_check": {"kiem_chung"}, "subtopic": {"chu_de"},
    "planner_volume": {"luong_tim_thang_dien_tu_keyword_planner"},
}.items():
    KEYWORD_TABLE_ALIASES.setdefault(canonical, set()).update(aliases | {canonical})


@dataclass
class TopicSourcePreview:
    filename: str
    file_format: str
    sheets_scanned: list[str] = field(default_factory=list)
    topic_pillar_header_row: int | None = None
    topic_pillar_sheet: str = ""
    keywords_header_row: int | None = None
    keywords_sheet: str = ""
    topic_pillars: list[dict[str, Any]] = field(default_factory=list)
    content_items: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)


def _match_header_row(rows: list[list[Any]], alias_map: dict[str, set[str]], max_scan: int = 15) -> tuple[int | None, dict[str, int]]:
    best_row_idx: int | None = None
    best_mapping: dict[str, int] = {}

    for r_idx, row in enumerate(rows[:max_scan], start=1):
        mapping: dict[str, int] = {}
        for c_idx, cell in enumerate(row):
            if cell is None:
                continue
            key = strip_accents_key(str(cell))
            if not key:
                continue
            for canonical, aliases in alias_map.items():
                if key in aliases and canonical not in mapping:
                    mapping[canonical] = c_idx
        if len(mapping) > len(best_mapping):
            best_mapping = mapping
            best_row_idx = r_idx

    if len(best_mapping) >= 2:
        return best_row_idx, best_mapping
    return None, {}


def _split_secondary_keywords(raw: Any) -> list[str]:
    if raw is None:
        return []
    text = str(raw).strip()
    if not text:
        return []
    parts = re.split(r"[,;\n|]+", text)
    out: list[str] = []
    seen: set[str] = set()
    for p in parts:
        cleaned = p.strip()
        norm = normalize_text(cleaned)
        if cleaned and norm not in seen:
            seen.add(norm)
            out.append(cleaned)
    return out


def _parse_topic_rows(
    rows: list[list[Any]],
    header_row: int,
    col_map: dict[str, int],
    sheet_name: str,
    filename: str,
    warnings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    topics: list[dict[str, Any]] = []
    code_pattern = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{1,24}$")

    for offset, row in enumerate(rows[header_row:], start=header_row + 1):
        def val(col_key: str) -> str:
            idx = col_map.get(col_key)
            if idx is None or idx >= len(row) or row[idx] is None:
                return ""
            return unicodedata.normalize("NFC", str(row[idx])).strip()

        code = val("topic_pillar_code")
        name = val("topic_pillar_name")
        pillar = val("pillar")
        topic_type = val("topic_type")
        split_axis = val("split_axis")
        main_topic = val("main_topic") or name

        if not any([code, name, pillar, main_topic]):
            continue

        if not code:
            warnings.append(
                {
                    "code": "MISSING_TOPIC_CODE",
                    "severity": "WARNING",
                    "sheet": sheet_name,
                    "row": offset,
                    "message": f"Dòng {offset} (sheet {sheet_name}) thiếu mã Topic Pillar.",
                }
            )
        elif not code_pattern.match(code):
            warnings.append(
                {
                    "code": "INVALID_TOPIC_CODE",
                    "severity": "WARNING",
                    "sheet": sheet_name,
                    "row": offset,
                    "message": f"Mã Topic Pillar '{code}' ở dòng {offset} không đúng định dạng mã chuẩn (vd: P01, P08, Z42).",
                }
            )

        if not name:
            warnings.append(
                {
                    "code": "MISSING_TOPIC_NAME",
                    "severity": "WARNING",
                    "sheet": sheet_name,
                    "row": offset,
                    "message": f"Dòng {offset} (mã {code or '?'}) thiếu tên Topic Pillar.",
                }
            )

        topics.append(
            {
                "pillar": pillar,
                "topic_pillar_code": code,
                "topic_pillar_name": name,
                "topic_type": topic_type,
                "split_axis": split_axis,
                "main_topic": main_topic,
                "notes": val("notes"),
                "legacy_code": val("legacy_code"),
                "source_file": filename,
                "source_sheet": sheet_name,
                "source_row": offset,
            }
        )
    unique = {}
    for topic in topics:
        code = topic["topic_pillar_code"]
        if code not in unique:
            unique[code] = topic
    return list(unique.values())


def _parse_keyword_rows(
    rows: list[list[Any]],
    header_row: int,
    col_map: dict[str, int],
    sheet_name: str,
    filename: str,
    valid_topic_codes: set[str],
    warnings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}

    for offset, row in enumerate(rows[header_row:], start=header_row + 1):
        def val(col_key: str) -> str:
            idx = col_map.get(col_key)
            if idx is None or idx >= len(row) or row[idx] is None:
                return ""
            return unicodedata.normalize("NFC", str(row[idx])).strip()

        tp_code = val("topic_pillar_code")
        c_code = val("content_code")
        if not tp_code and c_code:
            match = re.match(r"^([A-Za-z]+[0-9]+)", c_code)
            tp_code = match.group(1).upper() if match else ""
        title = val("content_title")
        primary_kw = val("primary_keyword")
        secondary_list = _split_secondary_keywords(val("secondary_keywords"))
        single_kw = val("keyword")
        role = val("role").upper()

        if not any([tp_code, c_code, title, primary_kw, secondary_list, single_kw]):
            continue

        if valid_topic_codes and tp_code and tp_code not in valid_topic_codes:
            warnings.append(
                {
                    "code": "ORPHAN_KEYWORD_TOPIC",
                    "severity": "WARNING",
                    "sheet": sheet_name,
                    "row": offset,
                    "message": f"Dòng {offset} (mã nội dung {c_code or '?'}) có mã Topic '{tp_code}' không khớp với bảng Topic Pillar (keyword lạc topic).",
                }
            )

        if not c_code and not primary_kw and not single_kw:
            warnings.append(
                {
                    "code": "INCOMPLETE_KEYWORD_ROW",
                    "severity": "WARNING",
                    "sheet": sheet_name,
                    "row": offset,
                    "message": f"Dòng {offset} thiếu cả mã nội dung và từ khóa.",
                }
            )
            continue

        key = (tp_code, c_code or f"ROW_{offset}")
        entry = grouped.get(key)
        if not entry:
            entry = {
                "topic_pillar_code": tp_code,
                "content_code": c_code,
                "content_title": title,
                "primary_keyword": "",
                "secondary_keywords": [],
                "keyword_rows": [],
                "source_file": filename,
                "source_sheet": sheet_name,
                "source_row": offset,
            }
            grouped[key] = entry

        if single_kw:
            entry["keyword_rows"].append({
                "keyword": single_kw, "role": "PRIMARY" if role in ("PRIMARY", "CHINH", "CHÍNH") else "SECONDARY",
                "funnel_stage": val("funnel_stage").upper(), "title_match_check": val("title_match_check"),
                "subtopic": val("subtopic"), "planner_volume": val("planner_volume"),
                "source_row": offset,
            })
        if title and not entry["content_title"]:
            entry["content_title"] = title
        if primary_kw and not entry["primary_keyword"]:
            entry["primary_keyword"] = primary_kw
        if single_kw:
            if role in ("PRIMARY", "CHINH", "CHÍNH") or ("role" not in col_map and not entry["primary_keyword"]):
                if not entry["primary_keyword"]:
                    entry["primary_keyword"] = single_kw
                elif normalize_text(single_kw) != normalize_text(entry["primary_keyword"]):
                    secondary_list.append(single_kw)
            else:
                secondary_list.append(single_kw)

        existing_norms = {normalize_text(k) for k in entry["secondary_keywords"]}
        if entry["primary_keyword"]:
            existing_norms.add(normalize_text(entry["primary_keyword"]))
        for sk in secondary_list:
            norm = normalize_text(sk)
            if norm and norm not in existing_norms:
                existing_norms.add(norm)
                entry["secondary_keywords"].append(sk)

    items = list(grouped.values())
    for item in items:
        if not item["primary_keyword"]:
            warnings.append(
                {
                    "code": "MISSING_PRIMARY_KEYWORD",
                    "severity": "WARNING",
                    "sheet": item["source_sheet"],
                    "row": item["source_row"],
                    "message": f"Mã nội dung '{item['content_code']}' thiếu Keyword chính.",
                }
            )
    return items


def parse_topic_source_file(file_bytes: bytes, filename: str) -> TopicSourcePreview:
    """
    Parse XLSX or CSV taxonomy + keywords file.
    Automatically detects non-row-1 headers (e.g., Topic Pillar header on row 4, Keywords header on row 1).
    Never fabricates business_goal or target_audience.
    """
    ext = Path(filename).suffix.lower().lstrip(".")
    preview = TopicSourcePreview(filename=filename, file_format=ext or "unknown")
    sheets_rows: dict[str, list[list[Any]]] = {}

    if ext in ("xlsx", "xlsm"):
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True, read_only=True)
        try:
            for name in wb.sheetnames:
                ws = wb[name]
                rows = [list(r) for r in ws.iter_rows(values_only=True)]
                sheets_rows[name] = rows
                preview.sheets_scanned.append(name)
        finally:
            wb.close()
    elif ext in ("csv", "tsv", "txt"):
        decoded = None
        for enc in ("utf-8-sig", "utf-8", "utf-16", "cp1258", "latin-1"):
            try:
                decoded = file_bytes.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        if decoded is None:
            raise ValueError("Không thể giải mã encoding của file CSV.")
        sample = decoded[:4096]
        delimiter = "\t" if "\t" in sample and sample.count("\t") > sample.count(",") else (";" if sample.count(";") > sample.count(",") else ",")
        reader = csv.reader(io.StringIO(decoded), delimiter=delimiter)
        sheets_rows["CSV"] = [list(r) for r in reader]
        preview.sheets_scanned.append("CSV")
    else:
        raise ValueError(f"Định dạng file '.{ext}' không được hỗ trợ. Vui lòng dùng .xlsx hoặc .csv.")

    # Locate Topic Pillar table and Keywords table across sheets
    best_tp: tuple[str, int, dict[str, int]] | None = None
    best_kw: tuple[str, int, dict[str, int]] | None = None

    for s_name, rows in sheets_rows.items():
        s_norm = strip_accents_key(s_name)
        tp_row, tp_map = _match_header_row(rows, TOPIC_PILLAR_ALIASES)
        kw_row, kw_map = _match_header_row(rows, KEYWORD_TABLE_ALIASES)

        # Prefer sheets explicitly named for Topic Pillar vs Keywords when scores tie
        if tp_row is not None and ("topic_pillar_name" in tp_map or "pillar" in tp_map or "split_axis" in tp_map):
            tp_score = len(tp_map) + (2 if "topic" in s_norm or "pillar" in s_norm else 0)
            prev_score = (len(best_tp[2]) + (2 if "topic" in strip_accents_key(best_tp[0]) or "pillar" in strip_accents_key(best_tp[0]) else 0)) if best_tp else -1
            if tp_score > prev_score:
                best_tp = (s_name, tp_row, tp_map)

        if kw_row is not None and ("primary_keyword" in kw_map or "keyword" in kw_map or "content_code" in kw_map):
            kw_score = len(kw_map) + (2 if "keyword" in s_norm or "tu_khoa" in s_norm else 0)
            prev_score = (len(best_kw[2]) + (2 if "keyword" in strip_accents_key(best_kw[0]) or "tu_khoa" in strip_accents_key(best_kw[0]) else 0)) if best_kw else -1
            if kw_score > prev_score:
                best_kw = (s_name, kw_row, kw_map)

    if best_tp:
        s_name, h_row, c_map = best_tp
        preview.topic_pillar_sheet = s_name
        preview.topic_pillar_header_row = h_row
        preview.topic_pillars = _parse_topic_rows(sheets_rows[s_name], h_row, c_map, s_name, filename, preview.warnings)
    else:
        preview.warnings.append(
            {
                "code": "TOPIC_TABLE_NOT_FOUND",
                "severity": "WARNING",
                "sheet": "",
                "row": None,
                "message": "Không tìm thấy bảng Topic Pillar rõ ràng trong file. Bạn vẫn có thể nhập trực tiếp trên form.",
            }
        )

    valid_tp_codes = {t["topic_pillar_code"] for t in preview.topic_pillars if t.get("topic_pillar_code")}

    if best_kw:
        s_name, h_row, c_map = best_kw
        preview.keywords_sheet = s_name
        preview.keywords_header_row = h_row
        preview.content_items = _parse_keyword_rows(
            sheets_rows[s_name], h_row, c_map, s_name, filename, valid_tp_codes, preview.warnings
        )
    else:
        preview.warnings.append(
            {
                "code": "KEYWORDS_TABLE_NOT_FOUND",
                "severity": "WARNING",
                "sheet": "",
                "row": None,
                "message": "Không tìm thấy bảng Keywords trong file.",
            }
        )

    # F0 strict cho Bộ key có Giai đoạn/Loại; file V1.6 vẫn đọc được.
    strict_finz = best_kw and ("funnel_stage" in best_kw[2] or any(strip_accents_key(str(cell)) in {"loai", "key"} for cell in sheets_rows[best_kw[0]][best_kw[1]-1]))
    if strict_finz:
        for column in ("keyword", "role", "content_code", "funnel_stage"):
            if column not in best_kw[2]:
                preview.warnings.append({"code":"F0-THIEU-COT", "severity":"ERROR", "sheet":best_kw[0], "row":best_kw[1], "column":column, "message":f"Thiếu cột bắt buộc: {column}."})
        for item in preview.content_items:
            def error(code: str, column: str, row: int, message: str):
                preview.warnings.append({"code": code, "severity": "ERROR", "sheet": item["source_sheet"], "row": row, "column": column, "message": message})
            records = item["keyword_rows"]
            if sum(r["role"] == "PRIMARY" for r in records) != 1:
                error("F0-KEY-CHINH", "Loại", item["source_row"], "Mỗi mã nội dung phải có đúng một key Chính.")
            if item["topic_pillar_code"] not in valid_tp_codes:
                error("F0-PILLAR", "Mã nội dung gốc", item["source_row"], "Mã pillar không có trong bảng Topic Pillar.")
            for record in records:
                if record["funnel_stage"] not in {"TOFU", "MOFU", "BOFU"}:
                    error("F0-GIAI-DOAN", "Giai đoạn", record["source_row"], "Giai đoạn phải là TOFU, MOFU hoặc BOFU.")
    preview.stats = {
        "topic_pillars_count": len(preview.topic_pillars),
        "content_items_count": len(preview.content_items),
        "warnings_count": len(preview.warnings),
    }
    return preview
