'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { AlertTriangle, BookOpen, CheckCircle2, Download, FileSpreadsheet, FileText, Printer, Sparkles } from 'lucide-react';
import { useProject } from '@/context/ProjectContext';
import { ApiError, apiRequest, downloadExportFile } from '@/lib/api';
import type { ContentBriefItem, ExportHistoryItem, MappingEligibility, StandardizedError } from '@/lib/types';
import { ErrorBanner } from '@/components/ErrorBanner';
import { StatusBadge } from '@/components/StatusBadge';

interface MappingEligibilityRow {
  id: string;
  primary_keyword: string;
  page_type: string;
  revision: number;
  eligibility: MappingEligibility;
}

interface BriefsPayload {
  briefs: ContentBriefItem[];
  mappings_eligibility?: MappingEligibilityRow[];
  writing_formulas_catalog: Array<{ id: string; name: string; description: string }>;
  engagement_tactics_catalog: Array<{ number: number; code: string; text: string }>;
}

export default function Step07BriefPage() {
  const { activeProject, refreshProjects } = useProject();
  const [data, setData] = useState<BriefsPayload | null>(null);
  const [exportsList, setExportsList] = useState<ExportHistoryItem[]>([]);
  const [selectedMappingIds, setSelectedMappingIds] = useState<Set<string>>(new Set());
  const [generating, setGenerating] = useState(false);
  const [exporting, setExporting] = useState<string | null>(null);
  const [showCatalog, setShowCatalog] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<StandardizedError | null>(null);
  const currentPidRef = useRef<string | null>(null);
  currentPidRef.current = activeProject?.id ?? null;

  const loadBriefs = useCallback(async () => {
    if (!activeProject) return;
    const reqPid = activeProject.id;
    try {
      const [res, expRes] = await Promise.all([
        apiRequest<BriefsPayload>(`/api/v1/projects/${reqPid}/briefs`),
        apiRequest<{ exports: ExportHistoryItem[] }>(`/api/v1/projects/${reqPid}/exports`),
      ]);
      if (currentPidRef.current !== reqPid) return;
      setData(res);
      setExportsList(expRes.exports || []);
      const eligRows = res.mappings_eligibility || [];
      setSelectedMappingIds((prev) => {
        const validIds = new Set(eligRows.map((m) => m.id));
        const kept = [...prev].filter((id) => validIds.has(id));
        if (kept.length > 0) return new Set(kept);
        // Default select eligible mappings if any exist, otherwise all
        const onlyElig = eligRows.filter((m) => m.eligibility.eligible_official).map((m) => m.id);
        return new Set(onlyElig.length > 0 ? onlyElig : eligRows.map((m) => m.id));
      });
    } catch (err) {
      if (currentPidRef.current === reqPid && err instanceof ApiError && err.structured) setError(err.structured);
    }
  }, [activeProject]);

  useEffect(() => {
    setData(null);
    setSelectedMappingIds(new Set());
    setNotice(null);
    setError(null);
    void loadBriefs();
  }, [loadBriefs]);

  if (!activeProject) {
    return (
      <div className="rounded-2xl border border-slate-800 bg-surface-900 p-8 text-center text-sm text-slate-300">
        Chưa chọn dự án. <Link href="/projects" className="text-sky-400 underline">Chọn dự án trước</Link>.
      </div>
    );
  }

  const eligRows = data?.mappings_eligibility || [];
  const chosenRows = eligRows.filter((m) => selectedMappingIds.has(m.id));
  // Strict UI truthfulness: OFFICIAL button enabled ONLY when selected mappings are ALL genuinely eligible_official!
  const canGenerateOfficialForSelection =
    chosenRows.length > 0 && chosenRows.every((m) => m.eligibility.eligible_official);

  const toggleMapping = (id: string) => {
    setSelectedMappingIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleGenerate = async (allowDraft: boolean) => {
    const reqPid = activeProject.id;
    setGenerating(true);
    setError(null);
    setNotice(null);
    const targetIds = chosenRows.length > 0 ? chosenRows.map((m) => m.id) : null;
    try {
      const res = await apiRequest<{ official_count: number; draft_count: number }>(
        `/api/v1/projects/${reqPid}/briefs/generate`,
        { method: 'POST', body: JSON.stringify({ allow_draft: allowDraft, mapping_ids: targetIds }) }
      );
      if (currentPidRef.current !== reqPid) return;
      setNotice(
        `Đã tạo xong Content Brief: ${res.official_count} bản CHÍNH THỨC, ${res.draft_count} bản DỰ THẢO.`
      );
      await loadBriefs();
      await refreshProjects(reqPid);
    } catch (err) {
      if (currentPidRef.current === reqPid && err instanceof ApiError && err.structured) setError(err.structured);
    } finally {
      if (currentPidRef.current === reqPid) setGenerating(false);
    }
  };

  const handleExport = async (fmt: 'xlsx' | 'csv' | 'json' | 'html') => {
    setExporting(fmt);
    setError(null);
    try {
      const fname = await downloadExportFile(activeProject.id, fmt);
      setNotice(`Đã xuất thành công tệp ${fname} (không gọi Google Sheets API, tên file sinh theo dự án ${activeProject.code}).`);
      await loadBriefs();
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
            Chỉ phát hành <strong>CHÍNH THỨC</strong> cho từng Mapping đạt đủ Quality Gates & phê duyệt phiên bản hiện hành. Mapping thiếu SERP/KD/Approval luôn giữ nhãn <strong>DỰ THẢO</strong>.
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            disabled={generating || !canGenerateOfficialForSelection}
            onClick={() => void handleGenerate(false)}
            className="inline-flex items-center gap-2 rounded-xl bg-emerald-500 px-4 py-2.5 text-xs font-semibold text-slate-950 hover:bg-emerald-400 disabled:opacity-40 transition"
            title={
              canGenerateOfficialForSelection
                ? 'Tất cả Mapping đang chọn đều đạt đủ Quality Gates'
                : 'Chỉ bật khi toàn bộ Mapping đang chọn đều đạt đủ điều kiện Brief CHÍNH THỨC'
            }
          >
            <Sparkles className="h-4 w-4" />
            Tạo Brief CHÍNH THỨC ({chosenRows.filter((m) => m.eligibility.eligible_official).length}/{chosenRows.length})
          </button>
          <button
            type="button"
            disabled={generating || chosenRows.length === 0}
            onClick={() => void handleGenerate(true)}
            className="inline-flex items-center gap-2 rounded-xl bg-sky-500/20 border border-sky-400/40 px-4 py-2.5 text-xs font-semibold text-sky-200 hover:bg-sky-500/30 disabled:opacity-40 transition"
          >
            <FileText className="h-4 w-4" />
            {generating ? 'Đang tạo Brief…' : 'Tạo Brief DỰ THẢO / Hỗn hợp'}
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

      {/* Per-Mapping Selection & Eligibility Gate Panel */}
      {eligRows.length > 0 && (
        <section className="rounded-2xl border border-slate-800 bg-surface-900 p-4 space-y-3">
          <div className="text-xs font-bold uppercase tracking-wider text-slate-300">
            Chọn Mapping để tạo Content Brief (Kiểm tra điều kiện theo từng từ khóa)
          </div>
          <div className="grid gap-2.5 md:grid-cols-2">
            {eligRows.map((m) => {
              const ok = m.eligibility.eligible_official;
              return (
                <label
                  key={m.id}
                  className={`flex items-start gap-2.5 rounded-xl border p-3 text-xs cursor-pointer transition ${
                    selectedMappingIds.has(m.id)
                      ? 'border-sky-500/50 bg-sky-950/20'
                      : 'border-slate-800 bg-surface-850'
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={selectedMappingIds.has(m.id)}
                    onChange={() => toggleMapping(m.id)}
                    className="mt-0.5 h-4 w-4 rounded"
                  />
                  <div className="space-y-1 min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <strong className="text-slate-100">{m.primary_keyword}</strong>
                      <span className="font-mono text-[11px] text-slate-400">rev #{m.revision}</span>
                      <StatusBadge status={m.eligibility.serp_tier} />
                      {m.eligibility.approval_state === 'STALE_SUPERSEDED' && <StatusBadge status="STALE_SUPERSEDED" />}
                    </div>
                    {ok ? (
                      <div className="inline-flex items-center gap-1 text-emerald-300">
                        <CheckCircle2 className="h-3.5 w-3.5" /> Đủ điều kiện phát hành CHÍNH THỨC
                      </div>
                    ) : (
                      <div className="text-amber-200/90">
                        Chỉ xuất DỰ THẢO — Chặn bởi: {m.eligibility.blockers.map((b) => b.code).join(', ')}
                      </div>
                    )}
                  </div>
                </label>
              );
            })}
          </div>
        </section>
      )}

      {/* Export Bar */}
      <section className="rounded-2xl border border-slate-800 bg-surface-900 p-4 flex flex-wrap items-center justify-between gap-3">
        <div className="text-xs text-slate-300">
          <strong className="text-slate-100">Xuất tệp cục bộ:</strong> XLSX chứa đúng 3 sheet (<code className="text-sky-300">Keyword Overview</code>,{' '}
          <code className="text-sky-300">Keyword Mapping</code>, <code className="text-sky-300">SEO Content Brief</code>) đặt tên theo dự án{' '}
          <strong className="text-white">{activeProject.code}</strong> kèm nhãn xác minh trung thực.
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

      {/* Historical Exports Provenance & Freshness List */}
      {exportsList.length > 0 && (
        <section className="rounded-2xl border border-slate-800 bg-surface-900 p-4 space-y-3" data-testid="export-history-section">
          <div className="text-xs font-bold uppercase tracking-wider text-slate-300">
            Lịch sử các bản xuất ({exportsList.length}) — Phân biệt bản hiện hành vs bản lịch sử đã thay thế
          </div>
          <div className="space-y-2">
            {exportsList.map((ex) => (
              <div
                key={ex.id}
                className={`flex flex-wrap items-center justify-between gap-2 rounded-xl border p-3 text-xs ${
                  ex.is_superseded
                    ? 'border-rose-500/35 bg-rose-950/20'
                    : 'border-slate-800 bg-surface-850'
                }`}
              >
                <div className="space-y-1 min-w-0">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className="font-mono text-slate-100 break-all">{ex.filename}</span>
                    <StatusBadge status={ex.freshness_status} />
                    <StatusBadge status={ex.recorded_brief_mode} />
                  </div>
                  {ex.is_superseded && ex.superseded_reason && (
                    <p className="text-[11px] text-rose-200/90">{ex.superseded_reason}</p>
                  )}
                </div>
                <div className="shrink-0">
                  {ex.is_superseded ? (
                    <a
                      href={`${(process.env.NEXT_PUBLIC_API_BASE || '').replace(/\/+$/, '')}${ex.historical_download_url}`}
                      className="inline-flex items-center gap-1 rounded-lg border border-rose-500/40 bg-rose-950/40 px-2.5 py-1.5 text-[11px] font-semibold text-rose-200 hover:bg-rose-900/50"
                    >
                      <Download className="h-3 w-3" /> Tải bản lịch sử (đã hết hiệu lực)
                    </a>
                  ) : (
                    <a
                      href={`${(process.env.NEXT_PUBLIC_API_BASE || '').replace(/\/+$/, '')}${ex.download_url}`}
                      className="inline-flex items-center gap-1 rounded-lg border border-slate-700 bg-surface-900 px-2.5 py-1.5 text-[11px] font-medium text-slate-200 hover:bg-slate-800"
                    >
                      <Download className="h-3 w-3" /> Tải lại bản hiện hành
                    </a>
                  )}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

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
              {b.is_stale && (
                <div className="rounded-xl border border-rose-500/40 bg-rose-950/30 p-3 text-xs text-rose-200 flex items-center gap-2">
                  <AlertTriangle className="h-4 w-4 text-rose-400 shrink-0" />
                  <span>
                    <strong>Brief đã cũ (STALE):</strong>{' '}
                    {b.stale_reasons && b.stale_reasons.length > 0
                      ? b.stale_reasons.join(' ')
                      : 'Mapping hoặc bằng chứng gốc đã thay đổi sau khi tạo bản này. Hãy phê duyệt phiên bản mới và tạo lại Brief.'}
                  </span>
                </div>
              )}

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
                      {b.priority} · brief v{b.version} {b.mapping_revision ? `· map rev #${b.mapping_revision}` : ''}
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
                  <p><strong className="text-slate-300">Metrics & Nguồn:</strong> <code className="text-slate-200 break-all">{JSON.stringify(b.metrics)}</code></p>
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
