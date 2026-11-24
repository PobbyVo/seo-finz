'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import {
  AlertCircle,
  CheckSquare,
  MessageSquareWarning,
  SearchCheck,
  Settings,
  Sparkles,
} from 'lucide-react';
import { useProject } from '@/context/ProjectContext';
import { ApiError, apiRequest } from '@/lib/api';
import type {
  CritiqueItem,
  DemandGroupItem,
  KeywordCandidateItem,
  StandardizedError,
} from '@/lib/types';
import { ErrorBanner } from '@/components/ErrorBanner';
import { StatusBadge } from '@/components/StatusBadge';

export default function Step02DemandMapPage() {
  const { activeProject, activeAI, refreshProjects, showCompletionPopup } = useProject();
  const [groups, setGroups] = useState<DemandGroupItem[]>([]);
  const [candidates, setCandidates] = useState<KeywordCandidateItem[]>([]);
  const [preCritiques, setPreCritiques] = useState<CritiqueItem[]>([]);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [showCritiquePanel, setShowCritiquePanel] = useState(true);
  const [analyzing, setAnalyzing] = useState(false);
  const [creatingReqs, setCreatingReqs] = useState(false);
  const [runInfo, setRunInfo] = useState<string | null>(null);
  const [error, setError] = useState<StandardizedError | null>(null);

  const loadDemandMap = useCallback(async () => {
    if (!activeProject) return;
    try {
      const data = await apiRequest<{
        demand_groups: DemandGroupItem[];
        candidates: KeywordCandidateItem[];
        pre_critiques: CritiqueItem[];
      }>(`/api/v1/projects/${activeProject.id}/demand-map`);
      setGroups(data.demand_groups);
      setCandidates(data.candidates);
      setPreCritiques(data.pre_critiques);
      setSelectedIds(new Set(data.demand_groups.map((g) => g.id)));
    } catch (err) {
      if (err instanceof ApiError && err.structured) setError(err.structured);
    }
  }, [activeProject]);

  useEffect(() => {
    void loadDemandMap();
  }, [loadDemandMap]);

  if (!activeProject) {
    return (
      <div className="rounded-2xl border border-slate-800 bg-surface-900 p-8 text-center text-sm text-slate-300">
        Chưa chọn dự án. <Link href="/projects" className="text-sky-400 underline">Chọn dự án trước</Link>.
      </div>
    );
  }

  const handleAnalyze = async () => {
    setAnalyzing(true);
    setError(null);
    setRunInfo(null);
    try {
      const res = await apiRequest<{
        provider: string;
        actual_model: string;
        fallback_events: Array<{ reason: string }>;
        summary: string;
        demand_groups: DemandGroupItem[];
      }>(`/api/v1/projects/${activeProject.id}/analyze-topic`, { method: 'POST' });
      let msg = `Đã phân tích bằng ${res.provider.toUpperCase()} (${res.actual_model}): ${res.summary}`;
      if (res.fallback_events?.length) {
        msg += ` | Gemini hạ bậc: ${res.fallback_events.map((e) => e.reason).join(' ')}`;
      }
      setRunInfo(msg);
      showCompletionPopup({title:"Đã hoàn tất phân tích",message:"Đã lưu kết quả phân tích vào dự án.",nextStepHref:"/steps/03-semrush",nextStepLabel:"Bước 03 — Phiếu Semrush",navigationEligible:true});
      await loadDemandMap();
      await refreshProjects(activeProject.id);
    } catch (err) {
      if (err instanceof ApiError && err.structured) setError(err.structured);
    } finally {
      setAnalyzing(false);
    }
  };

  const handlePromoteCandidate = async (candId: string, action: 'PROMOTE' | 'REQUEST_APPROVAL' | 'OUT_OF_SCOPE') => {
    setError(null);
    try {
      await apiRequest(`/api/v1/projects/${activeProject.id}/demand-map/candidates/${candId}/promote`, {
        method: 'POST',
        body: JSON.stringify({ action }),
      });
      await loadDemandMap();
      await refreshProjects(activeProject.id);
    } catch (err) {
      if (err instanceof ApiError && err.structured) setError(err.structured);
    }
  };

  const handleCreateSemrushRequests = async () => {
    const chosen = groups.filter((g) => selectedIds.has(g.id));
    if (!chosen.length) return;
    setCreatingReqs(true);
    setError(null);
    try {
      const items = chosen.map((g) => ({
        demand_group_id: g.id,
        seed_keyword: g.seed_keywords[0] || activeProject.primary_keyword_current || activeProject.primary_keyword_original,
        report_type: g.recommended_semrush_report || 'KEYWORD_OVERVIEW',
        market: activeProject.market || 'VN',
        purpose: `${g.name}: ${g.next_action}`,
        origin: 'ANALYST',
      }));
      const res = await apiRequest<{
        navigation_eligible: boolean;
        next_step_href: string;
        research_requests: unknown[];
      }>(`/api/v1/projects/${activeProject.id}/research-requests`, {
        method: 'POST',
        body: JSON.stringify({ items }),
      });
      await refreshProjects(activeProject.id);
      showCompletionPopup({
        title: `Đã tạo ${res.research_requests.length} phiếu Yêu cầu Semrush`,
        message: 'Các phiếu nghiên cứu thủ công đã lưu vào SQLite kèm hướng dẫn từng bước trên Semrush UI.',
        nextStepLabel: 'Bước 03 — Yêu cầu Semrush',
        nextStepHref: '/steps/03-semrush',
        navigationEligible: true,
      });
    } catch (err) {
      if (err instanceof ApiError && err.structured) setError(err.structured);
    } finally {
      setCreatingReqs(false);
    }
  };

  const toggleSelect = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Bước 02 — Bản đồ nhu cầu (AI Topic Intelligence)</h1>
          <p className="mt-1 text-sm text-slate-400">
            AI Topic Analyst & SEO Critic đọc dữ liệu SQLite để phân nhóm vấn đề người tìm kiếm, phản biện giả định và đề xuất báo cáo Semrush cần lấy.
            Search Intent ở bước này chỉ là giả định chưa xác minh SERP.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          {!activeAI && (
            <Link
              href="/settings/ai"
              className="inline-flex items-center gap-1.5 rounded-xl border border-amber-500/40 bg-amber-500/15 px-3.5 py-2 text-xs font-semibold text-amber-200 hover:bg-amber-500/25"
            >
              <Settings className="h-4 w-4" />
              Mở Settings AI
            </Link>
          )}
          <button
            type="button"
            onClick={() => void handleAnalyze()}
            disabled={analyzing}
            className="inline-flex items-center gap-2 rounded-xl bg-sky-500 px-4 py-2.5 text-sm font-semibold text-slate-950 hover:bg-sky-400 disabled:opacity-50 transition"
          >
            <Sparkles className="h-4 w-4" />
            {analyzing ? 'AI đang phân tích & phản biện…' : 'AI phân tích nhu cầu'}
          </button>
          <button
            type="button"
            onClick={() => setShowCritiquePanel((v) => !v)}
            className="inline-flex items-center gap-1.5 rounded-xl border border-slate-700 bg-surface-900 px-3.5 py-2.5 text-xs font-semibold text-slate-200 hover:bg-slate-800"
          >
            <MessageSquareWarning className="h-4 w-4 text-amber-400" />
            {showCritiquePanel ? 'Ẩn phản biện' : 'Xem phản biện'}
          </button>
          {groups.length > 0 && (
            <button
              type="button"
              disabled={creatingReqs || selectedIds.size === 0}
              onClick={() => void handleCreateSemrushRequests()}
              className="inline-flex items-center gap-1.5 rounded-xl bg-emerald-500/20 border border-emerald-400/40 px-4 py-2.5 text-xs font-semibold text-emerald-200 hover:bg-emerald-500/30 disabled:opacity-40"
            >
              <SearchCheck className="h-4 w-4" />
              Tạo yêu cầu Semrush ({selectedIds.size} nhóm đã chọn)
            </button>
          )}
        </div>
      </div>

      <ErrorBanner error={error} onDismiss={() => setError(null)} />

      {runInfo && (
        <div className="rounded-xl border border-sky-500/35 bg-sky-950/30 p-4 text-xs text-sky-200">{runInfo}</div>
      )}

      {/* Pre-Semrush Critic Panel */}
      {showCritiquePanel && preCritiques.length > 0 && (
        <section className="rounded-2xl border border-amber-500/30 bg-amber-950/15 p-5 space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-base font-bold text-amber-200 flex items-center gap-2">
              <MessageSquareWarning className="h-5 w-5 text-amber-400" />
              Phản biện của AI SEO Critic (Trước Semrush)
            </h2>
            <StatusBadge status={preCritiques[0].decision_status} />
          </div>
          <div className="grid gap-4 md:grid-cols-3 text-xs">
            <div className="space-y-1.5">
              <div className="font-semibold text-emerald-300">Bằng chứng ủng hộ</div>
              {preCritiques[0].supporting_evidence.map((item, i) => (
                <p key={i} className="text-slate-300">• {item}</p>
              ))}
            </div>
            <div className="space-y-1.5">
              <div className="font-semibold text-rose-300">Phản biện mạnh nhất</div>
              {preCritiques[0].counterarguments.map((item, i) => (
                <p key={i} className="text-slate-300">• {item}</p>
              ))}
            </div>
            <div className="space-y-1.5">
              <div className="font-semibold text-amber-300">Dữ liệu còn thiếu</div>
              {preCritiques[0].missing_data.map((item, i) => (
                <p key={i} className="text-slate-300">• {item}</p>
              ))}
            </div>
          </div>
          <p className="text-xs text-sky-200 pt-1">
            <strong>Hành động tiếp theo:</strong> {preCritiques[0].next_action}
          </p>
        </section>
      )}

      {/* Demand Group Cards — Every required field displayed together */}
      {groups.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-slate-700 bg-surface-900/50 p-10 text-center text-sm text-slate-400">
          Chưa có nhóm nhu cầu nào. Bấm <strong>AI phân tích nhu cầu</strong> để AI đọc dữ liệu SQLite của dự án{' '}
          <strong className="text-slate-200">{activeProject.code}</strong> và dựng Bản đồ nhu cầu.
        </div>
      ) : (
        <div className="grid gap-5 lg:grid-cols-2">
          {groups.map((g) => (
            <article
              key={g.id}
              className={`rounded-2xl border p-5 space-y-3.5 transition ${
                selectedIds.has(g.id)
                  ? 'border-sky-500/45 bg-surface-900'
                  : 'border-slate-800 bg-surface-900/60'
              }`}
            >
              <div className="flex items-start justify-between gap-3">
                <label className="flex items-start gap-2.5 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={selectedIds.has(g.id)}
                    onChange={() => toggleSelect(g.id)}
                    className="mt-1 h-4 w-4 rounded"
                  />
                  <div>
                    <h3 className="text-base font-bold text-slate-100">{g.name}</h3>
                    <div className="mt-1 flex flex-wrap gap-1.5">
                      <StatusBadge status={g.status} />
                      <span className="rounded-full bg-slate-800 px-2 py-0.5 text-[11px] font-semibold text-violet-300 border border-slate-700">
                        {g.assumed_page_type}
                      </span>
                      <span className="rounded-full bg-slate-800 px-2 py-0.5 text-[11px] text-slate-300 border border-slate-700">
                        {g.coverage_type}
                      </span>
                    </div>
                  </div>
                </label>
                <span className="rounded-lg bg-sky-500/15 px-2 py-1 font-mono text-[11px] font-semibold text-sky-300 shrink-0">
                  {g.recommended_semrush_report}
                </span>
              </div>

              <p className="text-xs leading-relaxed text-slate-200">
                <strong className="text-slate-400">Người tìm kiếm muốn gì:</strong> {g.user_need}
              </p>

              <div className="flex flex-wrap gap-1.5 text-[11px]">
                {g.seed_keywords.map((kw, i) => (
                  <span key={`s-${i}`} className="rounded-md bg-sky-500/15 border border-sky-500/30 px-2 py-0.5 font-medium text-sky-200">
                    Seed: {kw}
                  </span>
                ))}
                {g.related_keywords.map((kw, i) => (
                  <span key={`r-${i}`} className="rounded-md bg-slate-800 border border-slate-700 px-2 py-0.5 text-slate-300">
                    {kw}
                  </span>
                ))}
              </div>

              {/* Mandatory 4-pillar evidence & critique block */}
              <div className="grid gap-3 sm:grid-cols-2 text-xs">
                <div className="rounded-xl border border-emerald-500/20 bg-emerald-950/15 p-3 space-y-1">
                  <div className="font-semibold text-emerald-300">Bằng chứng ủng hộ & nguồn</div>
                  {g.supporting_evidence.map((e, i) => (
                    <p key={i} className="text-slate-300">• {e}</p>
                  ))}
                  <div className="pt-1 font-mono text-[11px] text-emerald-200/80">
                    source_refs: {g.source_refs.join(', ') || '(không có)'}
                  </div>
                </div>

                <div className="rounded-xl border border-rose-500/25 bg-rose-950/15 p-3 space-y-1">
                  <div className="font-semibold text-rose-300">Phản biện mạnh nhất</div>
                  <p className="text-slate-200">{g.strongest_counterargument}</p>
                  {g.boundary_note && (
                    <p className="text-[11px] text-slate-400 pt-1">Ranh giới Pillar: {g.boundary_note}</p>
                  )}
                </div>
              </div>

              <div className="rounded-xl border border-amber-500/20 bg-surface-850 p-3 text-xs space-y-1">
                <div className="font-semibold text-amber-300">Dữ liệu cần bổ sung để quyết định</div>
                {g.missing_data.map((m, i) => (
                  <p key={i} className="text-slate-300">• {m}</p>
                ))}
                <p className="pt-1 text-sky-300">
                  <strong>Hành động tiếp theo:</strong> {g.next_action}
                </p>
              </div>

              {g.critique_history.length > 0 && (
                <div className="border-t border-slate-800 pt-2.5 text-[11px] text-slate-400 space-y-1">
                  <div className="font-semibold text-slate-300">Lịch sử phản biện & cập nhật:</div>
                  {g.critique_history.map((h, i) => (
                    <p key={i}>
                      <span className="font-mono text-slate-500">[{h.stage}]</span> {h.note}
                    </p>
                  ))}
                </div>
              )}
            </article>
          ))}
        </div>
      )}

      {/* Proposed Candidates */}
      {candidates.length > 0 && (
        <section className="rounded-2xl border border-slate-800 bg-surface-900 p-5 space-y-3">
          <h2 className="text-base font-bold text-slate-100 flex items-center gap-2">
            <CheckSquare className="h-4 w-4 text-sky-400" />
            Ứng viên keyword AI đề xuất mở rộng ({candidates.length})
          </h2>
          <div className="space-y-2.5">
            {candidates.map((c) => (
              <div
                key={c.id}
                className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-800 bg-surface-850 p-3.5 text-xs"
              >
                <div className="space-y-1 max-w-2xl">
                  <div className="flex flex-wrap items-center gap-2">
                    <strong className="text-sm text-slate-100">{c.keyword}</strong>
                    <StatusBadge status={c.status} />
                    <span className="rounded bg-slate-800 px-2 py-0.5 text-[11px] text-slate-300">{c.assumed_page_type}</span>
                    {!c.source_ref_valid && (
                      <span className="inline-flex items-center gap-1 text-rose-300">
                        <AlertCircle className="h-3.5 w-3.5" /> source_ref chưa khớp nguồn
                      </span>
                    )}
                  </div>
                  <p className="text-slate-400">{c.rationale}</p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={() => void handlePromoteCandidate(c.id, 'PROMOTE')}
                    className="rounded-lg bg-sky-500/20 border border-sky-500/35 px-3 py-1.5 font-semibold text-sky-200 hover:bg-sky-500/30"
                  >
                    Đưa vào Bản đồ nhu cầu
                  </button>
                  <button
                    type="button"
                    onClick={() => void handlePromoteCandidate(c.id, 'REQUEST_APPROVAL')}
                    className="rounded-lg border border-amber-500/35 bg-amber-500/15 px-3 py-1.5 font-semibold text-amber-200 hover:bg-amber-500/25"
                  >
                    Chuyển Chờ phê duyệt
                  </button>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
