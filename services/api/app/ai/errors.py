from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


@dataclass
class StandardizedError:
    code: str
    reason: str
    impact: str
    solution: str
    next_action: str
    cta_label: str = "Mở AI Settings"
    cta_href: str = "/settings/ai"
    http_status: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AIProviderError(Exception):
    def __init__(self, error: StandardizedError):
        super().__init__(f"[{error.code}] {error.reason}")
        self.error = error


ERROR_CATALOG: dict[str, dict[str, str]] = {
    "AI_NOT_CONFIGURED": {
        "reason": "Chưa cấu hình nhà cung cấp AI hoặc chưa có API key hợp lệ.",
        "impact": "Không thể chạy AI Topic Analyst, AI Critic hoặc sinh gợi ý bằng AI.",
        "solution": "Vào Settings → AI Providers để nhập API key (OpenAI, Gemini hoặc Claude) hoặc chọn Mock Provider khi thử nghiệm không tốn phí.",
        "next_action": "Mở trang cấu hình AI Settings và kiểm tra kết nối.",
        "cta_label": "Mở AI Settings",
        "cta_href": "/settings/ai",
    },
    "API_KEY_INVALID": {
        "reason": "API key không hợp lệ, đã bị thu hồi hoặc nhập thiếu ký tự.",
        "impact": "Mọi yêu cầu tới nhà cung cấp AI sẽ bị từ chối (HTTP 401).",
        "solution": "Kiểm tra lại API key trong bảng điều khiển của nhà cung cấp, dán lại key mới và bấm Kiểm tra kết nối.",
        "next_action": "Cập nhật API key mới tại /settings/ai.",
        "cta_label": "Cập nhật API key",
        "cta_href": "/settings/ai",
    },
    "PERMISSION_DENIED": {
        "reason": "API key không có quyền truy cập model hoặc dự án này (HTTP 403).",
        "impact": "Không thể gọi model đã chọn bằng khóa hiện tại.",
        "solution": "Kiểm tra quyền/billing của tài khoản API, hoặc chuyển sang model thuộc gói được cấp quyền (Gemini tự hạ model sau 3 lần lỗi).",
        "next_action": "Kiểm tra quyền API key hoặc hạ bậc model.",
        "cta_label": "Kiểm tra AI Settings",
        "cta_href": "/settings/ai",
    },
    "MODEL_NOT_FOUND": {
        "reason": "Model ID không tồn tại hoặc chưa khả dụng với API key hiện tại (HTTP 404).",
        "impact": "Không thể thực thi yêu cầu AI trên model này.",
        "solution": "Chọn Model ID hợp lệ khác, hoặc với Gemini hãy bật chế độ Tự động chọn model mới nhất & hạ bậc sau 3 lỗi.",
        "next_action": "Cập nhật Model ID hoặc đồng bộ danh sách model mới nhất.",
        "cta_label": "Chọn lại Model",
        "cta_href": "/settings/ai",
    },
    "QUOTA_EXCEEDED": {
        "reason": "Tài khoản API đã hết hạn mức/tín dụng sử dụng (Quota Exceeded).",
        "impact": "Không thể hoàn thành lượt phân tích AI trên model hiện tại.",
        "solution": "Kiểm tra billing/quota tại trang quản trị nhà cung cấp hoặc để Gemini tự động hạ xuống model nhẹ hơn sau 3 lần lỗi.",
        "next_action": "Kiểm tra quota hoặc chuyển model tiết kiệm hơn.",
        "cta_label": "Xem AI Settings",
        "cta_href": "/settings/ai",
    },
    "RATE_LIMITED": {
        "reason": "Gửi quá nhiều yêu cầu trong thời gian ngắn (HTTP 429 Rate Limit).",
        "impact": "Yêu cầu AI bị trì hoãn tạm thời.",
        "solution": "Chờ vài giây rồi thử lại; với Gemini hệ thống sẽ tự thử lại và hạ model sau 3 lần lỗi liên tiếp.",
        "next_action": "Thử lại sau ít giây hoặc kiểm tra giới hạn RPM.",
        "cta_label": "Kiểm tra AI Settings",
        "cta_href": "/settings/ai",
    },
    "CONNECTION_TIMEOUT": {
        "reason": "Quá thời gian chờ phản hồi từ máy chủ AI (Timeout).",
        "impact": "Lượt phân tích AI chưa hoàn tất và không ghi dữ liệu dở dang vào SQLite.",
        "solution": "Kiểm tra kết nối mạng local và thử lại; nếu model quá tải, Gemini sẽ tự hạ model sau 3 lần lỗi.",
        "next_action": "Kiểm tra mạng và thử chạy lại tác vụ.",
        "cta_label": "Thử kết nối lại",
        "cta_href": "/settings/ai",
    },
    "PROVIDER_UNAVAILABLE": {
        "reason": "Máy chủ nhà cung cấp AI đang gặp sự cố tạm thời (HTTP 5xx).",
        "impact": "Không nhận được phản hồi từ nhà cung cấp AI.",
        "solution": "Thử lại sau vài phút; với Gemini hệ thống tự động hạ sang model dự phòng sau 3 lỗi liên tiếp.",
        "next_action": "Chờ ổn định hoặc kiểm tra trạng thái dịch vụ.",
        "cta_label": "Xem AI Settings",
        "cta_href": "/settings/ai",
    },
    "INVALID_PROVIDER_RESPONSE": {
        "reason": "Phản hồi từ model không đúng định dạng JSON/schema yêu cầu.",
        "impact": "Backend từ chối lưu kết quả không đáng tin cậy để tránh làm hỏng dữ liệu nghiên cứu.",
        "solution": "Thử chạy lại hoặc chọn model hỗ trợ Structured Output ổn định hơn (Gemini sẽ tự hạ model sau 3 lần lỗi).",
        "next_action": "Chạy lại bước phân tích hoặc kiểm tra model.",
        "cta_label": "Kiểm tra Model",
        "cta_href": "/settings/ai",
    },
    "DB_SAVE_FAILED": {
        "reason": "Không thể ghi dữ liệu vào cơ sở dữ liệu SQLite local.",
        "impact": "Thay đổi chưa được lưu nên hệ thống không chuyển bước để tránh mất dữ liệu.",
        "solution": "Kiểm tra quyền ghi thư mục data/ và dung lượng đĩa, sau đó bấm Lưu lại.",
        "next_action": "Thử lưu lại tại màn hình hiện tại.",
        "cta_label": "Thử lại",
        "cta_href": "#",
    },
    "KD_MISSING": {
        "reason": "Một số keyword trong bộ dữ liệu chưa có chỉ số KD (Keyword Difficulty) từ Semrush.",
        "impact": "Chưa thể đánh giá độ khó cạnh tranh theo KD, nhưng vẫn xem được Volume/Intent nếu có.",
        "solution": "Xuất thêm báo cáo Keyword Overview từ giao diện Semrush có cột KD và tải lên tại Bước 04.",
        "next_action": "Mở danh sách Yêu cầu Semrush để lấy bổ sung cột KD.",
        "cta_label": "Mở Yêu cầu Semrush",
        "cta_href": "/steps/03-semrush",
    },
}


