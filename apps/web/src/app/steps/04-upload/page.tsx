'use client';

import { Suspense, useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { CheckCircle2, FileUp, Info, Table2 } from 'lucide-react';
import { useProject } from '@/context/ProjectContext';
import { ApiError, apiRequest } from '@/lib/api';
import type { ResearchRequestItem, StandardizedError } from '@/lib/types';
import { ErrorBanner } from '@/components/ErrorBanner';
import { ResponsiveTable } from '@/components/ResponsiveTable';

interface ImportPreviewResp {
  upload_id: string;
  filename: string;
  sha256: string;
  report_type: string;
  file_format: string;
  sheets: string[];
  sheet_name: string;
  encoding: string;
  delimiter: string;
  locale: string;
  total_rows: number;
  max_supported_rows: number;
  headers: string[];
  suggested_mapping: Record<string, string | null>;
  sample_rows: Array<Record<string, unknown>>;
  notice: string;
}

const METRICS_FIELDS = [
  { key: 'keyword', label: 'Keyword (Bắt buộc) *' },
  { key: 'volume', label: 'Volume' },
  { key: 'kd', label: 'KD (%)' },
  { key: 'intent', label: 'Search Intent' },
  { key: 'cpc', label: 'CPC' },
  { key: 'serp_features', label: 'SERP Features' },
];

const ORGANIC_FIELDS = [
  { key: 'url', label: 'URL Organic (Bắt buộc) *' },
  { key: 'keyword', label: 'Keyword' },
  { key: 'position', label: 'Position / Thứ hạng' },
  { key: 'title', label: 'Title' },
  { key: 'page_type', label: 'Loại trang (nếu có)' },
];

function UploadContent() {
  const { activeProject, refreshProjects, showCompletionPopup } = useProject();
  const searchParams = useSearchParams();
  const initialReqId = searchParams.get('request_id') || '';

  const [requests, setRequests] = useState<ResearchRequestItem[]>([]);
  const [selectedRequestId, setSelectedRequestId] = useState(initialReqId);
  const [reportType, setReportType] = useState<'KEYWORD_OVERVIEW' | 'RELATED' | 'QUESTIONS' | 'ORGANIC_RESULTS'>('KEYWORD_OVERVIEW');
  const [locale, setLocale] = useState<'en-US' | 'vi-VN'>('en-US');
  const [market, setMarket] = useState('VN');

  const [preview, setPreview] = useState<ImportPreviewResp | null>(null);
  const [columnMapping, setColumnMapping] = useState<Record<string, string | null>>({});
  const [uploading, setUploading] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState<StandardizedError | null>(null);

  const loadRequests = useCallback(async () => {
    if (!activeProject) return;
    try {
      const data = await apiRequest<{ research_requests: ResearchRequestItem[] }>(
        `/api/v1/projects/${activeProject.id}/research-requests`
      );
      setRequests(data.research_requests);
      if (initialReqId) {
        const match = data.research_requests.find((r) => r.id === initialReqId);
        if (match) {
          setSelectedRequestId(match.id);
          setReportType(match.report_type);
          setMarket(match.market || activeProject.market || 'VN');
        }
      }
    } catch {
      // ignore
    }
  }, [activeProject, initialReqId]);

  useEffect(() => {
    void loadRequests();
    if (activeProject) setMarket(activeProject.market || 'VN');
  }, [loadRequests, activeProject]);

  if (!activeProject) {
    return (
      <div className="rounded-2xl border border-slate-800 bg-surface-900 p-8 text-center text-sm text-slate-300">
        Chưa chọn dự án. <Link href="/projects" className="text-sky-400 underline">Chọn dự án trước</Link>.
      </div>
    );
  }

  const handleRequestSelect = (id: string) => {
    setSelectedRequestId(id);
    const match = requests.find((r) => r.id === id);
    if (match) {
      setReportType(match.report_type);
      setMarket(match.market || activeProject.market || 'VN');
    }
  };

  const handlePreviewFile = async (file: File) => {
    setUploading(true);
    setError(null);
    setPreview(null);
    try {
      const fd = new FormData();
      fd.append('file', file);
      if (selectedRequestId) fd.append('research_request_id', selectedRequestId);
      fd.append('report_type', reportType);
      fd.append('locale', locale);
      const data = await apiRequest<ImportPreviewResp>(
        `/api/v1/projects/${activeProject.id}/imports/preview`,
        { method: 'POST', body: fd }
      );
      setPreview(data);
      setColumnMapping(data.suggested_mapping);
      // Rule T16: Preview NEVER triggers business completion popup!
    } catch (err) {
      if (err instanceof ApiError && err.structured) setError(err.structured);
    } finally {
      setUploading(false);
    }
  };

  const handleConfirmImport = async () => {
    if (!preview) return;
    setConfirming(true);
    setError(null);
    try {
      const res = await apiRequest<{
        batch_id: string;
        total_raw_rows: number;
        total_normalized_rows: number;
        duplicate_rows_detected: number;
        navigation_eligible: boolean;
        next_step_href: string;
      }>(`/api/v1/projects/${activeProject.id}/imports/confirm`, {
        method: 'POST',
        body: JSON.stringify({
          upload_id: preview.upload_id,
          research_request_id: selectedRequestId || null,
          report_type: preview.report_type,
          market,
          locale,
          sheet_name: preview.sheet_name,
          column_mapping: columnMapping,
        }),
      });
      await refreshProjects(activeProject.id);
      setPreview(null);
      showCompletionPopup({
        title: `Đã nhập batch ${res.batch_id} (PROCESS_COMPLETED)`,
        message: `Backend đã xử lý toàn bộ ${res.total_raw_rows} dòng thô → ${res.total_normalized_rows} dòng chuẩn hóa (${res.duplicate_rows_detected} dòng trùng không cộng dồn Volume). Lưu ý: upload xong là hoàn thành kỹ thuật, chưa phải đã đạt kiểm duyệt SEO.`,
        nextStepLabel: 'Bước 05 — Kiểm tra dữ liệu & AI Critic',
        nextStepHref: res.next_step_href,
        navigationEligible: res.navigation_eligible,
      });
    } catch (err) {
      if (err instanceof ApiError && err.structured) setError(err.structured);
    } finally {
      setConfirming(false);
    }
  };

  const activeFields = (preview?.report_type || reportType) === 'ORGANIC_RESULTS' ? ORGANIC_FIELDS : METRICS_FIELDS;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-100">Bước 04 — Tải file Semrush, Xem trước & Ghép cột</h1>
        <p className="mt-1 text-sm text-slate-400">
          Chọn đúng phiếu Semrush, kiểm tra locale (<code className="text-slate-200">9.900</code> vs <code className="text-slate-200">9,900</code>), chỉnh ánh xạ cột và bấm <strong>Xác nhận import</strong> để lưu toàn bộ file vào SQLite.
        </p>
      </div>

      <ErrorBanner error={error} onDismiss={() => setError(null)} />

      {/* Upload Setup */}
      <section className="rounded-2xl border border-slate-800 bg-surface-900 p-5 space-y-4">
        <div className="grid gap-4 md:grid-cols-4">
          <div className="md:col-span-2">
            <label htmlFor="up-req" className="block text-xs font-semibold text-slate-300 mb-1">
              Chọn phiếu Yêu cầu Semrush (khuyến nghị)
            </label>
            <select
              id="up-req"
              value={selectedRequestId}
              onChange={(e) => handleRequestSelect(e.target.value)}
              className="finz-select"
            >
              <option value="">-- Tải file tự do (không gắn phiếu) --</option>
              {requests.map((r) => (
                <option key={r.id} value={r.id}>
                  [{r.report_type}] {r.seed_keyword} ({r.status})
                </option>
              ))}
            </select>
          </div>

          <div>
            <label htmlFor="up-rt" className="block text-xs font-semibold text-slate-300 mb-1">Loại báo cáo</label>
            <select
              id="up-rt"
              value={reportType}
              onChange={(e) => setReportType(e.target.value as typeof reportType)}
              className="finz-select"
            >
              <option value="KEYWORD_OVERVIEW">KEYWORD_OVERVIEW (Metrics)</option>
              <option value="RELATED">RELATED (Metrics)</option>
              <option value="QUESTIONS">QUESTIONS (Metrics)</option>
              <option value="ORGANIC_RESULTS">ORGANIC_RESULTS (Parser riêng cho URL/Pos/Title)</option>
            </select>
          </div>

          <div>
            <label htmlFor="up-loc" className="block text-xs font-semibold text-slate-300 mb-1">Định dạng số (Locale)</label>
            <select
              id="up-loc"
              value={locale}
              onChange={(e) => setLocale(e.target.value as 'en-US' | 'vi-VN')}
              className="finz-select"
            >
              <option value="en-US">en-US (9,900 · thập phân 45.5)</option>
              <option value="vi-VN">vi-VN (9.900 · thập phân 45,5)</option>
            </select>
          </div>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3 pt-2 border-t border-slate-800">
          <div className="flex items-center gap-3 text-xs text-slate-400">
            <label htmlFor="up-mkt">Thị trường file:</label>
            <input
              id="up-mkt"
              value={market}
              onChange={(e) => setMarket(e.target.value.toUpperCase())}
              className="finz-input w-24 py-1 text-center font-mono"
            />
          </div>

          <label className="inline-flex cursor-pointer items-center gap-2 rounded-xl bg-sky-500 px-5 py-2.5 text-sm font-semibold text-slate-950 hover:bg-sky-400 transition">
            <FileUp className="h-4 w-4" />
            {uploading ? 'Đang đọc xem trước…' : 'Chọn file CSV / XLSX từ Semrush'}
            <input
              type="file"
              accept=".csv,.tsv,.xlsx,.xlsm"
              className="sr-only"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) void handlePreviewFile(f);
                e.target.value = '';
              }}
            />
          </label>
        </div>
      </section>

      {/* Preview & Column Mapping */}
      {preview && (
        <section className="rounded-2xl border border-sky-500/35 bg-surface-900 p-5 space-y-5">
          <div className="rounded-xl border border-sky-500/30 bg-sky-950/25 p-3.5 text-xs text-sky-200 flex items-start gap-2.5">
            <Info className="h-4 w-4 shrink-0 text-sky-400 mt-0.5" />
            <div>
              <p className="font-semibold">{preview.notice}</p>
              <p className="mt-1 text-slate-300">
                File: <strong>{preview.filename}</strong> · Sheet: <strong>{preview.sheet_name}</strong> · Encoding:{' '}
                <code>{preview.encoding}</code> · Delimiter: <code>{preview.delimiter === '\t' ? 'TAB' : preview.delimiter}</code> · SHA-256:{' '}
                <code className="text-[11px]">{preview.sha256.slice(0, 12)}…</code>
              </p>
            </div>
          </div>

          {/* Editable Column Mapping */}
          <div className="space-y-3">
            <h2 className="text-sm font-bold text-slate-100">
              Ánh xạ cột ({preview.report_type === 'ORGANIC_RESULTS' ? 'Parser Organic Results riêng biệt' : 'Parser Keyword Metrics'})
            </h2>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {activeFields.map((f) => (
                <div key={f.key}>
                  <label htmlFor={`map-${f.key}`} className="block text-xs font-semibold text-slate-300 mb-1">
                    {f.label}
                  </label>
                  <select
                    id={`map-${f.key}`}
                    value={columnMapping[f.key] || ''}
                    onChange={(e) =>
                      setColumnMapping((prev) => ({
                        ...prev,
                        [f.key]: e.target.value || null,
                      }))
                    }
                    className="finz-select text-xs"
                  >
                    <option value="">-- Không ghép / Bỏ qua --</option>
                    {preview.headers.map((h) => (
                      <option key={h} value={h}>
                        {h}
                      </option>
                    ))}
                  </select>
                </div>
              ))}
            </div>
          </div>

          {/* Sample Rows Table */}
          <div className="space-y-2">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
              <Table2 className="h-4 w-4 text-sky-400" />
              Xem trước 15 dòng đầu (tổng file: {preview.total_rows.toLocaleString('vi-VN')} dòng)
            </h3>
            <ResponsiveTable caption="Mẫu dữ liệu xem trước từ file Semrush">
              <thead>
                <tr>
                  {preview.headers.map((h) => (
                    <th key={h} scope="col">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {preview.sample_rows.map((row, rIdx) => (
                  <tr key={rIdx}>
                    {preview.headers.map((h, cIdx) =>
                      cIdx === 0 ? (
                        <th key={h} scope="row">{String(row[h] ?? '—')}</th>
                      ) : (
                        <td key={h} data-label={h}>{String(row[h] ?? '—')}</td>
                      )
                    )}
                  </tr>
                ))}
              </tbody>
            </ResponsiveTable>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3 pt-2 border-t border-slate-800">
            <button
              type="button"
              onClick={() => setPreview(null)}
              className="rounded-xl border border-slate-700 bg-surface-850 px-4 py-2 text-xs font-medium text-slate-300 hover:bg-slate-800"
            >
              Hủy bản xem trước
            </button>
            <button
              type="button"
              disabled={confirming}
              onClick={() => void handleConfirmImport()}
              className="inline-flex items-center gap-2 rounded-xl bg-emerald-500 px-5 py-2.5 text-sm font-semibold text-slate-950 hover:bg-emerald-400 disabled:opacity-50 transition"
            >
              <CheckCircle2 className="h-4 w-4" />
              {confirming ? 'Đang xử lý toàn bộ file & ghi SQLite…' : `Xác nhận import toàn bộ ${preview.total_rows.toLocaleString('vi-VN')} dòng`}
            </button>
          </div>
        </section>
      )}
    </div>
  );
}

export default function Step04UploadPage() {
  return (
    <Suspense fallback={<div className="h-48 animate-pulse rounded-2xl bg-surface-900 border border-slate-800" />}>
      <UploadContent />
    </Suspense>
  );
}
