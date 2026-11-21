from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import openpyxl

from app.config import settings
from app.domain.taxonomy_parser import normalize_text, strip_accents_key

METRICS_COLUMN_ALIASES: dict[str, set[str]] = {
    "keyword": {"keyword", "keywords", "tu_khoa", "query", "search_term"},
    "volume": {"volume", "search_volume", "avg_monthly_searches", "sv", "luong_tim_kiem"},
    "kd": {"keyword_difficulty", "kd", "kd_", "difficulty", "do_kho", "keyword_difficulty_"},
    "intent": {"intent", "search_intent", "y_dinh_tim_kiem", "intents"},
    "cpc": {"cpc", "cpc_usd", "cpc_vnd", "cost_per_click"},
    "serp_features": {"serp_features", "serp_feature", "features", "serp_features_by_keyword"},
}

# NOTE: Semrush SERP Analysis CSV uses `Type` for `Organic` vs `AI Overview` (NOT page_type!)
ORGANIC_COLUMN_ALIASES: dict[str, set[str]] = {
    "keyword": {"keyword", "keywords", "tu_khoa", "query"},
    "url": {"url", "landing_page", "page_url", "serp_url", "link"},
    "position": {"position", "pos", "rank", "ranking", "vi_tri"},
    "result_type": {"type", "result_type", "serp_type", "loai_ket_qua"},
    "domain": {"domain", "root_domain", "ten_mien"},
    "title": {"title", "page_title", "serp_title", "tieu_de"},
    "page_type": {"page_type", "content_type", "loai_trang"},
    "serp_features": {"serp_features", "serp_feature", "features"},
}

MISSING_TOKENS = {"", "-", "--", "—", "n/a", "na", "null", "none", "nan"}
VALID_PAGE_TYPES = {"ARTICLE", "TOOL", "DOWNLOAD", "SERVICE", "PRODUCT", "UNKNOWN"}


def parse_localized_number(raw: Any, locale: str = "en-US") -> float | None:
    """
    Parse numbers honoring locale:
    - en-US: '9,900' -> 9900.0, '45.5' -> 45.5
    - vi-VN: '9.900' -> 9900.0, '45,5' -> 45.5
    Missing/blank/'n/a'/'-' MUST return None (distinct from 0!).
    """
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return float(raw)

    s = str(raw).strip()
    if s.lower() in MISSING_TOKENS:
        return None

    s = s.replace("%", "").replace("$", "").replace("₫", "").replace("VND", "").strip()
    if not s or s.lower() in MISSING_TOKENS:
        return None

    multiplier = 1.0
    upper = s.upper()
    if upper.endswith("K"):
        multiplier = 1_000.0
        s = s[:-1].strip()
    elif upper.endswith("M"):
        multiplier = 1_000_000.0
        s = s[:-1].strip()

    s = s.replace(" ", "").replace("\u00a0", "")

    if locale == "vi-VN":
        if "." in s and "," in s:
            s = s.replace(".", "").replace(",", ".")
        elif "." in s:
            if re.fullmatch(r"-?\d{1,3}(?:\.\d{3})+", s):
                s = s.replace(".", "")
            elif multiplier > 1.0:
                pass
            else:
                parts = s.split(".")
                if len(parts) == 2 and len(parts[1]) == 3:
                    s = s.replace(".", "")
        elif "," in s:
            s = s.replace(",", ".")
    else:
        if "," in s and "." in s:
            s = s.replace(",", "")
        elif "," in s:
            if re.fullmatch(r"-?\d{1,3}(?:,\d{3})+", s):
                s = s.replace(",", "")
            else:
                s = s.replace(",", ".")

    try:
        return float(s) * multiplier
    except ValueError:
        return None


def validate_organic_url(url: str | None) -> tuple[bool, str, str]:
    """Validate an organic URL (http/https + valid domain) and return (is_valid, canonical_url, domain)."""
    if not url:
        return False, "", ""
    cleaned = url.strip()
    parsed = urlparse(cleaned)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc or "." not in parsed.netloc:
        return False, cleaned, ""
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    path = parsed.path.rstrip("/") or "/"
    canonical = f"{parsed.scheme.lower()}://{host}{path}"
    if parsed.query:
        canonical = f"{canonical}?{parsed.query}"
    return True, canonical, host


