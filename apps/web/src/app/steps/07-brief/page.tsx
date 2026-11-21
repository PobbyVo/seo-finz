'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { BookOpen, Download, FileSpreadsheet, FileText, Printer, Sparkles } from 'lucide-react';
import { useProject } from '@/context/ProjectContext';
import { ApiError, apiRequest, downloadExportFile } from '@/lib/api';
import type { ContentBriefItem, StandardizedError } from '@/lib/types';
import { ErrorBanner } from '@/components/ErrorBanner';
import { StatusBadge } from '@/components/StatusBadge';

interface BriefsPayload {
  briefs: ContentBriefItem[];
  writing_formulas_catalog: Array<{ id: string; name: string; description: string }>;
  engagement_tactics_catalog: Array<{ number: number; code: string; text: string }>;
}

export default function Step07BriefPage() {
  const { activeProject, refreshProjects } = useProject();
  const [data, setData] = useState<BriefsPayload | null>(null);
  const [generating, setGenerating] = useState(false);
  const [exporting, setExporting] = useState<string | null>(null);
  const [showCatalog, setShowCatalog] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<StandardizedError | null>(null);

  const loadBriefs = useCallback(async () => {
    if (!activeProject) return;
    try {
      const res = await apiRequest<BriefsPayload>(`/api/v1/projects/${activeProject.id}/briefs`);
      setData(res);
    } catch (err) {
      if (err instanceof ApiError && err.structured) setError(err.structured);
    }
  }, [activeProject]);

  useEffect(() => {
    void loadBriefs();
  }, [loadBriefs]);

  if (!activeProject) {
    return (
      <div className="rounded-2xl border border-slate-800 bg-surface-900 p-8 text-center text-sm text-slate-300">
        Chưa chọn dự án. <Link href="/projects" className="text-sky-400 underline">Chọn dự án trước</Link>.
      </div>
    );
  }

  const canOfficial = Boolean(activeProject.workflow?.evidence_summary?.can_generate_official_brief);

  const handleGenerate = async (allowDraft: boolean) => {
    setGenerating(true);
    setError(null);
    setNotice(null);
    try {
      const res = await apiRequest<{ official_count: number; draft_count: number }>(
        `/api/v1/projects/${activeProject.id}/briefs/generate`,
        { method: 'POST', body: JSON.stringify({ allow_draft: allowDraft }) }
      );
      setNotice(
        `Đã tạo xong Content Brief: ${res.official_count} bản CHÍNH THỨC, ${res.draft_count} bản DỰ THẢO.`
      );
      await loadBriefs();
      await refreshProjects(activeProject.id);
    } catch (err) {
      if (err instanceof ApiError && err.structured) setError(err.structured);
    } finally {
      setGenerating(false);
    }
  };

  const handleExport = async (fmt: 'xlsx' | 'csv' | 'json' | 'html') => {
    setExporting(fmt);
    setError(null);
    try {
      const fname = await downloadExportFile(activeProject.id, fmt);
      setNotice(`Đã xuất thành công tệp ${fname} (không gọi Google Sheets API, tên file sinh theo dự án ${activeProject.code}).`);
    } catch (err) {
      setError({
        code: 'EXPORT_FAILED',
        reason: String(err),
        impact: 'Chưa tải được file xuất.',
        solution: 'Đảm bảo đã tạo ít nhất 1 Content Brief trước khi xuất.',
        next_action: 'Thử lại sau khi tạo Brief.',
      });
    } finally {
      setExporting(null);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Bước 07 — SEO Content Brief & Xuất Deliverables</h1>
          <p className="mt-1 text-sm text-slate-400">
            Gồm 3 bảng logic (Keyword Overview, Keyword Mapping, SEO Content Brief) + Writing Strategy cấp toàn bài (13 công thức viết & 16 chiến thuật thu hút độc giả).
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            disabled={generating || !canOfficial}
            onClick={() => void handleGenerate(false)}
            className="inline-flex items-center gap-2 rounded-xl bg-emerald-500 px-4 py-2.5 text-xs font-semibold text-slate-950 hover:bg-emerald-400 disabled:opacity-40 transition"
            title={canOfficial ? 'Đủ Quality Gates' : 'Cần phê duyệt Mapping và có ORGANIC_RESULTS để tạo bản CHÍNH THỨC'}
          >
            <Sparkles className="h-4 w-4" />
            Tạo Brief CHÍNH THỨC
          </button>
          <button
            type="button"
            disabled={generating}
            onClick={() => void handleGenerate(true)}
            className="inline-flex items-center gap-2 rounded-xl bg-sky-500/20 border border-sky-400/40 px-4 py-2.5 text-xs font-semibold text-sky-200 hover:bg-sky-500/30 disabled:opacity-40 transition"
          >
            <FileText className="h-4 w-4" />
            {generating ? 'Đang tạo Brief…' : 'Tạo Brief DỰ THẢO (hoặc cập nhật)'}
          </button>
          <button
            type="button"
            onClick={() => setShowCatalog((v) => !v)}
            className="inline-flex items-center gap-1.5 rounded-xl border border-slate-700 bg-surface-900 px-3.5 py-2.5 text-xs font-medium text-slate-200 hover:bg-slate-800"
          >
            <BookOpen className="h-4 w-4 text-violet-400" />
            {showCatalog ? 'Ẩn thư viện 13+16' : 'Thư viện 13 công thức & 16 chiến thuật'}
          </button>
        </div>
      </div>

      <ErrorBanner error={error} onDismiss={() => setError(null)} />
      {notice && (
        <div className="rounded-xl border border-emerald-500/35 bg-emerald-950/25 p-3.5 text-xs text-emerald-200">{notice}</div>
      )}

      {/* Export Bar */}
      <section className="rounded-2xl border border-slate-800 bg-surface-900 p-4 flex flex-wrap items-center justify-between gap-3">
        <div className="text-xs text-slate-300">
          <strong className="text-slate-100">Xuất tệp cục bộ:</strong> XLSX chứa đúng 3 sheet (<code className="text-sky-300">Keyword Overview</code>,{' '}
          <code className="text-sky-300">Keyword Mapping</code>, <code className="text-sky-300">SEO Content Brief</code>) đặt tên theo dự án{' '}
          <strong className="text-white">{activeProject.code}</strong>.
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            disabled={!!exporting}
            onClick={() => void handleExport('xlsx')}
            className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-500/20 border border-emerald-500/40 px-3 py-1.5 text-xs font-semibold text-emerald-200 hover:bg-emerald-500/30"
          >
            <FileSpreadsheet className="h-3.5 w-3.5" />
            {exporting === 'xlsx' ? 'Đang xuất…' : 'Xuất XLSX (3 bảng)'}
          </button>
          <button
            type="button"
            disabled={!!exporting}
            onClick={() => void handleExport('csv')}
            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-700 bg-surface-850 px-3 py-1.5 text-xs font-medium text-slate-200 hover:bg-slate-800"
          >
            <Download className="h-3.5 w-3.5" /> CSV
          </button>
          <button
            type="button"
            disabled={!!exporting}
            onClick={() => void handleExport('json')}
            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-700 bg-surface-850 px-3 py-1.5 text-xs font-medium text-slate-200 hover:bg-slate-800"
          >
            <Download className="h-3.5 w-3.5" /> JSON
          </button>
          <button
            type="button"
            disabled={!!exporting}
            onClick={() => void handleExport('html')}
            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-700 bg-surface-850 px-3 py-1.5 text-xs font-medium text-slate-200 hover:bg-slate-800"
          >
            <Printer className="h-3.5 w-3.5" /> Bản in HTML
          </button>
        </div>
      </section>

      {/* Optional 13 Formulas + 16 Engagement Tactics Library */}
      {showCatalog && data && (
        <section className="grid gap-5 lg:grid-cols-2 rounded-2xl border border-violet-500/30 bg-surface-900 p-5 text-xs">
          <div className="space-y-2">
            <h2 className="text-sm font-bold text-violet-200">Danh mục 13 công thức viết ({data.writing_formulas_catalog.length})</h2>
            <ul className="space-y-1.5 text-slate-300">
              {data.writing_formulas_catalog.map((f) => (
                <li key={f.id}>
                  <strong className="text-sky-300">{f.name}:</strong> {f.description}
                </li>
              ))}
            </ul>
          </div>
          <div className="space-y-2">
            <h2 className="text-sm font-bold text-violet-200">Thư viện 16 chiến thuật thu hút độc giả ({data.engagement_tactics_catalog.length})</h2>
            <ol className="space-y-1 text-slate-300 list-decimal list-inside">
              {data.engagement_tactics_catalog.map((t) => (
                <li key={t.code}>{t.text}</li>
              ))}
            </ol>
          </div>
        </section>
      )}

      {/* Brief Cards */}
      {!data || data.briefs.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-slate-700 bg-surface-900/50 p-10 text-center text-sm text-slate-400">
          Chưa có SEO Content Brief nào. Hoàn thành Bước 06 (Keyword Mapping) rồi bấm nút tạo Brief ở phía trên.
        </div>
      ) : (
        <div className="space-y-5">
          {data.briefs.map((b) => (
            <article key={b.id} className="rounded-2xl border border-slate-800 bg-surface-900 p-6 space-y-5">
              <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-800 pb-4">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-sm font-bold text-sky-300">{b.br_code}</span>
                    <StatusBadge status={b.brief_mode} />
                    <StatusBadge status={b.status} />
                    <span className="rounded bg-violet-500/20 px-2 py-0.5 text-xs font-semibold text-violet-200">
                      {b.content_type}
                    </span>
                    <span className="rounded bg-slate-800 px-2 py-0.5 font-mono text-xs text-slate-300">
                      {b.priority} · v{b.version}
                    </span>
                  </div>
                  <h2 className="mt-2 text-lg font-bold text-slate-100">{b.seo_title}</h2>
                  <p className="text-xs font-mono text-sky-400">{b.proposed_url}</p>
                </div>
              </div>

              <div className="grid gap-4 md:grid-cols-2 text-xs">
                <div className="space-y-1.5 rounded-xl border border-slate-800 bg-surface-850 p-4">
                  <p><strong className="text-slate-300">Keyword chính:</strong> <span className="text-sky-300 font-semibold">{b.primary_keyword}</span></p>
                  <p><strong className="text-slate-300">Keyword phụ:</strong> {b.secondary_keywords.join(', ') || '—'}</p>
                  <p><strong className="text-slate-300">H1:</strong> {b.h1}</p>
                  <p><strong className="text-slate-300">Meta Description:</strong> {b.meta_description}</p>
                  <p><strong className="text-slate-300">Search Intent:</strong> <span className="font-mono text-amber-300">[{b.search_intent_status}]</span> {b.search_intent_summary}</p>
                </div>
                <div className="space-y-1.5 rounded-xl border border-slate-800 bg-surface-850 p-4">
                  <p><strong className="text-slate-300">Độc giả mục tiêu:</strong> {b.target_audience}</p>
                  <p><strong className="text-slate-300">Mục tiêu bài viết:</strong> {b.article_goal}</p>
                  <p><strong className="text-slate-300">CTA:</strong> {b.cta}</p>
                  <p><strong className="text-slate-300">Metrics & Nguồn:</strong> <code className="text-slate-200">{JSON.stringify(b.metrics)}</code></p>
                </div>
              </div>

              {/* Writing Strategy (Whole Article Level) */}
              <div className="rounded-xl border border-violet-500/30 bg-violet-950/15 p-4 text-xs space-y-2.5">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h3 className="text-sm font-bold text-violet-200">Writing Strategy (Áp dụng cấp TOÀN BÀI)</h3>
                  <span className="rounded-full bg-violet-500/20 px-2.5 py-0.5 text-[11px] text-violet-200">
                    Chính: {b.writing_strategy.primary_formula} · Bổ trợ: {(b.writing_strategy.supporting_formulas || []).join(', ')}
                  </span>
                </div>
                <p className="text-slate-300"><strong>Lý do chọn:</strong> {b.writing_strategy.rationale}</p>
                <p className="text-[11px] text-amber-200/90">{b.writing_strategy.editor_autonomy_note}</p>
                <div className="grid gap-3 md:grid-cols-2 pt-1">
                  <div>
                    <div className="font-semibold text-slate-200 mb-1">Ý tưởng mở bài (1–2 gợi ý):</div>
                    <ul className="space-y-1 text-slate-300 list-disc list-inside">
                      {(b.writing_strategy.opening_ideas || []).map((idea, idx) => <li key={idx}>{idea}</li>)}
                    </ul>
                  </div>
                  <div>
                    <div className="font-semibold text-slate-200 mb-1">Chiến thuật thu hút (3–6 chiến thuật toàn bài):</div>
                    <ul className="space-y-1 text-slate-300 list-disc list-inside">
                      {(b.writing_strategy.engagement_tactics || []).map((t) => (
                        <li key={t.code}><span className="font-mono text-sky-300">{t.code}</span>: {t.text}</li>
                      ))}
                    </ul>
                  </div>
                </div>
              </div>

              {/* Outline + Checklist */}
              <div className="grid gap-4 md:grid-cols-2 text-xs">
                <div className="rounded-xl border border-slate-800 bg-surface-850 p-4 space-y-2">
                  <h3 className="font-bold text-slate-200">Outline H2 / H3 (Content chủ động triển khai)</h3>
                  <ul className="space-y-2 text-slate-300">
                    {b.outline.map((h, i) => (
                      <li key={i}>
                        <div className="font-semibold text-sky-200">{h.level}: {h.heading}</div>
                        {h.children && (
                          <ul className="ml-4 mt-1 space-y-0.5 text-slate-400 list-disc list-inside">
                            {h.children.map((c, j) => (
                              <li key={j}>{c.level}: {c.heading}</li>
                            ))}
                          </ul>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>

                <div className="rounded-xl border border-slate-800 bg-surface-850 p-4 space-y-2">
                  <h3 className="font-bold text-slate-200">SEO Checklist & Internal Links</h3>
                  <ul className="space-y-1 text-slate-300 list-disc list-inside">
                    {b.seo_checklist.map((item, i) => <li key={i}>{item}</li>)}
                  </ul>
                  {b.internal_links.length > 0 && (
                    <div className="pt-2 border-t border-slate-800">
                      <div className="font-semibold text-slate-200 mb-1">Internal Links đề xuất:</div>
                      {b.internal_links.map((lk, i) => (
                        <p key={i} className="text-slate-400">
                          • <strong>{lk.anchor}</strong> → <code className="text-sky-300">{lk.target_url}</code> ({lk.reason})
                        </p>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
