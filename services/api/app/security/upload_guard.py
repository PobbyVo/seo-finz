from __future__ import annotations

import io
import re
import uuid
import zipfile
from pathlib import Path

from fastapi import HTTPException, UploadFile

from app.config import settings

_CHUNK_SIZE = 64 * 1024  # 64 KB streaming chunks
_MAX_XLSX_UNCOMPRESSED_BYTES = 80 * 1024 * 1024  # 80 MB anti-zip-bomb limit
_WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
}


def sanitize_upload_filename(raw_name: str | None, default_name: str = "upload.csv") -> str:
    """Safely sanitize untrusted filenames across Windows, macOS, and Linux."""
    base = Path((raw_name or default_name).replace("\\", "/")).name
    base = re.sub(r"[\x00-\x1f\x7f<>:\"/\\|?*]+", "_", base).strip(" .")
    if not base:
        base = default_name
    stem = Path(base).stem.upper()
    if stem in _WINDOWS_RESERVED:
        base = f"file_{base}"
    if len(base) > 120:
        ext = Path(base).suffix[:12]
        base = f"{Path(base).stem[:100]}{ext}"
    return base


def build_unique_upload_path(uploads_dir: Path, project_id: str, purpose: str, sha256: str, filename: str) -> Path:
    """Guarantee unique storage path so hash prefix collisions never overwrite an existing user file."""
    safe_name = sanitize_upload_filename(filename)
    uniq = uuid.uuid4().hex[:8]
    return uploads_dir / f"{project_id}_{purpose}_{sha256[:12]}_{uniq}_{safe_name}"


async def read_bounded_upload(
    file: UploadFile,
    *,
    max_bytes: int | None = None,
) -> bytes:
    """
    Stream-read an uploaded file in bounded chunks BEFORE buffering into RAM.
    Rejects oversized uploads with HTTP 413 immediately, and validates XLSX archives
    against zip-bomb expansion before handing bytes to openpyxl.
    """
    limit = max_bytes if max_bytes is not None else settings.max_upload_bytes
    chunks: list[bytes] = []
    total = 0

    while True:
        chunk = await file.read(_CHUNK_SIZE)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise HTTPException(
                status_code=413,
                detail={
                    "code": "UPLOAD_TOO_LARGE",
                    "reason": f"Tệp tải lên vượt quá giới hạn an toàn {limit // (1024 * 1024)} MB ({limit:,} bytes).",
                    "impact": "Backend đã từ chối tệp ngay khi đọc luồng để bảo vệ bộ nhớ hệ thống.",
                    "solution": "Chia nhỏ tệp xuất từ Semrush/Excel hoặc lọc bớt các cột không cần thiết rồi tải lại.",
                    "next_action": "Giảm dung lượng tệp và upload lại.",
                },
            )
        chunks.append(chunk)

    raw = b"".join(chunks)
    if not raw:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "UPLOAD_EMPTY",
                "reason": "Tệp tải lên rỗng (0 bytes).",
                "impact": "Không có dữ liệu để xem trước hoặc import.",
                "solution": "Kiểm tra lại tệp đã xuất từ Semrush hoặc Excel rồi tải lại.",
                "next_action": "Chọn tệp có dữ liệu hợp lệ.",
            },
        )

    ext = Path(file.filename or "").suffix.lower()
    if ext in {".xlsx", ".xlsm"}:
        _validate_xlsx_zip_safety(raw)
    return raw


def _validate_xlsx_zip_safety(raw: bytes) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            uncompressed = sum(info.file_size for info in zf.infolist())
            if uncompressed > _MAX_XLSX_UNCOMPRESSED_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail={
                        "code": "UPLOAD_ZIP_BOMB_REJECTED",
                        "reason": (
                            f"Tệp XLSX có kích thước giải nén bất thường ({uncompressed // (1024 * 1024)} MB), "
                            "vượt ngưỡng bảo vệ an toàn."
                        ),
                        "impact": "Tệp bị từ chối để tránh tràn RAM khi phân tích.",
                        "solution": "Lưu lại tệp Excel sạch hoặc xuất sang định dạng CSV.",
                        "next_action": "Xuất lại tệp gọn hơn và tải lên lại.",
                    },
                )
    except HTTPException:
        raise
    except zipfile.BadZipFile as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "MALFORMED_XLSX",
                "reason": f"Tệp XLSX bị hỏng hoặc không phải định dạng Excel hợp lệ ({exc}).",
                "impact": "Không thể đọc bảng dữ liệu từ tệp này.",
                "solution": "Mở tệp bằng Excel/Google Sheets và lưu lại định dạng .xlsx hoặc .csv chuẩn.",
                "next_action": "Tải lên tệp hợp lệ.",
            },
        ) from exc