def normalize_serp_result_type(raw_type: Any) -> str:
    """Classify Semrush SERP `Type` column into ORGANIC vs AI_OVERVIEW vs NON_ORGANIC."""
    if raw_type is None:
        return "ORGANIC"
    s = str(raw_type).strip()
    if not s or s.lower() in MISSING_TOKENS:
        return "ORGANIC"
    low = s.lower()
    if low == "organic":
        return "ORGANIC"
    if "ai overview" in low or low == "ai_overview":
        return "AI_OVERVIEW"
    return re.sub(r"[^A-Z0-9]+", "_", s.upper()).strip("_") or "NON_ORGANIC"


def infer_page_type_from_url(url: str | None, title: str | None = None) -> str:
    """Hypothesis-only page-type inference from URL/title."""
    combined = f"{url or ''} {title or ''}".lower()
    if any(k in combined for k in ("/tool", "/tinh-", "calculator", "cong-cu", "tính ", "quy-doi")):
        return "TOOL"
    if any(k in combined for k in (".pdf", ".xlsx", ".docx", "download", "template", "bieu-mau", "mau-", "tải ")):
        return "DOWNLOAD"
    if any(k in combined for k in ("/service", "/dich-vu", "tu-van", "dịch vụ")):
        return "SERVICE"
    if any(k in combined for k in ("/product", "/san-pham", "/pricing", "/khoa-hoc", "bảng giá")):
        return "PRODUCT"
    if url:
        return "ARTICLE"
    return "UNKNOWN"


def detect_encoding_and_delimiter(file_bytes: bytes) -> tuple[str, str, str]:
    decoded = None
    used_enc = "utf-8"
    for enc in ("utf-8-sig", "utf-8", "utf-16", "cp1258", "latin-1"):
        try:
            decoded = file_bytes.decode(enc)
            used_enc = enc
            break
        except UnicodeDecodeError:
            continue
    if decoded is None:
        raise ValueError("Không thể nhận diện encoding của tệp CSV.")
    sample = decoded[:4096]
    counts = {",": sample.count(","), ";": sample.count(";"), "\t": sample.count("\t")}
    delimiter = max(counts, key=lambda k: counts[k]) if max(counts.values()) > 0 else ","
    return decoded, used_enc, delimiter


def read_tabular_file(
    file_bytes: bytes,
    filename: str,
    sheet_name: str | None = None,
) -> tuple[list[str], list[list[Any]], dict[str, Any]]:
    ext = Path(filename).suffix.lower().lstrip(".")
    if len(file_bytes) > settings.max_upload_bytes:
        raise ValueError(
            f"Tệp vượt quá giới hạn an toàn {settings.max_upload_bytes // (1024 * 1024)} MB."
        )

    meta: dict[str, Any] = {
        "file_format": ext,
        "sheets": [],
        "sheet_name": "",
        "encoding": "utf-8",
        "delimiter": ",",
    }

    if ext in ("xlsx", "xlsm"):
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True, read_only=True)
        try:
            meta["sheets"] = list(wb.sheetnames)
            chosen = sheet_name if (sheet_name and sheet_name in wb.sheetnames) else wb.sheetnames[0]
            meta["sheet_name"] = chosen
            ws = wb[chosen]
            all_rows = [list(r) for r in ws.iter_rows(values_only=True)]
        finally:
            wb.close()
    elif ext in ("csv", "tsv", "txt"):
        decoded, enc, delim = detect_encoding_and_delimiter(file_bytes)
        meta["encoding"] = enc
        meta["delimiter"] = delim
        meta["sheet_name"] = "CSV"
        meta["sheets"] = ["CSV"]
        all_rows = [list(r) for r in csv.reader(io.StringIO(decoded), delimiter=delim)]
    else:
        raise ValueError(f"Định dạng '.{ext}' không được hỗ trợ. Vui lòng tải file CSV hoặc XLSX từ Semrush.")

    non_empty = [r for r in all_rows if any(c is not None and str(c).strip() != "" for c in r)]
    if not non_empty:
        raise ValueError("Tệp tải lên không có dữ liệu.")

    headers = [str(c).strip() if c is not None else f"Column_{i + 1}" for i, c in enumerate(non_empty[0])]
    data_rows = non_empty[1:]
    meta["total_rows"] = len(data_rows)
    if len(data_rows) > settings.max_upload_rows:
        raise ValueError(
            f"Tệp có {len(data_rows):,} dòng, vượt giới hạn xử lý an toàn {settings.max_upload_rows:,} dòng/lần."
        )
    return headers, data_rows, meta


