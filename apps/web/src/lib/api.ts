import type { StandardizedError } from './types';

export class ApiError extends Error {
  status: number;
  structured: StandardizedError | null;

  constructor(status: number, message: string, structured: StandardizedError | null = null) {
    super(message);
    this.status = status;
    this.structured = structured;
  }
}

const API_BASE = (process.env.NEXT_PUBLIC_API_BASE || '').replace(/\/+$/, '');

function resolveApiUrl(path: string): string {
  if (/^https?:\/\//i.test(path)) return path;
  return `${API_BASE}${path}`;
}

export async function apiRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  const isFormData = typeof FormData !== 'undefined' && options.body instanceof FormData;
  const headers: Record<string, string> = {};
  if (!isFormData) {
    headers['Content-Type'] = 'application/json';
  }
  if (options.headers) {
    Object.assign(headers, options.headers as Record<string, string>);
  }

  let res: Response;
  try {
    res = await fetch(resolveApiUrl(path), {
      ...options,
      headers,
      cache: 'no-store',
    });
  } catch {
    throw new ApiError(0, 'Không thể kết nối tới backend FastAPI (127.0.0.1:8000).', {
      code: 'BACKEND_UNREACHABLE',
      reason: 'Không thể kết nối tới FastAPI local.',
      impact: 'Không đọc hoặc lưu được dữ liệu vào SQLite.',
      solution: 'Kiểm tra tiến trình `npm run dev` đang chạy cả API (cổng 8000) và Web (cổng 3000).',
      next_action: 'Chạy lại `npm run dev` tại thư mục gốc Finz.',
    });
  }

  if (!res.ok) {
    const rawText = await res.text().catch(() => '');
    let body: unknown = rawText;
    try {
      body = rawText ? JSON.parse(rawText) : null;
    } catch {
      body = rawText;
    }
    const detail = (body as { detail?: unknown })?.detail;
    if (detail && typeof detail === 'object' && 'code' in (detail as Record<string, unknown>)) {
      const s = detail as StandardizedError;
      throw new ApiError(res.status, s.reason || s.code, s);
    }
    const msg =
      typeof detail === 'string'
        ? detail
        : typeof body === 'string' && body.trim()
        ? `HTTP ${res.status}: ${body.trim().slice(0, 200)}`
        : `Lỗi máy chủ (HTTP ${res.status})`;
    throw new ApiError(res.status, msg, {
      code: res.status >= 500 ? 'PROVIDER_UNAVAILABLE' : 'REQUEST_ERROR',
      reason: msg,
      impact: 'Yêu cầu tới backend chưa hoàn tất (có thể do quá thời gian chờ hoặc phản hồi lỗi).',
      solution: 'Kiểm tra lại kết nối mạng, cấu hình AI hoặc log trong terminal `npm run dev` rồi thử lại.',
      next_action: 'Thử lại thao tác sau ít giây.',
    });
  }

  return (await res.json()) as T;
}

export async function downloadExportFile(projectId: string, format: 'xlsx' | 'csv' | 'json' | 'html'): Promise<string> {
  const res = await fetch(resolveApiUrl(`/api/v1/projects/${projectId}/exports/download`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ format }),
  });
  if (!res.ok) {
    throw new Error(`Xuất file ${format.toUpperCase()} thất bại (HTTP ${res.status}).`);
  }
  const blob = await res.blob();
  const filename =
    res.headers.get('X-FinZ-Export-Filename') || `FinZ_SEO_Brief.${format}`;
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  return filename;
}
