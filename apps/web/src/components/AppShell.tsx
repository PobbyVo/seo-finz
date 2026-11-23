'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  Activity,
  CheckCircle2,
  ClipboardCheck,
  Cpu,
  FileSpreadsheet,
  FileText,
  FolderKanban,
  LayoutDashboard,
  Map as MapIcon,
  Menu,
  Network,
  SearchCheck,
  Settings,
  ShieldCheck,
  Sparkles,
  UploadCloud,
  X,
} from 'lucide-react';
import { useProject } from '@/context/ProjectContext';
import { CompletionPopup } from './CompletionPopup';

const STEP_NAV = [
  { num: 1, href: '/steps/01-topic', label: '01. Thiết lập chủ đề', icon: FileSpreadsheet },
  { num: 2, href: '/steps/02-demand-map', label: '02. Bản đồ nhu cầu AI', icon: Sparkles },
  { num: 3, href: '/steps/03-semrush', label: '03. Yêu cầu Semrush', icon: SearchCheck },
  { num: 4, href: '/steps/04-upload', label: '04. Tải file & ghép cột', icon: UploadCloud },
  { num: 5, href: '/steps/05-evidence', label: '05. Kiểm tra & AI Critic', icon: ShieldCheck },
  { num: 6, href: '/steps/06-mapping', label: '06. Kế hoạch & Mapping', icon: MapIcon },
  { num: 7, href: '/steps/07-brief', label: '07. Content Brief & Xuất', icon: FileText },
];

