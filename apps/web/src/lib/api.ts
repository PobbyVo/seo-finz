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
    res = await fetch(path, {
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
    let body: unknown = null;
    try {
      body = await res.json();
    } catch {
      body = await res.text();
    }
    const detail = (body as { detail?: unknown })?.detail;
    if (detail && typeof detail === 'object' && 'code' in (detail as Record<string, unknown>)) {
      const s = detail as StandardizedError;
      throw new ApiError(res.status, s.reason || s.code, s);
    }
    const msg = typeof detail === 'string' ? detail : `Lỗi máy chủ (HTTP ${res.status})`;
    throw new ApiError(res.status, msg, {
      code: res.status >= 500 ? 'DB_SAVE_FAILED' : 'REQUEST_ERROR',
      reason: msg,
      impact: 'Thao tác chưa được ghi nhận vào SQLite.',
      solution: 'Kiểm tra lại dữ liệu đầu vào hoặc nhật ký hệ thống rồi thử lại.',
      next_action: 'Thử lại sau khi kiểm tra thông tin.',
    });
  }

  return (await res.json()) as T;
}

export async function downloadExportFile(projectId: string, format: 'xlsx' | 'csv' | 'json' | 'html'): Promise<string> {
  const res = await fetch(`/api/v1/projects/${projectId}/exports/download`, {
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
