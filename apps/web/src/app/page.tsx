'use client';

import Link from 'next/link';
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  ClipboardCheck,
  Database,
  Layers,
  RefreshCw,
  SearchCheck,
  ShieldCheck,
  Sparkles,
} from 'lucide-react';
import { useProject } from '@/context/ProjectContext';
import { StatusBadge } from '@/components/StatusBadge';

export default function DashboardPage() {
  const { activeProject, loading, refreshProjects } = useProject();

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="h-24 animate-pulse rounded-2xl bg-surface-900 border border-slate-800" />
        <div className="grid gap-4 md:grid-cols-4">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-28 animate-pulse rounded-2xl bg-surface-900 border border-slate-800" />
          ))}
        </div>
      </div>
    );
  }

  if (!activeProject) {
    return (
      <div className="rounded-2xl border border-slate-800 bg-surface-900 p-10 text-center space-y-4">
        <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-sky-500/15 text-sky-400 ring-1 ring-sky-500/30">
          <Sparkles className="h-7 w-7" />
        </div>
        <h1 className="text-2xl font-bold text-slate-100">Chào mừng tới FinZ SEO Workbench V1.6</h1>
        <p className="mx-auto max-w-xl text-sm text-slate-400">
          Hệ thống hỗ trợ ra quyết định SEO có kiểm chứng (Human-in-the-Loop): nhập Topic Pillar & Keyword vào SQLite,
          AI phân tích & phản biện, đối chiếu bằng chứng xuất từ Semrush UI, phê duyệt Keyword Mapping và tạo SEO Content Brief.
        </p>
        <div className="flex flex-wrap justify-center gap-3 pt-2">
          <Link
            href="/projects"
            className="inline-flex items-center gap-2 rounded-xl bg-sky-500 px-5 py-2.5 text-sm font-semibold text-slate-950 hover:bg-sky-400 transition"
          >
            Tạo dự án SEO đầu tiên
            <ArrowRight className="h-4 w-4" />
          </Link>
          <Link
            href="/settings/ai"
            className="inline-flex items-center gap-2 rounded-xl border border-slate-700 bg-surface-850 px-5 py-2.5 text-sm font-medium text-slate-200 hover:bg-slate-800 transition"
          >
            Cấu hình AI Providers (Gemini / OpenAI / Claude)
          </Link>
        </div>
      </div>
    );
  }

  const wf = activeProject.workflow;
  const counts = wf?.counts;
  const steps = wf?.steps || [];
  const blockers = wf?.blockers || [];
  const gates = wf?.gates || [];
  const nextAction = wf?.next_action;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-4 rounded-2xl border border-slate-800 bg-surface-900/90 p-5">
        <div className="space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-lg bg-sky-500/15 px-2.5 py-1 font-mono text-xs font-bold text-sky-300 ring-1 ring-sky-500/30">
              {activeProject.code}
            </span>
            <h1 className="text-xl font-bold text-slate-100">{activeProject.name}</h1>
            <StatusBadge status={wf?.evidence_summary?.serp_status || 'SERP_NOT_VERIFIED'} />
          </div>
          <p className="text-sm text-slate-400">
            Topic Pillar:{' '}
            <strong className="text-slate-200">
              {activeProject.topic_pillar_code || activeProject.code} — {activeProject.topic_pillar_name || activeProject.main_topic || '(chưa điền)'}
            </strong>{' '}
            · Phiên bản <span className="font-mono text-slate-200">v{activeProject.version}</span> · Chu kỳ nghiên cứu{' '}
            <span className="font-mono text-slate-200">#{activeProject.research_cycle}</span>
          </p>
          <p className="text-xs text-slate-500">
            Lưu SQLite gần nhất:{' '}
            {activeProject.updated_at ? new Date(activeProject.updated_at).toLocaleString('vi-VN') : 'Chưa xác định'}
          </p>
        </div>
        <button
          type="button"
          onClick={() => void refreshProjects(activeProject.id)}
          className="inline-flex items-center gap-1.5 rounded-xl border border-slate-700 bg-surface-850 px-3.5 py-2 text-xs font-medium text-slate-200 hover:bg-slate-800 transition"
        >
          <RefreshCw className="h-3.5 w-3.5" />
          Làm mới trạng thái thật
        </button>
      </div>

      {/* KPI Metrics (real SQLite counts, no fake % progress) */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-2xl border border-slate-800 bg-surface-900 p-4">
          <div className="flex items-center justify-between text-xs text-slate-400">
            <span>Nhóm nhu cầu AI</span>
            <Layers className="h-4 w-4 text-sky-400" />
          </div>
          <div className="mt-2 text-2xl font-bold text-slate-100">{counts?.demand_groups ?? 0}</div>
          <div className="mt-1 text-xs text-slate-500">Đối chiếu nguồn taxonomy SQLite</div>
        </div>

        <div className="rounded-2xl border border-slate-800 bg-surface-900 p-4">
          <div className="flex items-center justify-between text-xs text-slate-400">
            <span>Yêu cầu Semrush</span>
            <SearchCheck className="h-4 w-4 text-amber-400" />
          </div>
          <div className="mt-2 text-2xl font-bold text-slate-100">
            {counts?.research_requests ?? 0}
            <span className="ml-2 text-xs font-normal text-amber-300">
              ({counts?.waiting_requests ?? 0} đang chờ)
            </span>
          </div>
          <div className="mt-1 text-xs text-slate-500">Thao tác thủ công trên Semrush UI</div>
        </div>

        <div className="rounded-2xl border border-slate-800 bg-surface-900 p-4">
          <div className="flex items-center justify-between text-xs text-slate-400">
            <span>Batch Evidence đã nhập</span>
            <Database className="h-4 w-4 text-cyan-400" />
          </div>
          <div className="mt-2 text-2xl font-bold text-slate-100">{counts?.research_batches ?? 0}</div>
          <div className="mt-1 text-xs text-slate-500">
            {wf?.evidence_summary?.metrics_rows_count ?? 0} metrics · {wf?.evidence_summary?.organic_rows_count ?? 0} organic
          </div>
        </div>

        <div className="rounded-2xl border border-slate-800 bg-surface-900 p-4">
          <div className="flex items-center justify-between text-xs text-slate-400">
            <span>Quyết định chờ duyệt</span>
            <ClipboardCheck className="h-4 w-4 text-violet-400" />
          </div>
          <div className="mt-2 text-2xl font-bold text-slate-100">{counts?.pending_approvals ?? 0}</div>
          <div className="mt-1 text-xs text-slate-500">
            {counts?.content_briefs ?? 0} Content Brief đã sinh
          </div>
        </div>
      </div>

      {/* Next Action + Blockers */}
      <div className="grid gap-5 lg:grid-cols-2">
        {/* Next Action */}
        <section className="rounded-2xl border border-sky-500/30 bg-gradient-to-br from-sky-950/35 to-surface-900 p-5 flex flex-col justify-between gap-4">
          <div className="space-y-2">
            <div className="inline-flex items-center gap-1.5 rounded-full bg-sky-500/15 px-2.5 py-0.5 text-xs font-semibold text-sky-300">
              <CheckCircle2 className="h-3.5 w-3.5" />
              Việc cần làm tiếp theo
            </div>
            <h2 className="text-lg font-bold text-slate-100">{nextAction?.title}</h2>
            <p className="text-sm text-slate-300 leading-relaxed">{nextAction?.description}</p>
          </div>
          {nextAction && (
            <div>
              <Link
                href={nextAction.cta_href}
                className="inline-flex items-center gap-2 rounded-xl bg-sky-500 px-4 py-2.5 text-sm font-semibold text-slate-950 hover:bg-sky-400 transition"
              >
                {nextAction.cta_label}
                <ArrowRight className="h-4 w-4" />
              </Link>
            </div>
          )}
        </section>

        {/* Blockers */}
        <section className="rounded-2xl border border-slate-800 bg-surface-900 p-5 space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-base font-bold text-slate-100 flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 text-amber-400" />
              Điểm nghẽn & Cảnh báo bằng chứng ({blockers.length})
            </h2>
          </div>
          {blockers.length === 0 ? (
            <div className="rounded-xl border border-emerald-500/25 bg-emerald-950/20 p-4 text-sm text-emerald-200">
              Không có điểm nghẽn nghiêm trọng nào ở thời điểm hiện tại.
            </div>
          ) : (
            <div className="space-y-2.5 max-h-72 overflow-y-auto pr-1">
              {blockers.map((b) => (
                <div
                  key={b.code}
                  className="rounded-xl border border-amber-500/25 bg-surface-850 p-3.5 text-xs space-y-1.5"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-semibold text-amber-200">{b.title}</span>
                    <span className="font-mono text-[11px] text-slate-400">{b.code}</span>
                  </div>
                  <p className="text-slate-300">
                    <strong className="text-slate-200">Nguyên nhân:</strong> {b.cause}
                  </p>
                  <p className="text-slate-400">
                    <strong className="text-slate-300">Hậu quả:</strong> {b.impact}
                  </p>
                  <p className="text-sky-200/90">
                    <strong>Giải pháp:</strong> {b.solution}
                  </p>
                  <div className="pt-1">
                    <Link
                      href={b.cta_href}
                      className="inline-flex items-center gap-1 text-sky-400 hover:text-sky-300 font-semibold"
                    >
                      {b.cta_label} <ArrowRight className="h-3 w-3" />
                    </Link>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      </div>

      {/* 7-Step Stepper */}
      <section className="rounded-2xl border border-slate-800 bg-surface-900 p-5 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-base font-bold text-slate-100">Tiến trình 7 bước thực tế (Không có bước nhập SERP thủ công)</h2>
          <span className="text-xs text-slate-400">Cập nhật từ trạng thái SQLite thực</span>
        </div>
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          {steps.map((s) => (
            <Link
              key={s.step_number}
              href={s.href}
              className="group rounded-xl border border-slate-800 bg-surface-850/90 p-4 hover:border-sky-500/45 transition flex flex-col justify-between gap-3"
            >
              <div className="space-y-2">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs font-bold text-slate-200 group-hover:text-sky-300 transition">
                    {s.title}
                  </span>
                </div>
                <StatusBadge status={s.status} />
                <p className="text-xs text-slate-400 leading-relaxed">
                  {s.summary || 'Chưa có dữ liệu thao tác ở bước này.'}
                </p>
              </div>
              <span className="inline-flex items-center gap-1 text-xs font-semibold text-sky-400">
                Mở bước <ArrowRight className="h-3.5 w-3.5" />
              </span>
            </Link>
          ))}
        </div>
      </section>

      {/* Quality Gates Matrix F0..F7, E0..E2 */}
      <section className="rounded-2xl border border-slate-800 bg-surface-900 p-5 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-bold text-slate-100 flex items-center gap-2">
            <ShieldCheck className="h-4 w-4 text-emerald-400" />
            Quality Gates kiểm chứng bằng chứng (F0–F7 & E0–E2)
          </h2>
          <span className="text-xs text-slate-400">
            Brief chính thức: {wf?.evidence_summary?.can_generate_official_brief ? 'ĐỦ ĐIỀU KIỆN' : 'CHƯA ĐỦ GATE'}
          </span>
        </div>
        <div className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
          {gates.map((g) => (
            <div
              key={g.gate_code}
              className="flex items-center justify-between gap-2 rounded-xl border border-slate-800 bg-surface-850 px-3.5 py-2.5"
            >
              <div className="min-w-0">
                <span className="font-mono text-xs font-bold text-sky-300 mr-2">{g.gate_code}</span>
                <span className="text-xs text-slate-300 truncate">{g.gate_name}</span>
              </div>
              <StatusBadge status={g.status} className="shrink-0" />
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
