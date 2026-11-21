'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import {
  CheckCircle2,
  MessageSquareWarning,
  RefreshCw,
  RotateCw,
  SearchCheck,
  ShieldCheck,
} from 'lucide-react';
import { useProject } from '@/context/ProjectContext';
import { ApiError, apiRequest } from '@/lib/api';
import type { CritiqueItem, EvidenceRowItem, QualityGateItem, StandardizedError } from '@/lib/types';
import { ErrorBanner } from '@/components/ErrorBanner';
import { StatusBadge } from '@/components/StatusBadge';
import { ResponsiveTable } from '@/components/ResponsiveTable';

interface EvidencePayload {
  batches: Array<{
    id: string;
    report_type: string;
    market: string;
    locale: string;
    total_raw_rows: number;
    total_normalized_rows: number;
    duplicate_rows_detected: number;
    status: string;
    source_timestamp: string | null;
  }>;
  total_evidence_rows: number;
  rows: EvidenceRowItem[];
  post_critiques: CritiqueItem[];
  research_cycle: number;
  max_critique_rounds_per_cycle: number;
  quality_gates: QualityGateItem[];
  summary: {
    metrics_rows_count: number;
    organic_rows_count: number;
    duplicate_rows_count: number;
    missing_volume_count: number;
    missing_kd_count: number;
    missing_intent_count: number;
    source_coverage_ratio: number;
    low_volume_keywords: string[];
    serp_verified: boolean;
    serp_status: string;
    ready_for_brief: boolean;
  };
}