def suggest_column_mapping(headers: list[str], report_type: str) -> dict[str, str | None]:
    alias_map = ORGANIC_COLUMN_ALIASES if report_type == "ORGANIC_RESULTS" else METRICS_COLUMN_ALIASES
    suggested: dict[str, str | None] = {k: None for k in alias_map}
    for h in headers:
        norm = strip_accents_key(h)
        for field_name, aliases in alias_map.items():
            if suggested[field_name] is None and norm in aliases:
                suggested[field_name] = h
    for h in headers:
        norm = strip_accents_key(h)
        if report_type == "ORGANIC_RESULTS":
            if suggested["url"] is None and (norm == "url" or "page_url" in norm or "serp_url" in norm or "link" in norm):
                suggested["url"] = h
            if suggested["position"] is None and ("pos" in norm or "rank" in norm):
                suggested["position"] = h
            if suggested["result_type"] is None and norm in {"type", "result_type", "serp_type"}:
                suggested["result_type"] = h
            if suggested["domain"] is None and norm == "domain":
                suggested["domain"] = h
            if suggested["title"] is None and "title" in norm:
                suggested["title"] = h
            if suggested["keyword"] is None and norm in {"keyword", "keywords", "query", "tu_khoa"}:
                suggested["keyword"] = h
            if suggested["serp_features"] is None and "serp" in norm:
                suggested["serp_features"] = h
        else:
            if suggested["keyword"] is None and "keyword" in norm:
                suggested["keyword"] = h
            if suggested["volume"] is None and "volume" in norm:
                suggested["volume"] = h
            if suggested["kd"] is None and ("kd" in norm or "difficulty" in norm):
                suggested["kd"] = h
            if suggested["intent"] is None and "intent" in norm:
                suggested["intent"] = h
            if suggested["serp_features"] is None and "serp" in norm:
                suggested["serp_features"] = h
            if suggested["cpc"] is None and "cpc" in norm:
                suggested["cpc"] = h
    return suggested


@dataclass
class ParsedSemrushResult:
    row_type: str  # METRICS | ORGANIC_RESULTS
    total_raw_rows: int
    total_normalized_rows: int
    duplicate_rows_detected: int
    rows: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)