def build_error(
    code: str,
    *,
    detail: str | None = None,
    http_status: int | None = None,
    cta_label: str | None = None,
    cta_href: str | None = None,
) -> StandardizedError:
    base = ERROR_CATALOG.get(
        code,
        {
            "reason": "Đã xảy ra lỗi không xác định từ nhà cung cấp AI.",
            "impact": "Tác vụ chưa hoàn tất.",
            "solution": "Kiểm tra lại cấu hình AI và nhật ký hệ thống.",
            "next_action": "Mở AI Settings hoặc Nhật ký để xem chi tiết.",
            "cta_label": "Mở AI Settings",
            "cta_href": "/settings/ai",
        },
    )
    reason = base["reason"]
    if detail:
        # Ensure we never leak raw API keys in detail
        safe_detail = sanitize_secret_text(detail)
        reason = f"{reason} Chi tiết: {safe_detail}"
    return StandardizedError(
        code=code,
        reason=reason,
        impact=base["impact"],
        solution=base["solution"],
        next_action=base["next_action"],
        cta_label=cta_label or base["cta_label"],
        cta_href=cta_href or base["cta_href"],
        http_status=http_status,
    )


def sanitize_secret_text(text: str) -> str:
    """Scrub common API key patterns from any diagnostic text before storing/returning."""
    import re

    patterns = [
        r"AQ\.[0-9A-Za-z\-_]{16,}",
        r"AIza[0-9A-Za-z\-_]{20,}",
        r"sk-ant-[0-9A-Za-z\-_]{16,}",
        r"sk-proj-[0-9A-Za-z\-_]{16,}",
        r"sk-[0-9A-Za-z\-_]{20,}",
        r"Bearer\s+[0-9A-Za-z\-_\.]{16,}",
        r"key=[0-9A-Za-z\-_]{12,}",
    ]
    cleaned = text
    for pat in patterns:
        cleaned = re.sub(pat, "[REDACTED_KEY]", cleaned)
    return cleaned[:400]


def _extract_provider_message(body_text: str) -> str:
    import json

    if not body_text:
        return ""
    try:
        parsed = json.loads(body_text)
        if isinstance(parsed, dict):
            err = parsed.get("error")
            if isinstance(err, dict) and err.get("message"):
                return sanitize_secret_text(str(err["message"]))[:220]
            if isinstance(err, str):
                return sanitize_secret_text(err)[:220]
            if parsed.get("message"):
                return sanitize_secret_text(str(parsed["message"]))[:220]
    except Exception:
        pass
    return sanitize_secret_text(body_text.strip())[:180]


def normalize_http_error(status_code: int, body_text: str = "") -> StandardizedError:
    low = body_text.lower()
    upstream_msg = _extract_provider_message(body_text)
    suffix = f" ({upstream_msg})" if upstream_msg else ""

    if status_code == 401:
        return build_error("API_KEY_INVALID", detail=f"HTTP 401 Unauthorized{suffix}", http_status=401)
    if status_code == 400 and ("api key" in low or "api_key_invalid" in low or "invalid api key" in low):
        return build_error("API_KEY_INVALID", detail=f"API key bị nhà cung cấp từ chối{suffix}", http_status=400)
    if status_code == 403:
        return build_error("PERMISSION_DENIED", detail=f"HTTP 403 Forbidden{suffix}", http_status=403)
    if status_code == 404 or ("not found" in low and "model" in low):
        return build_error("MODEL_NOT_FOUND", detail=f"HTTP {status_code}: model không tồn tại hoặc chưa được hỗ trợ{suffix}", http_status=status_code)
    if status_code == 429:
        if "quota" in low or "billing" in low or "insufficient_quota" in low or "resource_exhausted" in low:
            return build_error("QUOTA_EXCEEDED", detail=f"HTTP 429 Quota/Resource Exhausted{suffix}", http_status=429)
        return build_error("RATE_LIMITED", detail=f"HTTP 429 Too Many Requests{suffix}", http_status=429)
    if status_code >= 500:
        return build_error("PROVIDER_UNAVAILABLE", detail=f"HTTP {status_code} Server Error{suffix}", http_status=status_code)
    return build_error("INVALID_PROVIDER_RESPONSE", detail=f"HTTP {status_code}{suffix}", http_status=status_code)