export default function Step05EvidencePage() {
  const { activeProject, refreshProjects, showCompletionPopup } = useProject();
  const [data, setData] = useState<EvidencePayload | null>(null);
  const [tab, setTab] = useState<'METRICS' | 'ORGANIC_RESULTS'>('METRICS');
  const [runningCritic, setRunningCritic] = useState(false);
  const [approvingFu, setApprovingFu] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<StandardizedError | null>(null);
  const currentPidRef = useRef<string | null>(null);
  currentPidRef.current = activeProject?.id ?? null;

  const loadEvidence = useCallback(async () => {
    if (!activeProject) return;
    const reqPid = activeProject.id;
    try {
      const res = await apiRequest<EvidencePayload>(`/api/v1/projects/${reqPid}/evidence?limit=250`);
      if (currentPidRef.current === reqPid) setData(res);
    } catch (err) {
      if (currentPidRef.current === reqPid && err instanceof ApiError && err.structured) setError(err.structured);
    }
  }, [activeProject]);

  useEffect(() => {
    setData(null);
    setNotice(null);
    setError(null);
    void loadEvidence();
  }, [loadEvidence]);

  if (!activeProject) {
    return (
      <div className="rounded-2xl border border-slate-800 bg-surface-900 p-8 text-center text-sm text-slate-300">
        Chưa chọn dự án. <Link href="/projects" className="text-sky-400 underline">Chọn dự án trước</Link>.
      </div>
    );
  }

  const handleRunCritic = async () => {
    setRunningCritic(true);
    setError(null);
    setNotice(null);
    try {
      const res = await apiRequest<{
        provider: string;
        actual_model: string;
        navigation_eligible: boolean;
        next_step_href: string;
        critique: CritiqueItem;
      }>(`/api/v1/projects/${activeProject.id}/ai/critic`, {
        method: 'POST',
        body: JSON.stringify({ stage: 'POST_SEMRUSH' }),
      });
      await loadEvidence();
      await refreshProjects(activeProject.id);
      if (res.navigation_eligible) {
        showCompletionPopup({
          title: 'AI Critic hoàn tất đối chiếu bằng chứng',
          message: `Đã đối chiếu xong bằng ${res.provider.toUpperCase()} (${res.actual_model}).`,
          nextStepLabel: 'Bước 06 — Kế hoạch bài viết / Mapping',
          nextStepHref: res.next_step_href,
          navigationEligible: true,
        });
      } else {
        setNotice(
          `AI Critic (${res.provider.toUpperCase()}/${res.actual_model}) đã lưu lượt phản biện #${res.critique.round_number} và đề xuất bổ sung dữ liệu — không tự chuyển bước để bạn xem xét.`
        );
      }
    } catch (err) {
      if (err instanceof ApiError && err.structured) setError(err.structured);
    } finally {
      setRunningCritic(false);
    }
  };

  const handleApproveFollowups = async (critiqueId: string) => {
    setApprovingFu(true);
    setError(null);
    try {
      const res = await apiRequest<{
        created_requests: unknown[];
        navigation_eligible: boolean;
        next_step_href: string;
      }>(`/api/v1/projects/${activeProject.id}/research/followups`, {
        method: 'POST',
        body: JSON.stringify({ critique_id: critiqueId }),
      });
      await refreshProjects(activeProject.id);
      showCompletionPopup({
        title: `Đã duyệt ${res.created_requests.length} yêu cầu nghiên cứu bổ sung`,
        message: 'Các phiếu Yêu cầu Semrush bổ sung từ AI Critic đã được tạo vào SQLite.',
        nextStepLabel: 'Bước 03 — Yêu cầu Semrush',
        nextStepHref: res.next_step_href,
        navigationEligible: true,
      });
    } catch (err) {
      if (err instanceof ApiError && err.structured) setError(err.structured);
    } finally {
      setApprovingFu(false);
    }
  };

  const handleReopenCycle = async () => {
    setError(null);
    try {
      const res = await apiRequest<{ research_cycle: number }>(`/api/v1/projects/${activeProject.id}/research/reopen-cycle`, {
        method: 'POST',
      });
      setNotice(`Đã mở chu kỳ nghiên cứu mới #${res.research_cycle}. Bạn có thể chạy thêm tối đa 2 lượt AI Critic sau khi bổ sung bằng chứng.`);
      await loadEvidence();
      await refreshProjects(activeProject.id);
    } catch (err) {
      if (err instanceof ApiError && err.structured) setError(err.structured);
    }
  };

  const visibleRows = (data?.rows || []).filter((r) => r.row_type === tab);
  const currentCycleCritiques = (data?.post_critiques || []).filter(
    (c) => c.research_cycle === data?.research_cycle
  );

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Bước 05 — Kiểm tra dữ liệu & AI Critic sau Semrush</h1>
          <p className="mt-1 text-sm text-slate-400">
            So khớp bằng chứng Semrush trong SQLite với bộ keyword nguồn, chạy Quality Gates deterministic và phản biện bằng AI Critic (tối đa 2 lượt/chu kỳ).
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          <button
            type="button"
            onClick={() => void handleRunCritic()}
            disabled={runningCritic}
            className="inline-flex items-center gap-2 rounded-xl bg-sky-500 px-4 py-2.5 text-sm font-semibold text-slate-950 hover:bg-sky-400 disabled:opacity-50 transition"
          >
            <MessageSquareWarning className="h-4 w-4" />
            {runningCritic
              ? 'AI Critic đang đối chiếu…'
              : `Chạy AI Critic (Chu kỳ #${data?.research_cycle ?? 1} · ${currentCycleCritiques.length}/${data?.max_critique_rounds_per_cycle ?? 2})`}
          </button>
          <button
            type="button"
            onClick={() => void handleReopenCycle()}
            className="inline-flex items-center gap-1.5 rounded-xl border border-slate-700 bg-surface-900 px-3.5 py-2.5 text-xs font-medium text-slate-200 hover:bg-slate-800"
          >
            <RotateCw className="h-3.5 w-3.5" />
            Mở chu kỳ mới
          </button>
          <Link
            href="/steps/06-mapping"
            className="inline-flex items-center gap-1.5 rounded-xl bg-emerald-500/20 border border-emerald-500/35 px-4 py-2.5 text-xs font-semibold text-emerald-200 hover:bg-emerald-500/30"
          >
            Sang Bước 06 Mapping →
          </Link>
        </div>
      </div>

      <ErrorBanner error={error} onDismiss={() => setError(null)} />
      {notice && (
        <div className="rounded-xl border border-sky-500/30 bg-sky-950/25 p-3.5 text-xs text-sky-200">{notice}</div>
      )}

      {/* Deterministic Summary Stats */}
      {data && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div className="rounded-2xl border border-slate-800 bg-surface-900 p-4">
            <div className="text-xs text-slate-400">Metrics chuẩn hóa</div>
            <div className="mt-1 text-2xl font-bold text-slate-100">{data.summary.metrics_rows_count}</div>
            <div className="mt-1 text-[11px] text-slate-500">
              Thiếu KD: {data.summary.missing_kd_count} · Thiếu Intent: {data.summary.missing_intent_count}
            </div>
          </div>
          <div className="rounded-2xl border border-slate-800 bg-surface-900 p-4">
            <div className="text-xs text-slate-400">Bằng chứng Organic SERP</div>
            <div className="mt-1 text-2xl font-bold text-slate-100">{data.summary.organic_rows_count}</div>
            <div className="mt-1"><StatusBadge status={data.summary.serp_status} /></div>
          </div>
          <div className="rounded-2xl border border-slate-800 bg-surface-900 p-4">
            <div className="text-xs text-slate-400">Bao phủ keyword nguồn</div>
            <div className="mt-1 text-2xl font-bold text-sky-300">
              {Math.round((data.summary.source_coverage_ratio || 0) * 100)}%
            </div>
            <div className="mt-1 text-[11px] text-slate-500">
              Trùng lặp giữ nguyên: {data.summary.duplicate_rows_count}
            </div>
          </div>
          <div className="rounded-2xl border border-slate-800 bg-surface-900 p-4">
            <div className="text-xs text-slate-400">Keyword Volume thấp giữ lại (B2B)</div>
            <div className="mt-1 text-2xl font-bold text-indigo-300">{data.summary.low_volume_keywords.length}</div>
            <div className="mt-1 text-[11px] text-slate-500">Không lọc bỏ bởi ngưỡng cứng</div>
          </div>
        </div>
      )}

      {/* Post-Semrush Critic Results */}
      {data && data.post_critiques.length > 0 && (
        <section className="space-y-3">
          <h2 className="text-base font-bold text-slate-100 flex items-center gap-2">
            <ShieldCheck className="h-5 w-5 text-amber-400" />
            Phản biện AI Critic sau Semrush ({data.post_critiques.length} lượt)
          </h2>
          {data.post_critiques.map((c) => (
            <article key={c.id} className="rounded-2xl border border-amber-500/30 bg-surface-900 p-5 space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs text-slate-400">
                    Chu kỳ #{c.research_cycle ?? 1} · Lượt {c.round_number}
                  </span>
                  <StatusBadge status={c.decision_status} />
                </div>
                <span className="text-xs text-slate-500">
                  {c.created_at ? new Date(c.created_at).toLocaleString('vi-VN') : ''}
                </span>
              </div>

              <div className="grid gap-4 md:grid-cols-3 text-xs">
                <div className="rounded-xl bg-emerald-950/20 border border-emerald-500/20 p-3 space-y-1">
                  <div className="font-semibold text-emerald-300">Bằng chứng ủng hộ</div>
                  {c.supporting_evidence.map((s, i) => <p key={i} className="text-slate-300">• {s}</p>)}
                </div>
                <div className="rounded-xl bg-rose-950/20 border border-rose-500/25 p-3 space-y-1">
                  <div className="font-semibold text-rose-300">Phản biện mạnh nhất</div>
                  {c.counterarguments.map((s, i) => <p key={i} className="text-slate-200">• {s}</p>)}
                </div>
                <div className="rounded-xl bg-amber-950/20 border border-amber-500/20 p-3 space-y-1">
                  <div className="font-semibold text-amber-300">Dữ liệu còn thiếu</div>
                  {c.missing_data.length ? c.missing_data.map((s, i) => <p key={i} className="text-slate-300">• {s}</p>) : <p className="text-slate-400">Không ghi nhận thiếu hụt chính.</p>}
                </div>
              </div>

              {c.followup_requests.length > 0 && (
                <div className="rounded-xl border border-sky-500/30 bg-surface-850 p-4 space-y-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="text-xs font-bold text-sky-300">
                      Đề xuất nghiên cứu bổ sung từ AI Critic ({c.followup_requests.length})
                    </div>
                    <button
                      type="button"
                      disabled={approvingFu}
                      onClick={() => void handleApproveFollowups(c.id)}
                      className="inline-flex items-center gap-1.5 rounded-lg bg-sky-500 px-3.5 py-1.5 text-xs font-semibold text-slate-950 hover:bg-sky-400 disabled:opacity-50"
                    >
                      <SearchCheck className="h-3.5 w-3.5" />
                      Duyệt yêu cầu nghiên cứu bổ sung
                    </button>
                  </div>
                  <ul className="space-y-1 text-xs text-slate-300">
                    {c.followup_requests.map((fu, idx) => (
                      <li key={idx}>
                        <span className="font-mono text-violet-300">[{fu.report_type}]</span>{' '}
                        <strong>{fu.seed_keyword}</strong> — {fu.purpose}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              <p className="text-xs text-sky-200">
                <strong>Hành động tiếp theo:</strong> {c.next_action}
              </p>
            </article>
          ))}
        </section>
      )}

      {/* Evidence Rows Table */}
      <section className="rounded-2xl border border-slate-800 bg-surface-900 p-5 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setTab('METRICS')}
              className={`rounded-lg px-3.5 py-1.5 text-xs font-semibold transition ${
                tab === 'METRICS' ? 'bg-sky-500 text-slate-950' : 'bg-surface-850 text-slate-300 hover:bg-slate-800'
              }`}
            >
              Keyword Metrics ({data?.summary.metrics_rows_count ?? 0})
            </button>
            <button
              type="button"
              onClick={() => setTab('ORGANIC_RESULTS')}
              className={`rounded-lg px-3.5 py-1.5 text-xs font-semibold transition ${
                tab === 'ORGANIC_RESULTS' ? 'bg-sky-500 text-slate-950' : 'bg-surface-850 text-slate-300 hover:bg-slate-800'
              }`}
            >
              Organic Results / SERP ({data?.summary.organic_rows_count ?? 0})
            </button>
          </div>
          <button
            type="button"
            onClick={() => void loadEvidence()}
            className="inline-flex items-center gap-1 rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-300 hover:bg-slate-800"
          >
            <RefreshCw className="h-3.5 w-3.5" /> Làm mới
          </button>
        </div>

        {visibleRows.length === 0 ? (
          <div className="rounded-xl border border-dashed border-slate-700 p-8 text-center text-xs text-slate-400">
            Chưa có dòng dữ liệu {tab} nào. Hãy upload file Semrush tại{' '}
            <Link href="/steps/04-upload" className="text-sky-400 underline">Bước 04</Link>.
          </div>
        ) : tab === 'METRICS' ? (
          <ResponsiveTable caption="Bảng dữ liệu bằng chứng Keyword Metrics đã chuẩn hóa trong SQLite">
            <thead>
              <tr>
                <th scope="col">Keyword</th>
                <th scope="col">Volume</th>
                <th scope="col">KD</th>
                <th scope="col">Intent</th>
                <th scope="col">CPC</th>
                <th scope="col">Cảnh báo / Trùng</th>
              </tr>
            </thead>
            <tbody>
              {visibleRows.map((r) => (
                <tr key={r.id} className={r.is_duplicate ? 'opacity-60' : ''}>
                  <th scope="row">{r.keyword}</th>
                  <td data-label="Volume" className="font-mono">
                    {r.volume !== null ? r.volume.toLocaleString('vi-VN') : <span className="text-amber-300">null</span>}
                  </td>
                  <td data-label="KD" className="font-mono">
                    {r.kd !== null ? `${r.kd}%` : <span className="text-amber-300">thiếu</span>}
                  </td>
                  <td data-label="Intent">{r.intent || <span className="text-slate-500">thiếu</span>}</td>
                  <td data-label="CPC" className="font-mono">{r.cpc !== null ? r.cpc : '—'}</td>
                  <td data-label="Cảnh báo" className="text-xs">
                    {r.is_duplicate ? (
                      <span className="text-amber-300">Trùng (không cộng Vol)</span>
                    ) : r.warnings.length > 0 ? (
                      <span className="text-amber-200">{r.warnings.join(', ')}</span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-emerald-400">
                        <CheckCircle2 className="h-3.5 w-3.5" /> OK
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </ResponsiveTable>
        ) : (
          <ResponsiveTable caption="Bảng dữ liệu bằng chứng Organic Results đã chuẩn hóa trong SQLite">
            <thead>
              <tr>
                <th scope="col">Keyword</th>
                <th scope="col">Vị trí</th>
                <th scope="col">Loại kết quả & Hợp lệ</th>
                <th scope="col">Loại trang (giả định)</th>
                <th scope="col">URL</th>
                <th scope="col">Tiêu đề / Domain</th>
              </tr>
            </thead>
            <tbody>
              {visibleRows.map((r) => (
                <tr key={r.id} className={r.organic_valid === false || r.is_duplicate ? 'opacity-60' : ''}>
                  <th scope="row">{r.keyword || '—'}</th>
                  <td data-label="Vị trí" className="font-mono">#{r.organic_position ?? '—'}</td>
                  <td data-label="Loại kết quả" className="text-xs space-y-1">
                    <span
                      className={`rounded px-2 py-0.5 font-mono text-[11px] font-semibold ${
                        (r.serp_result_type || 'ORGANIC') === 'ORGANIC'
                          ? 'bg-emerald-500/20 text-emerald-200'
                          : 'bg-amber-500/20 text-amber-200'
                      }`}
                    >
                      {r.serp_result_type || 'ORGANIC'}
                    </span>
                    {r.organic_valid === false && <div className="text-[11px] text-amber-300">Loại khỏi Organic rank</div>}
                    {r.is_duplicate && <div className="text-[11px] text-amber-300">Trùng URL</div>}
                  </td>
                  <td data-label="Loại trang">
                    <span className="rounded bg-violet-500/20 px-2 py-0.5 text-xs font-semibold text-violet-200">
                      {r.organic_page_type || 'UNKNOWN'}
                    </span>
                  </td>
                  <td data-label="URL" className="font-mono text-xs text-sky-300 break-all">{r.organic_url}</td>
                  <td data-label="Tiêu đề" className="text-xs">{r.organic_title || r.organic_domain || '—'}</td>
                </tr>
              ))}
            </tbody>
          </ResponsiveTable>
        )}
      </section>
    </div>
  );
}