def parse_semrush_rows(
    headers: list[str],
    data_rows: list[list[Any]],
    *,
    report_type: str,
    column_mapping: dict[str, str | None],
    locale: str = "en-US",
    market: str = "VN",
    fallback_keyword: str | None = None,
) -> ParsedSemrushResult:
    """
    Parse ALL rows of a Semrush CSV/XLSX upload.
    - ORGANIC_RESULTS uses a dedicated organic parser distinguishing `Type=Organic` vs `AI Overview`,
      validating URLs & positions >= 1, preserving rejected raw rows with diagnostics, and binding
      `fallback_keyword` (from ResearchRequest.seed_keyword or explicit target_keyword) when the
      Semrush SERP Analysis CSV omits a Keyword column.
    - METRICS parses Volume/KD/Intent/CPC/SERP Features with locale awareness, NULL != 0,
      and deduplicates keywords WITHOUT summing Volume.
    """
    header_index = {h: i for i, h in enumerate(headers)}
    warnings: list[dict[str, Any]] = []
    parsed_rows: list[dict[str, Any]] = []
    dup_count = 0

    def cell(row: list[Any], field_name: str) -> Any:
        col = column_mapping.get(field_name)
        if not col or col not in header_index:
            return None
        idx = header_index[col]
        return row[idx] if idx < len(row) else None

    if report_type == "ORGANIC_RESULTS":
        if not column_mapping.get("url"):
            raise ValueError(
                "Báo cáo ORGANIC_RESULTS bắt buộc phải ghép cột URL (không dùng nhầm parser metrics cho báo cáo organic)."
            )
        bound_kw = (fallback_keyword or "").strip()
        seen_organic_urls: set[tuple[str, str]] = set()
        non_organic_count = 0
        invalid_url_count = 0
        invalid_pos_count = 0
        missing_kw_count = 0

        for idx, row in enumerate(data_rows, start=2):
            raw_dict = {headers[i]: (row[i] if i < len(row) else None) for i in range(len(headers))}
            kw_cell = str(cell(row, "keyword") or "").strip()
            kw = kw_cell or bound_kw
            kw_norm = normalize_text(kw)
            raw_url = str(cell(row, "url") or "").strip()
            url_ok, canonical_url, host_from_url = validate_organic_url(raw_url)
            domain = str(cell(row, "domain") or "").strip().lower() or host_from_url
            pos_val = parse_localized_number(cell(row, "position"), locale=locale)
            pos = int(round(pos_val)) if pos_val is not None else None
            pos_ok = pos is not None and pos >= 1
            result_type = normalize_serp_result_type(cell(row, "result_type"))
            title = str(cell(row, "title") or "").strip() or None
            sf_raw = cell(row, "serp_features")
            serp_features = (
                str(sf_raw).strip()
                if sf_raw is not None and str(sf_raw).strip().lower() not in MISSING_TOKENS
                else None
            )
            explicit_pt = str(cell(row, "page_type") or "").strip().upper() or None
            page_type = explicit_pt if explicit_pt in VALID_PAGE_TYPES else infer_page_type_from_url(raw_url, title)

            row_warns: list[str] = []
            organic_valid = True
            if result_type != "ORGANIC":
                organic_valid = False
                non_organic_count += 1
                row_warns.append(f"NON_ORGANIC_SERP_ROW:{result_type}")
            if not url_ok:
                organic_valid = False
                invalid_url_count += 1
                row_warns.append("INVALID_ORGANIC_URL")
            if not pos_ok:
                organic_valid = False
                invalid_pos_count += 1
                row_warns.append("INVALID_ORGANIC_POSITION")
            if not kw_norm:
                organic_valid = False
                missing_kw_count += 1
                row_warns.append("MISSING_SERP_KEYWORD")

            is_dup = False
            if organic_valid:
                dedup_key = (kw_norm, canonical_url.lower())
                if dedup_key in seen_organic_urls:
                    is_dup = True
                    dup_count += 1
                    row_warns.append("DUPLICATE_ORGANIC_URL")
                else:
                    seen_organic_urls.add(dedup_key)

            parsed_rows.append(
                {
                    "row_type": "ORGANIC_RESULTS",
                    "source_row_number": idx,
                    "keyword": kw,
                    "keyword_normalized": kw_norm,
                    "volume": None,
                    "kd": None,
                    "intent": None,
                    "cpc": None,
                    "serp_features": serp_features,
                    "organic_url": raw_url or None,
                    "organic_position": pos,
                    "organic_title": title,
                    "organic_page_type": page_type,
                    "serp_result_type": result_type,
                    "organic_domain": domain,
                    "organic_valid": organic_valid,
                    "market": market,
                    "is_duplicate": is_dup,
                    "raw_row": raw_dict,
                    "row_warnings": row_warns,
                }
            )

        if non_organic_count > 0:
            warnings.append(
                {
                    "code": "NON_ORGANIC_SERP_ROWS_EXCLUDED",
                    "severity": "INFO",
                    "message": f"Đã giữ raw và loại {non_organic_count} dòng không phải Organic (vd: AI Overview) khỏi tính thứ hạng Organic.",
                }
            )
        if dup_count > 0:
            warnings.append(
                {
                    "code": "DUPLICATE_ORGANIC_URLS",
                    "severity": "WARNING",
                    "message": f"Phát hiện {dup_count} URL organic trùng lặp trong cùng từ khóa; giữ thứ hạng cao nhất.",
                }
            )
        if invalid_url_count > 0:
            warnings.append(
                {
                    "code": "INVALID_ORGANIC_URL",
                    "severity": "WARNING",
                    "message": f"{invalid_url_count} dòng có URL không hợp lệ (đã lưu raw để đối soát, không tính là bằng chứng SERP).",
                }
            )
        if invalid_pos_count > 0:
            warnings.append(
                {
                    "code": "INVALID_ORGANIC_POSITION",
                    "severity": "WARNING",
                    "message": f"{invalid_pos_count} dòng thiếu hoặc sai thứ hạng Position (<1).",
                }
            )
        if missing_kw_count > 0:
            warnings.append(
                {
                    "code": "MISSING_SERP_KEYWORD",
                    "severity": "WARNING",
                    "message": (
                        f"{missing_kw_count} dòng SERP thiếu từ khóa gắn kết (không có cột Keyword và chưa gắn phiếu/từ khóa mục tiêu) "
                        "— không được tính là bằng chứng xác minh SERP."
                    ),
                }
            )

        valid_normalized = len([r for r in parsed_rows if r["organic_valid"] and not r["is_duplicate"]])
        return ParsedSemrushResult(
            row_type="ORGANIC_RESULTS",
            total_raw_rows=len(data_rows),
            total_normalized_rows=valid_normalized,
            duplicate_rows_detected=dup_count,
            rows=parsed_rows,
            warnings=warnings,
        )

    # METRICS parser (KEYWORD_OVERVIEW | RELATED | QUESTIONS)
    if not column_mapping.get("keyword"):
        raise ValueError("Vui lòng ghép cột 'Keyword' trước khi xác nhận import.")

    seen_keywords: set[str] = set()
    missing_vol = 0
    missing_kd = 0
    missing_intent = 0

    for idx, row in enumerate(data_rows, start=2):
        raw_dict = {headers[i]: (row[i] if i < len(row) else None) for i in range(len(headers))}
        kw_raw = cell(row, "keyword")
        kw = str(kw_raw).strip() if kw_raw is not None else ""
        if not kw:
            continue
        kw_norm = normalize_text(kw)
        row_warns: list[str] = []

        is_dup = kw_norm in seen_keywords
        if is_dup:
            dup_count += 1
            row_warns.append("DUPLICATE_KEYWORD_NOT_SUMMED")
        else:
            seen_keywords.add(kw_norm)

        vol_num = parse_localized_number(cell(row, "volume"), locale=locale)
        volume = int(round(vol_num)) if vol_num is not None else None
        kd_num = parse_localized_number(cell(row, "kd"), locale=locale)
        kd = round(kd_num, 2) if kd_num is not None else None
        cpc_num = parse_localized_number(cell(row, "cpc"), locale=locale)
        cpc = round(cpc_num, 2) if cpc_num is not None else None

        intent_raw = cell(row, "intent")
        intent = (
            str(intent_raw).strip()
            if intent_raw is not None and str(intent_raw).strip().lower() not in MISSING_TOKENS
            else None
        )
        sf_raw = cell(row, "serp_features")
        serp_features = (
            str(sf_raw).strip()
            if sf_raw is not None and str(sf_raw).strip().lower() not in MISSING_TOKENS
            else None
        )

        if not is_dup:
            if volume is None:
                missing_vol += 1
                row_warns.append("VOLUME_MISSING")
            if kd is None:
                missing_kd += 1
                row_warns.append("KD_MISSING")
            if intent is None:
                missing_intent += 1
                row_warns.append("INTENT_MISSING")

        parsed_rows.append(
            {
                "row_type": "METRICS",
                "source_row_number": idx,
                "keyword": kw,
                "keyword_normalized": kw_norm,
                "volume": volume,
                "kd": kd,
                "intent": intent,
                "cpc": cpc,
                "serp_features": serp_features,
                "organic_url": None,
                "organic_position": None,
                "organic_title": None,
                "organic_page_type": None,
                "serp_result_type": "METRICS",
                "organic_domain": "",
                "organic_valid": True,
                "market": market,
                "is_duplicate": is_dup,
                "raw_row": raw_dict,
                "row_warnings": row_warns,
            }
        )

    if dup_count > 0:
        warnings.append(
            {
                "code": "DUPLICATE_KEYWORDS_DETECTED",
                "severity": "WARNING",
                "message": f"Phát hiện {dup_count} dòng keyword trùng lặp; hệ thống đã giữ nguyên bản ghi gốc và KHÔNG cộng dồn Volume.",
            }
        )
    if missing_kd > 0:
        warnings.append(
            {
                "code": "KD_MISSING",
                "severity": "WARNING",
                "message": f"{missing_kd} keyword thiếu chỉ số KD (null khác 0).",
            }
        )
    if missing_vol > 0:
        warnings.append(
            {
                "code": "VOLUME_MISSING",
                "severity": "WARNING",
                "message": f"{missing_vol} keyword thiếu Volume (null khác 0).",
            }
        )
    if missing_intent > 0:
        warnings.append(
            {
                "code": "INTENT_MISSING",
                "severity": "WARNING",
                "message": f"{missing_intent} keyword thiếu Search Intent từ Semrush.",
            }
        )

    return ParsedSemrushResult(
        row_type="METRICS",
        total_raw_rows=len(data_rows),
        total_normalized_rows=len([r for r in parsed_rows if not r["is_duplicate"]]),
        duplicate_rows_detected=dup_count,
        rows=parsed_rows,
        warnings=warnings,
    )
