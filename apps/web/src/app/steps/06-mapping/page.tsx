'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { AlertTriangle, ArrowRight, CheckCircle2, ClipboardCheck, Layers, Map, Wrench } from 'lucide-react';
import { useProject } from '@/context/ProjectContext';
import { ApiError, apiRequest } from '@/lib/api';
import type { KeywordMappingItem, OpportunityItem, StandardizedError } from '@/lib/types';
import { ErrorBanner } from '@/components/ErrorBanner';
import { StatusBadge } from '@/components/StatusBadge';
import { ResponsiveTable } from '@/components/ResponsiveTable';

interface OpportunitiesPayload {
  policy_version?: string;
  serp_verified: boolean;
  serp_status: string;
  eligible_official_count?: number;
  plan_mode: string;
  article_quota: {
    soft_min: number;
    soft_max: number;
    current_articles: number;
    non_article_assets_excluded: number;
    research_gaps: number;
  };
  mappings: KeywordMappingItem[];
  article_opportunities: OpportunityItem[];
  non_article_assets: OpportunityItem[];
  research_gaps: OpportunityItem[];
}

export default function Step06MappingPage() {
  const { activeProject, refreshProjects, showCompletionPopup } = useProject();
  const [data, setData] = useState<OpportunitiesPayload | null>(null);
  const [building, setBuilding] = useState(false);
  const [error, setError] = useState<StandardizedError | null>(null);
  const currentPidRef = useRef<string | null>(null);
  currentPidRef.current = activeProject?.id ?? null;

  const loadData = useCallback(async () => {
    if (!activeProject) return;
    const reqPid = activeProject.id;
    try {
      const res = await apiRequest<OpportunitiesPayload>(`/api/v1/projects/${reqPid}/opportunities`);
      if (currentPidRef.current === reqPid) setData(res);
    } catch (err) {
      if (currentPidRef.current === reqPid && err instanceof ApiError && err.structured) setError(err.structured);
    }
  }, [activeProject]);

  useEffect(() => {
    setData(null);
    setError(null);
    void loadData();
  }, [loadData]);

  if (!activeProject) {
    return (
      <div className="rounded-2xl border border-slate-800 bg-surface-900 p-8 text-center text-sm text-slate-300">
        Chưa chọn dự án. <Link href="/projects" className="text-sky-400 underline">Chọn dự án trước</Link>.
      </div>
    );
  }

  const handleGenerateMapping = async () => {
    const reqPid = activeProject.id;
    setBuilding(true);
    setError(null);
    try {
      const res = await apiRequest<{
        revision: number;
        mappings_count: number;
        approvals_created: number;
        approvals_superseded?: number;
        briefs_marked_stale?: number;
        serp_status: string;
        navigation_eligible: boolean;
        next_step_href: string;
      }>(`/api/v1/projects/${reqPid}/mapping/preview`, { method: 'POST' });
      if (currentPidRef.current !== reqPid) return;
      await loadData();
      await refreshProjects(reqPid);
      if (res.navigation_eligible) {
        showCompletionPopup({
          title: `Đã cập nhật Keyword Mapping rev #${res.revision}`,
          message: `Đã lưu ${res.mappings_count} dòng mapping (${res.serp_status}) vào SQLite.`,
          nextStepLabel: 'Bước 07 — Content Brief',
          nextStepHref: res.next_step_href,
          navigationEligible: true,
        });
      }
    } catch (err) {
      if (currentPidRef.current === reqPid && err instanceof ApiError && err.structured) setError(err.structured);
    } finally {
      if (currentPidRef.current === reqPid) setBuilding(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Bước 06 — Kế hoạch bài viết & Keyword Mapping</h1>
          <p className="mt-1 text-sm text-slate-400">
            Mỗi Mapping được kiểm chứng độc lập theo đúng từ khóa, đúng thị trường và đúng phiên bản/fingerprint. Không có bước nhập SERP thủ công; mục chưa đủ SERP luôn gắn <code className="text-amber-300">SERP_NOT_VERIFIED</code> hoặc <code className="text-orange-300">PARTIAL_SERP_EVIDENCE</code>.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          <button
            type="button"
            disabled={building}
            onClick={() => void handleGenerateMapping()}
            className="inline-flex items-center gap-2 rounded-xl bg-sky-500 px-4 py-2.5 text-sm font-semibold text-slate-950 hover:bg-sky-400 disabled:opacity-50 transition"
          >
            <Map className="h-4 w-4" />
            {building ? 'Đang lập Keyword Mapping…' : 'Lập / Cập nhật Keyword Mapping'}
          </button>
          <Link
            href="/approvals"
            className="inline-flex items-center gap-1.5 rounded-xl border border-amber-500/40 bg-amber-500/15 px-4 py-2.5 text-xs font-semibold text-amber-200 hover:bg-amber-500/25"
          >
            <ClipboardCheck className="h-4 w-4" />
            Mở Chờ phê duyệt
          </Link>
        </div>
      </div>

      <ErrorBanner error={error} onDismiss={() => setError(null)} />

      {/* SERP Honesty Banner & Soft Quota */}
      {data && (
        <div className="grid gap-4 lg:grid-cols-2">
          <div
            className={`rounded-2xl border p-4 text-xs space-y-1.5 ${
              data.serp_status === 'SERP_VERIFIED' || data.serp_status === 'TOP_10_VERIFIED'
                ? 'border-emerald-500/30 bg-emerald-950/20 text-emerald-200'
                : 'border-amber-500/35 bg-amber-950/20 text-amber-200'
            }`}
          >
            <div className="flex items-center justify-between gap-2">
              <span className="font-bold flex items-center gap-1.5">
                {data.serp_verified ? <CheckCircle2 className="h-4 w-4" /> : <AlertTriangle className="h-4 w-4" />}
                Bằng chứng SERP & Điều kiện Brief chính thức
              </span>
              <StatusBadge status={data.serp_status} />
            </div>
            <p className="text-slate-300">
              Đủ điều kiện xuất Brief CHÍNH THỨC:{' '}
              <strong className="text-sky-300">
                {data.eligible_official_count ?? 0}/{data.mappings.length}
              </strong>{' '}
              mapping (Policy v{data.policy_version || '1.6.2'}). Chỉ chứng nhận trên <strong>1 snapshot SERP thống nhất</strong> cho đúng từ khóa &amp; thị trường (không gộp nhiều batch).
            </p>
          </div>

          <div className="rounded-2xl border border-slate-800 bg-surface-900 p-4 text-xs space-y-1.5">
            <div className="font-bold text-slate-100 flex items-center gap-1.5">
              <Layers className="h-4 w-4 text-sky-400" />
              Mục tiêu mềm bài ARTICLE ({data.article_quota.soft_min}–{data.article_quota.soft_max} bài)
            </div>
            <p className="text-slate-300">
              Bài ARTICLE hiện có: <strong className="text-sky-300">{data.article_quota.current_articles}</strong> · Tài nguyên TOOL/DOWNLOAD/SERVICE (không tính vào quota):{' '}
              <strong className="text-violet-300">{data.article_quota.non_article_assets_excluded}</strong> · Khoảng trống nghiên cứu:{' '}
              <strong className="text-amber-300">{data.article_quota.research_gaps}</strong>.
            </p>
            <p className="text-slate-500">Không ép tạo đủ 5–7 bài nếu chưa đủ nhu cầu độc lập và bằng chứng.</p>
          </div>
        </div>
      )}

      {/* Main Keyword Mapping Table */}
      <section className="space-y-3">
        <h2 className="text-base font-bold text-slate-100">Bảng Keyword Mapping ({data?.mappings.length ?? 0})</h2>
        {!data || data.mappings.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-slate-700 bg-surface-900/50 p-10 text-center text-sm text-slate-400">
            Chưa có Keyword Mapping. Bấm <strong>Lập / Cập nhật Keyword Mapping</strong> để dựng kế hoạch từ dữ liệu SQLite.
          </div>
        ) : (
          <ResponsiveTable caption="Bảng kế hoạch Keyword Mapping theo bằng chứng từng từ khóa">
            <thead>
              <tr>
                <th scope="col">Keyword chính & Phiên bản</th>
                <th scope="col">Loại trang & URL</th>
                <th scope="col">Metrics & Nguồn</th>
                <th scope="col">SERP & Phê duyệt</th>
                <th scope="col">Điểm nghẽn cụ thể & Hành động sửa</th>
              </tr>
            </thead>
            <tbody>
              {data.mappings.map((m) => {
                const elig = m.eligibility;
                const blockers = elig?.blockers || [];
                const needsReapproval = elig?.approval_state === 'STALE_SUPERSEDED';
                return (
                  <tr key={m.id}>
                    <th scope="row">
                      <div>{m.primary_keyword}</div>
                      <div className="mt-1 font-mono text-[11px] font-normal text-slate-400">
                        rev #{m.revision} {m.content_fingerprint ? `· fp:${m.content_fingerprint.slice(0, 8)}` : ''}
                      </div>
                      {m.secondary_keywords.length > 0 && (
                        <div className="mt-1 text-[11px] font-normal text-slate-400">
                          Phụ: {m.secondary_keywords.slice(0, 4).join(', ')}
                        </div>
                      )}
                    </th>
                    <td data-label="Loại trang & URL">
                      <span className="rounded bg-violet-500/20 px-2 py-0.5 text-xs font-semibold text-violet-200">
                        {m.page_type}
                      </span>
                      <div className="mt-1 font-mono text-xs text-sky-300">{m.proposed_url}</div>
                      <div className="mt-1 text-[11px] text-slate-400">
                        {m.priority} · Biz: {m.business_value} · Effort: {m.effort}
                      </div>
                    </td>
                    <td data-label="Metrics & Nguồn" className="text-xs">
                      <div className="font-mono">
                        Vol: {m.volume !== null ? m.volume.toLocaleString('vi-VN') : 'null'} · KD: {m.kd !== null ? `${m.kd}%` : 'null'}
                      </div>
                      <div className="text-slate-400">Intent: {m.intent || 'thiếu'}</div>
                      <div className="text-[11px] text-slate-500">{m.metrics_source}</div>
                    </td>
                    <td data-label="SERP & Phê duyệt" className="space-y-1.5">
                      <div className="flex flex-wrap gap-1">
                        <StatusBadge status={elig?.serp_tier || m.serp_status} />
                        {needsReapproval ? (
                          <StatusBadge status="STALE_SUPERSEDED" />
                        ) : (
                          <StatusBadge status={m.is_approved ? 'APPROVED' : 'PENDING'} />
                        )}
                      </div>
                      <div className="text-[11px] text-slate-400">
                        Brief chính thức:{' '}
                        <strong className={elig?.eligible_official ? 'text-emerald-300' : 'text-amber-300'}>
                          {elig?.eligible_official ? 'ĐỦ ĐIỀU KIỆN' : 'CHƯA ĐỦ GATE'}
                        </strong>
                      </div>
                      {elig?.serp_evidence?.selected_batch_id && (
                        <div className="font-mono text-[10px] text-slate-500">
                          Snapshot: {elig.serp_evidence.selected_batch_id}
                          {elig.serp_evidence.snapshot_identity?.timestamp_kind
                            ? ` (${elig.serp_evidence.snapshot_identity.timestamp_kind})`
                            : ''}
                        </div>
                      )}
                    </td>
                    <td data-label="Điểm nghẽn" className="text-xs max-w-sm space-y-1.5">
                      {blockers.length === 0 ? (
                        <div className="inline-flex items-center gap-1.5 text-emerald-300 font-medium">
                          <CheckCircle2 className="h-4 w-4" /> Đạt đủ Quality Gates cho Brief chính thức
                        </div>
                      ) : (
                        <ul className="space-y-1.5">
                          {blockers.map((b, idx) => (
                            <li key={idx} className="rounded-lg border border-amber-500/25 bg-amber-950/20 p-2 space-y-1">
                              <div className="font-mono text-[11px] font-semibold text-amber-200">{b.code}</div>
                              <p className="text-slate-300">{b.reason}</p>
                              {b.cta_href && (
                                <Link href={b.cta_href} className="inline-flex items-center gap-1 text-sky-400 hover:text-sky-300 font-semibold">
                                  {b.cta_label || 'Khắc phục'} <ArrowRight className="h-3 w-3" />
                                </Link>
                              )}
                            </li>
                          ))}
                        </ul>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </ResponsiveTable>
        )}
      </section>

      {/* Separate Panels: Non-Article Assets & Research Gaps */}
      {data && (data.non_article_assets.length > 0 || data.research_gaps.length > 0) && (
        <div className="grid gap-5 md:grid-cols-2">
          <section className="rounded-2xl border border-violet-500/30 bg-surface-900 p-5 space-y-3">
            <h3 className="text-sm font-bold text-violet-200 flex items-center gap-2">
              <Wrench className="h-4 w-4 text-violet-400" />
              Tài nguyên TOOL / DOWNLOAD / SERVICE (Không tính vào quota ARTICLE)
            </h3>
            {data.non_article_assets.length === 0 ? (
              <p className="text-xs text-slate-500">Không có tài nguyên phi bài viết.</p>
            ) : (
              data.non_article_assets.map((o) => (
                <div key={o.id} className="rounded-xl border border-slate-800 bg-surface-850 p-3 text-xs space-y-1">
                  <div className="flex items-center justify-between gap-2">
                    <strong className="text-slate-100">{o.primary_keyword}</strong>
                    <span className="rounded bg-violet-500/20 px-2 py-0.5 text-[11px] font-semibold text-violet-200">{o.page_type}</span>
                  </div>
                  <p className="text-slate-400">{o.rationale}</p>
                </div>
              ))
            )}
          </section>

          <section className="rounded-2xl border border-amber-500/30 bg-surface-900 p-5 space-y-3">
            <h3 className="text-sm font-bold text-amber-200">
              Khoảng trống nghiên cứu (Chưa đủ metrics Semrush)
            </h3>
            {data.research_gaps.length === 0 ? (
              <p className="text-xs text-slate-500">Tất cả nhóm nhu cầu hiện tại đã có dòng metrics khớp.</p>
            ) : (
              data.research_gaps.map((g) => (
                <div key={g.id} className="rounded-xl border border-slate-800 bg-surface-850 p-3 text-xs space-y-1">
                  <strong className="text-amber-200">{g.primary_keyword}</strong>
                  <p className="text-slate-400">{g.rationale}</p>
                </div>
              ))
            )}
          </section>
        </div>
      )}
    </div>
  );
}
