'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { Copy, Check, PlusCircle, UploadCloud, Eye, Shield } from 'lucide-react';
import { useProject } from '@/context/ProjectContext';
import { ApiError, apiRequest } from '@/lib/api';
import type { ResearchRequestItem, StandardizedError } from '@/lib/types';
import { ErrorBanner } from '@/components/ErrorBanner';
import { StatusBadge } from '@/components/StatusBadge';

export default function Step03SemrushPage() {
  const { activeProject, refreshProjects } = useProject();
  const [requests, setRequests] = useState<ResearchRequestItem[]>([]);
  const [notice, setNotice] = useState('');
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [seedKw, setSeedKw] = useState('');
  const [reportType, setReportType] = useState<'KEYWORD_OVERVIEW' | 'RELATED' | 'QUESTIONS' | 'ORGANIC_RESULTS'>('KEYWORD_OVERVIEW');
  const [purpose, setPurpose] = useState('');
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<StandardizedError | null>(null);

  const loadRequests = useCallback(async () => {
    if (!activeProject) return;
    try {
      const data = await apiRequest<{
        research_requests: ResearchRequestItem[];
        manual_only_notice: string;
      }>(`/api/v1/projects/${activeProject.id}/research-requests`);
      setRequests(data.research_requests);
      setNotice(data.manual_only_notice);
    } catch (err) {
      if (err instanceof ApiError && err.structured) setError(err.structured);
    }
  }, [activeProject]);

  useEffect(() => {
    void loadRequests();
    if (activeProject) {
      setSeedKw(activeProject.primary_keyword_current || activeProject.primary_keyword_original || '');
    }
  }, [loadRequests, activeProject]);

  if (!activeProject) {
    return (
      <div className="rounded-2xl border border-slate-800 bg-surface-900 p-8 text-center text-sm text-slate-300">
        Chưa chọn dự án. <Link href="/projects" className="text-sky-400 underline">Chọn dự án trước</Link>.
      </div>
    );
  }

  const handleCopyGuide = async (req: ResearchRequestItem) => {
    const text = [
      `[${req.id}] Báo cáo Semrush: ${req.report_type} | Market: ${req.market}`,
      `Seed keyword: ${req.seed_keyword}`,
      `Mục đích: ${req.purpose}`,
      `Cột nên xuất: ${req.expected_columns.join(', ')}`,
      'Hướng dẫn thao tác:',
      ...req.semrush_steps.map((s, idx) => `${idx + 1}. ${s}`),
    ].join('\n');
    try {
      await navigator.clipboard.writeText(text);
      setCopiedId(req.id);
      setTimeout(() => setCopiedId(null), 1800);
    } catch {
      // ignore clipboard errors
    }
  };

  const handleCreateManual = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!seedKw.trim()) return;
    setCreating(true);
    setError(null);
    try {
      await apiRequest(`/api/v1/projects/${activeProject.id}/research-requests`, {
        method: 'POST',
        body: JSON.stringify({
          items: [
            {
              seed_keyword: seedKw.trim(),
              report_type: reportType,
              market: activeProject.market || 'VN',
              purpose: purpose.trim() || `Lấy dữ liệu ${reportType} còn thiếu cho '${seedKw.trim()}'.`,
              origin: 'MANUAL',
            },
          ],
        }),
      });
      setPurpose('');
      await loadRequests();
      await refreshProjects(activeProject.id);
    } catch (err) {
      if (err instanceof ApiError && err.structured) setError(err.structured);
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-100">Bước 03 — Yêu cầu nghiên cứu Semrush</h1>
        <p className="mt-1 text-sm text-slate-400">
          Danh sách các báo cáo Semrush thật sự cần lấy kèm hướng dẫn thao tác từng bước trên giao diện web Semrush.
        </p>
      </div>

      <div className="rounded-xl border border-sky-500/30 bg-sky-950/20 p-3.5 text-xs text-sky-200 flex items-center gap-2.5">
        <Shield className="h-4 w-4 shrink-0 text-sky-400" />
        <span>{notice || 'Không yêu cầu mật khẩu, API token hay MCP Semrush — bạn tự xuất CSV/XLSX từ Semrush UI và tải lên Bước 04.'}</span>
      </div>

      <ErrorBanner error={error} onDismiss={() => setError(null)} />

      {/* Create Additional Request */}
      <form onSubmit={handleCreateManual} className="rounded-2xl border border-slate-800 bg-surface-900 p-5 space-y-4">
        <div className="flex items-center gap-2 text-sm font-bold text-slate-100">
          <PlusCircle className="h-4 w-4 text-sky-400" />
          Tạo yêu cầu Semrush bổ sung
        </div>
        <div className="grid gap-3 md:grid-cols-4 items-end">
          <div>
            <label htmlFor="rr-seed" className="block text-xs font-semibold text-slate-300 mb-1">Keyword seed *</label>
            <input id="rr-seed" required value={seedKw} onChange={(e) => setSeedKw(e.target.value)} className="finz-input" />
          </div>
          <div>
            <label htmlFor="rr-type" className="block text-xs font-semibold text-slate-300 mb-1">Loại báo cáo</label>
            <select
              id="rr-type"
              value={reportType}
              onChange={(e) => setReportType(e.target.value as typeof reportType)}
              className="finz-select"
            >
              <option value="KEYWORD_OVERVIEW">KEYWORD_OVERVIEW (Volume/KD/Intent)</option>
              <option value="RELATED">RELATED (Từ khóa liên quan/đồng nghĩa)</option>
              <option value="QUESTIONS">QUESTIONS (Câu hỏi thực tế)</option>
              <option value="ORGANIC_RESULTS">ORGANIC_RESULTS (URL/Position/Title tùy chọn)</option>
            </select>
          </div>
          <div>
            <label htmlFor="rr-purpose" className="block text-xs font-semibold text-slate-300 mb-1">Mục đích nghiên cứu</label>
            <input
              id="rr-purpose"
              value={purpose}
              onChange={(e) => setPurpose(e.target.value)}
              placeholder="VD: Bổ sung cột KD hoặc xác minh dạng trang"
              className="finz-input"
            />
          </div>
          <button
            type="submit"
            disabled={creating}
            className="rounded-xl bg-sky-500 px-4 py-2.5 text-sm font-semibold text-slate-950 hover:bg-sky-400 disabled:opacity-50 transition"
          >
            {creating ? 'Đang tạo…' : 'Tạo phiếu yêu cầu'}
          </button>
        </div>
      </form>

      {/* Request Cards */}
      {requests.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-slate-700 bg-surface-900/50 p-10 text-center text-sm text-slate-400">
          Chưa có phiếu Yêu cầu Semrush nào. Bạn có thể tạo tự động từ{' '}
          <Link href="/steps/02-demand-map" className="text-sky-400 underline">Bước 02</Link> hoặc tạo mới ở trên.
        </div>
      ) : (
        <div className="space-y-4">
          {requests.map((r) => (
            <article key={r.id} className="rounded-2xl border border-slate-800 bg-surface-900 p-5 space-y-3">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="space-y-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-xs text-slate-400">{r.id}</span>
                    <span className="rounded-md bg-violet-500/15 border border-violet-500/30 px-2 py-0.5 font-mono text-xs font-semibold text-violet-200">
                      {r.report_type}
                    </span>
                    <span className="rounded-md bg-slate-800 px-2 py-0.5 text-xs text-slate-300">Market: {r.market}</span>
                    <StatusBadge status={r.status} />
                  </div>
                  <h3 className="text-base font-bold text-slate-100">Seed: &ldquo;{r.seed_keyword}&rdquo;</h3>
                  <p className="text-xs text-slate-400">{r.purpose}</p>
                </div>

                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={() => void handleCopyGuide(r)}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-slate-700 bg-surface-850 px-3 py-1.5 text-xs font-medium text-slate-200 hover:bg-slate-800"
                  >
                    {copiedId === r.id ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
                    {copiedId === r.id ? 'Đã sao chép' : 'Sao chép hướng dẫn'}
                  </button>
                  <Link
                    href={`/steps/04-upload?request_id=${r.id}`}
                    className="inline-flex items-center gap-1.5 rounded-lg bg-sky-500 px-3 py-1.5 text-xs font-semibold text-slate-950 hover:bg-sky-400"
                  >
                    <UploadCloud className="h-3.5 w-3.5" />
                    Gửi file
                  </Link>
                  <Link
                    href="/steps/05-evidence"
                    className="inline-flex items-center gap-1.5 rounded-lg border border-slate-700 bg-surface-850 px-3 py-1.5 text-xs text-slate-300 hover:bg-slate-800"
                  >
                    <Eye className="h-3.5 w-3.5" />
                    Xem dữ liệu
                  </Link>
                </div>
              </div>

              <div className="grid gap-3 md:grid-cols-3 text-xs pt-2 border-t border-slate-800/80">
                <div>
                  <div className="font-semibold text-slate-300 mb-1">Cột cần xuất (nếu Semrush hiển thị)</div>
                  <div className="flex flex-wrap gap-1.5">
                    {r.expected_columns.map((c) => (
                      <span key={c} className="rounded bg-slate-800 px-2 py-0.5 font-mono text-[11px] text-sky-200">
                        {c}
                      </span>
                    ))}
                  </div>
                </div>
                <div className="md:col-span-2">
                  <div className="font-semibold text-slate-300 mb-1">Hướng dẫn thao tác trên Semrush UI</div>
                  <ol className="list-decimal list-inside space-y-1 text-slate-400">
                    {r.semrush_steps.map((st, idx) => (
                      <li key={idx}>{st}</li>
                    ))}
                  </ol>
                </div>
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