function stepDotColor(status?: string): string {
  switch (status) {
    case 'QUALITY_APPROVED':
      return 'bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.65)]';
    case 'PROCESS_COMPLETED':
      return 'bg-cyan-400';
    case 'WAITING_USER':
    case 'REVIEW_REQUIRED':
    case 'HOLD':
      return 'bg-amber-400';
    case 'ERROR':
      return 'bg-rose-400';
    case 'READY':
      return 'bg-sky-400';
    default:
      return 'bg-slate-600';
  }
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { projects, activeProject, activeProjectId, setActiveProjectId, activeAI } = useProject();
  const [mobileOpen, setMobileOpen] = useState(false);

  const stepsByNum = new Map(
    (activeProject?.workflow?.steps || []).map((s) => [s.step_number, s.status])
  );
  const pendingApprovals = activeProject?.workflow?.counts?.pending_approvals || 0;

  const sidebarContent = (
    <div className="flex h-full flex-col bg-surface-900 border-r border-slate-800/80">
      {/* Brand */}
      <div className="flex items-center justify-between px-4 py-4 border-b border-slate-800/80">
        <Link href="/" className="flex items-center gap-2.5" onClick={() => setMobileOpen(false)}>
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-sky-500 to-violet-500 text-slate-950 font-black text-sm shadow-lg shadow-sky-500/20">
            FZ
          </div>
          <div>
            <div className="text-sm font-bold tracking-tight text-slate-100">FinZ SEO Workbench</div>
            <div className="text-[11px] text-slate-400">V2.0 · Evidence-First · Dark</div>
          </div>
        </Link>
        <button
          type="button"
          onClick={() => setMobileOpen(false)}
          className="lg:hidden rounded-lg p-1.5 text-slate-400 hover:bg-slate-800 hover:text-white"
          aria-label="Đóng thanh điều hướng"
        >
          <X className="h-5 w-5" />
        </button>
      </div>

      {/* Active Project Switcher */}
      <div className="px-3 py-3 border-b border-slate-800/80">
        <label htmlFor="project-switcher" className="block text-[11px] font-semibold uppercase tracking-wider text-slate-400 mb-1.5">
          Dự án đang hoạt động
        </label>
        {projects.length > 0 ? (
          <select
            id="project-switcher"
            value={activeProjectId || ''}
            onChange={(e) => setActiveProjectId(e.target.value)}
            className="finz-select text-xs font-medium py-2"
          >
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                [{p.code}] {p.name} (v{p.version})
              </option>
            ))}
          </select>
        ) : (
          <Link
            href="/projects"
            onClick={() => setMobileOpen(false)}
            className="block rounded-lg border border-dashed border-sky-500/40 bg-sky-500/10 px-3 py-2 text-center text-xs font-medium text-sky-300 hover:bg-sky-500/20"
          >
            + Tạo dự án SEO đầu tiên
          </Link>
        )}
        {activeProject && (
          <div className="mt-2 flex items-center justify-between text-[11px] text-slate-400">
            <span className="truncate">
              Topic: <strong className="text-slate-200">{activeProject.topic_pillar_code || activeProject.code}</strong>
            </span>
            <span className="font-mono text-slate-500">v{activeProject.version} · C{activeProject.research_cycle}</span>
          </div>
        )}
      </div>

      {/* Navigation */}
      <nav aria-label="Điều hướng chính" className="flex-1 overflow-y-auto px-3 py-3 space-y-5">
        <div className="space-y-1">
          <div className="px-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
            Điều hành
          </div>
          <Link
            href="/"
            onClick={() => setMobileOpen(false)}
            aria-current={pathname === '/' ? 'page' : undefined}
            className={`flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm font-medium transition ${
              pathname === '/'
                ? 'bg-sky-500/15 text-sky-300 ring-1 ring-sky-500/30'
                : 'text-slate-300 hover:bg-slate-800/70 hover:text-white'
            }`}
          >
            <LayoutDashboard className="h-4 w-4 shrink-0" aria-hidden="true" />
            Tổng quan & Trạng thái
          </Link>
          <Link
            href="/projects"
            onClick={() => setMobileOpen(false)}
            aria-current={pathname === '/projects' ? 'page' : undefined}
            className={`flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm font-medium transition ${
              pathname === '/projects'
                ? 'bg-sky-500/15 text-sky-300 ring-1 ring-sky-500/30'
                : 'text-slate-300 hover:bg-slate-800/70 hover:text-white'
            }`}
          >
            <FolderKanban className="h-4 w-4 shrink-0" aria-hidden="true" />
            Quản lý dự án
          </Link>
        </div>

        {/* 7-Step Flow */}
        <div className="space-y-1">
          <div className="px-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
            Luồng 7 bước nghiên cứu
          </div>
          {STEP_NAV.map((item) => {
            const Icon = item.icon;
            const active = pathname === item.href;
            const st = stepsByNum.get(item.num);
            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => setMobileOpen(false)}
                aria-current={active ? 'page' : undefined}
                className={`flex items-center justify-between gap-2 rounded-lg px-2.5 py-2 text-[13px] font-medium transition ${
                  active
                    ? 'bg-sky-500/15 text-sky-200 ring-1 ring-sky-500/35'
                    : 'text-slate-300 hover:bg-slate-800/70 hover:text-white'
                }`}
              >
                <span className="flex items-center gap-2.5 truncate">
                  <Icon className="h-4 w-4 shrink-0 text-slate-400" aria-hidden="true" />
                  <span className="truncate">{item.label}</span>
                </span>
                <span
                  title={st || 'NOT_STARTED'}
                  className={`h-2 w-2 shrink-0 rounded-full ${stepDotColor(st)}`}
                />
              </Link>
            );
          })}
        </div>

        {/* Governance */}
        <div className="space-y-1">
          <div className="px-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
            Kiểm soát & Nhật ký
          </div>
          <Link
            href="/approvals"
            onClick={() => setMobileOpen(false)}
            aria-current={pathname === '/approvals' ? 'page' : undefined}
            className={`flex items-center justify-between gap-2 rounded-lg px-2.5 py-2 text-sm font-medium transition ${
              pathname === '/approvals'
                ? 'bg-sky-500/15 text-sky-300 ring-1 ring-sky-500/30'
                : 'text-slate-300 hover:bg-slate-800/70 hover:text-white'
            }`}
          >
            <span className="flex items-center gap-2.5">
              <ClipboardCheck className="h-4 w-4 shrink-0" aria-hidden="true" />
              Chờ phê duyệt
            </span>
            {pendingApprovals > 0 && (
              <span className="rounded-full bg-amber-500/20 px-2 py-0.5 text-xs font-bold text-amber-300 ring-1 ring-amber-400/40">
                {pendingApprovals}
              </span>
            )}
          </Link>
          <Link
            href="/logs"
            onClick={() => setMobileOpen(false)}
            aria-current={pathname === '/logs' ? 'page' : undefined}
            className={`flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm font-medium transition ${
              pathname === '/logs'
                ? 'bg-sky-500/15 text-sky-300 ring-1 ring-sky-500/30'
                : 'text-slate-300 hover:bg-slate-800/70 hover:text-white'
            }`}
          >
            <Activity className="h-4 w-4 shrink-0" aria-hidden="true" />
            Nhật ký hệ thống
          </Link>
        </div>
      </nav>

      {/* Settings -> AI Providers at bottom of sidebar (Section 06 requirement!) */}
      <div className="p-3 border-t border-slate-800/80 bg-surface-950/50">
        <Link
          href="/settings/ai"
          onClick={() => setMobileOpen(false)}
          aria-current={pathname === '/settings/ai' ? 'page' : undefined}
          className={`flex items-center justify-between gap-2 rounded-xl px-3 py-2.5 text-sm font-medium transition ${
            pathname === '/settings/ai'
              ? 'bg-violet-500/20 text-violet-200 ring-1 ring-violet-400/40'
              : 'bg-surface-850 text-slate-200 hover:bg-slate-800 ring-1 ring-slate-700/70'
          }`}
        >
          <span className="flex items-center gap-2.5 min-w-0">
            <Settings className="h-4 w-4 shrink-0 text-violet-400" aria-hidden="true" />
            <span className="truncate">
              <span className="block text-xs font-semibold">Settings → AI Providers</span>
              <span className="block truncate text-[11px] text-slate-400">
                {activeAI
                  ? `${activeAI.provider.toUpperCase()} · ${activeAI.active_model_id || activeAI.model_id}`
                  : 'Chưa cấu hình AI'}
              </span>
            </span>
          </span>
          {activeAI?.connection_status === 'CONNECTED' ? (
            <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-400" aria-hidden="true" />
          ) : (
            <Cpu className="h-4 w-4 shrink-0 text-slate-500" aria-hidden="true" />
          )}
        </Link>
      </div>
    </div>
  );

  return (
    <div className="flex min-h-screen bg-surface-950 text-slate-100">
      {/* Desktop Sidebar */}
      <aside className="hidden lg:block lg:w-72 lg:shrink-0 lg:sticky lg:top-0 lg:h-screen">
        {sidebarContent}
      </aside>

      {/* Mobile Drawer */}
      {mobileOpen && (
        <div className="fixed inset-0 z-50 flex lg:hidden">
          <div className="fixed inset-0 bg-black/70 backdrop-blur-sm" onClick={() => setMobileOpen(false)} />
          <div className="relative z-10 w-72 max-w-[85vw] h-full">{sidebarContent}</div>
        </div>
      )}

      {/* Main Content */}
      <div className="flex flex-1 flex-col min-w-0">
        {/* Top bar (mobile menu + quick status strip) */}
        <header className="sticky top-0 z-30 flex items-center justify-between gap-3 border-b border-slate-800/80 bg-surface-950/85 backdrop-blur-md px-4 py-3 lg:px-8">
          <div className="flex items-center gap-3 min-w-0">
            <button
              type="button"
              onClick={() => setMobileOpen(true)}
              className="lg:hidden rounded-lg border border-slate-700 bg-surface-900 p-2 text-slate-200 hover:bg-slate-800"
              aria-label="Mở menu điều hướng"
            >
              <Menu className="h-4 w-4" />
            </button>
            <div className="min-w-0">
              <div className="flex items-center gap-2 text-sm font-semibold text-slate-100 truncate">
                <Network className="h-4 w-4 text-sky-400 shrink-0 hidden sm:block" aria-hidden="true" />
                {activeProject ? (
                  <span className="truncate">
                    <span className="font-mono text-sky-400">[{activeProject.code}]</span> {activeProject.name}
                  </span>
                ) : (
                  <span>Chưa chọn dự án</span>
                )}
              </div>
              {activeProject && (
                <p className="text-xs text-slate-400 truncate">
                  Keyword gốc: <span className="text-slate-200">{activeProject.primary_keyword_original || '(chưa nhập)'}</span>
                  {' · '}Thị trường: <span className="text-slate-200">{activeProject.market}</span>
                </p>
              )}
            </div>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            <Link
              href="/settings/ai"
              className="hidden sm:inline-flex items-center gap-1.5 rounded-full border border-slate-700/80 bg-surface-900 px-3 py-1 text-xs text-slate-300 hover:border-violet-400/50 hover:text-white transition"
            >
              <span
                className={`h-2 w-2 rounded-full ${
                  activeAI?.connection_status === 'CONNECTED'
                    ? 'bg-emerald-400'
                    : activeAI
                    ? 'bg-sky-400'
                    : 'bg-rose-400'
                }`}
              />
              {activeAI ? `${activeAI.provider.toUpperCase()}: ${activeAI.active_model_id || activeAI.model_id}` : 'Cấu hình AI'}
            </Link>
          </div>
        </header>

        <main className="flex-1 px-4 py-6 lg:px-8 max-w-7xl w-full mx-auto">
          {children}
        </main>
      </div>

      <CompletionPopup />
    </div>
  );
}
