'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { AlertTriangle, CheckCircle2, ClipboardCheck, Layers, Map, Wrench } from 'lucide-react';
import { useProject } from '@/context/ProjectContext';
import { ApiError, apiRequest } from '@/lib/api';
import type { KeywordMappingItem, OpportunityItem, StandardizedError } from '@/lib/types';
import { ErrorBanner } from '@/components/ErrorBanner';
import { StatusBadge } from '@/components/StatusBadge';
import { ResponsiveTable } from '@/components/ResponsiveTable';

interface OpportunitiesPayload {
  serp_verified: boolean;
  serp_status: string;
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

  const loadData = useCallback(async () => {
    if (!activeProject) return;
    try {
      const res = await apiRequest<OpportunitiesPayload>(`/api/v1/projects/${activeProject.id}/opportunities`);
      setData(res);
    } catch (err) {
      if (err instanceof ApiError && err.structured) setError(err.structured);
    }
  }, [activeProject]);

  useEffect(() => {
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
    setBuilding(true);
    setError(null);
    try {
      const res = await apiRequest<{
        revision: number;
        mappings_count: number;
        approvals_created: number;
        serp_status: string;
        navigation_eligible: boolean;
        next_step_href: string;
      }>(`/api/v1/projects/${activeProject.id}/mapping/preview`, { method: 'POST' });
      await loadData();
      await refreshProjects(activeProject.id);
      showCompletionPopup({
        title: `Đã lập Keyword Mapping revision #${res.revision}`,
        message: `Đã lưu ${res.mappings_count} dòng mapping (${res.serp_status}) và tạo ${res.approvals_created} mục chờ bạn phê duyệt.`,
        nextStepLabel: res.approvals_created > 0 ? 'Chờ phê duyệt' : 'Bước 07 — Content Brief',
        nextStepHref: res.next_step_href,
        navigationEligible: res.navigation_eligible,
      });
    } catch (err) {
      if (err instanceof ApiError && err.structured) setError(err.structured);
    } finally {
      setBuilding(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Bước 06 — Kế hoạch bài viết & Keyword Mapping</h1>
          <p className="mt-1 text-sm text-slate-400">
            Xây dựng cơ hội bài viết dựa trên bằng chứng Semrush. Không có màn hình nhập SERP thủ công; nếu thiếu file ORGANIC_RESULTS, kế hoạch luôn được gắn <code className="text-amber-300">SERP_NOT_VERIFIED</code>.
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
              data.serp_verified
                ? 'border-emerald-500/30 bg-emerald-950/20 text-emerald-200'
                : 'border-amber-500/35 bg-amber-950/20 text-amber-200'
            }`}
          >
            <div className="flex items-center justify-between">
              <span className="font-bold flex items-center gap-1.5">
                {data.serp_verified ? <CheckCircle2 className="h-4 w-4" /> : <AlertTriangle className="h-4 w-4" />}
                Trạng thái bằng chứng SERP
              </span>
              <StatusBadge status={data.serp_status} />
            </div>
            <p className="text-slate-300">
              {data.serp_verified
                ? 'Đã đối chiếu bằng chứng ORGANIC_RESULTS từ Semrush. Sau khi người dùng phê duyệt Mapping, bạn có thể xuất Content Brief CHÍNH THỨC.'
                : 'Chưa có file ORGANIC_RESULTS: kế hoạch hiện tại là DỰ THẢO (SERP_NOT_VERIFIED). Hệ thống KHÔNG giả vờ đã phân tích Top 10 Google.'}
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
          <ResponsiveTable caption="Bảng kế hoạch Keyword Mapping theo bằng chứng">
            <thead>
              <tr>
                <th scope="col">Keyword chính</th>
                <th scope="col">Loại trang & URL</th>
                <th scope="col">Metrics & Nguồn</th>
                <th scope="col">Ưu tiên / Giá trị / Công sức</th>
                <th scope="col">Đề xuất gộp/tách & Trạng thái</th>
                <th scope="col">Phê duyệt</th>
              </tr>
            </thead>
            <tbody>
              {data.mappings.map((m) => (
                <tr key={m.id}>
                  <th scope="row">
                    <div>{m.primary_keyword}</div>
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
                  </td>
                  <td data-label="Metrics & Nguồn" className="text-xs">
                    <div className="font-mono">
                      Vol: {m.volume !== null ? m.volume.toLocaleString('vi-VN') : 'null'} · KD: {m.kd !== null ? `${m.kd}%` : 'null'}
                    </div>
                    <div className="text-slate-400">Intent: {m.intent || 'thiếu'}</div>
                    <div className="text-[11px] text-slate-500">{m.metrics_source}</div>
                  </td>
                  <td data-label="Ưu tiên" className="text-xs">
                    <span className="font-mono font-bold text-sky-300">{m.priority}</span> · Biz: {m.business_value} · Effort: {m.effort}
                  </td>
                  <td data-label="Đề xuất" className="text-xs max-w-xs space-y-1.5">
                    <div className="flex flex-wrap gap-1">
                      <StatusBadge status={m.serp_status} />
                      <StatusBadge status={m.content_status} />
                    </div>
                    <p className="text-slate-400 leading-relaxed">{m.merge_split_proposal}</p>
                  </td>
                  <td data-label="Phê duyệt">
                    <StatusBadge status={m.is_approved ? 'APPROVED' : 'PENDING'} />
                  </td>
                </tr>
              ))}
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
