'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { Activity, Cpu, History, RefreshCw } from 'lucide-react';
import { useProject } from '@/context/ProjectContext';
import { apiRequest } from '@/lib/api';
import { StatusBadge } from '@/components/StatusBadge';
import { ResponsiveTable } from '@/components/ResponsiveTable';

interface LogsPayload {
  events: Array<{
    id: string;
    level: string;
    event_type: string;
    message: string;
    details: Record<string, unknown>;
    created_at: string | null;
  }>;
  ai_runs: Array<{
    id: string;
    role: string;
    provider: string;
    requested_model: string;
    actual_model: string;
    prompt_version: string;
    research_cycle: number;
    latency_ms: number;
    fallback_events: Array<{ from_model: string; to_model: string; reason: string }>;
    source_refs: string[];
    status: string;
    error_code: string | null;
    created_at: string | null;
  }>;
  snapshots: Array<{
    id: string;
    version: number;
    reason: string;
    created_at: string | null;
  }>;
}

export default function LogsPage() {
  const { activeProject } = useProject();
  const [data, setData] = useState<LogsPayload | null>(null);

  const loadLogs = useCallback(async () => {
    if (!activeProject) return;
    try {
      const res = await apiRequest<LogsPayload>(`/api/v1/projects/${activeProject.id}/logs`);
      setData(res);
    } catch {
      // ignore
    }
  }, [activeProject]);

  useEffect(() => {
    void loadLogs();
  }, [loadLogs]);

  if (!activeProject) {
    return (
      <div className="rounded-2xl border border-slate-800 bg-surface-900 p-8 text-center text-sm text-slate-300">
        Chưa chọn dự án. <Link href="/projects" className="text-sky-400 underline">Chọn dự án trước</Link>.
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Nhật ký hệ thống, AI Runs & Lịch sử phiên bản</h1>
          <p className="mt-1 text-sm text-slate-400">
            Theo dõi trung thực mọi lượt chạy AI (bao gồm sự kiện Gemini tự động hạ model sau 3 lỗi), import batch, phê duyệt và snapshot SQLite.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void loadLogs()}
          className="inline-flex items-center gap-1.5 rounded-xl border border-slate-700 bg-surface-900 px-3.5 py-2 text-xs font-medium text-slate-200 hover:bg-slate-800"
        >
          <RefreshCw className="h-3.5 w-3.5" /> Làm mới
        </button>
      </div>

      {/* AI Runs History */}
      <section className="space-y-3">
        <h2 className="text-base font-bold text-slate-100 flex items-center gap-2">
          <Cpu className="h-4 w-4 text-violet-400" />
          Lịch sử gọi AI ({data?.ai_runs.length ?? 0})
        </h2>
        {!data || data.ai_runs.length === 0 ? (
          <div className="rounded-xl border border-dashed border-slate-700 p-6 text-xs text-slate-400">Chưa có lần chạy AI nào.</div>
        ) : (
          <ResponsiveTable caption="Lịch sử gọi nhà cung cấp AI và tự động hạ model">
            <thead>
              <tr>
                <th scope="col">Vai trò</th>
                <th scope="col">Provider & Model thực tế</th>
                <th scope="col">Độ trễ</th>
                <th scope="col">Trạng thái</th>
                <th scope="col">Sự kiện hạ model / Nguồn</th>
                <th scope="col">Thời điểm</th>
              </tr>
            </thead>
            <tbody>
              {data.ai_runs.map((r) => (
                <tr key={r.id}>
                  <th scope="row" className="font-mono text-xs">{r.role}</th>
                  <td data-label="Provider & Model" className="text-xs font-mono">
                    {r.provider.toUpperCase()} / <span className="text-sky-300">{r.actual_model}</span>
                  </td>
                  <td data-label="Độ trễ" className="font-mono text-xs">{r.latency_ms} ms</td>
                  <td data-label="Trạng thái">
                    <StatusBadge status={r.status === 'COMPLETED' ? 'PASSED' : 'ERROR'} />
                    {r.error_code && <span className="ml-1.5 font-mono text-[11px] text-rose-300">{r.error_code}</span>}
                  </td>
                  <td data-label="Ghi chú" className="text-xs text-slate-400">
                    {r.fallback_events.length > 0
                      ? r.fallback_events.map((e) => e.reason).join(' ')
                      : r.source_refs.length > 0
                      ? `refs: ${r.source_refs.join(', ')}`
                      : '—'}
                  </td>
                  <td data-label="Thời điểm" className="text-xs text-slate-400">
                    {r.created_at ? new Date(r.created_at).toLocaleString('vi-VN') : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </ResponsiveTable>
        )}
      </section>

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Events Timeline */}
        <section className="lg:col-span-2 rounded-2xl border border-slate-800 bg-surface-900 p-5 space-y-3">
          <h2 className="text-base font-bold text-slate-100 flex items-center gap-2">
            <Activity className="h-4 w-4 text-sky-400" />
            Nhật ký tác vụ thật ({data?.events.length ?? 0})
          </h2>
          <div className="space-y-2 max-h-96 overflow-y-auto pr-1">
            {(data?.events || []).map((e) => (
              <div key={e.id} className="rounded-xl border border-slate-800 bg-surface-850 p-3 text-xs space-y-1">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono font-semibold text-sky-300">{e.event_type}</span>
                  <span className="text-[11px] text-slate-500">
                    {e.created_at ? new Date(e.created_at).toLocaleString('vi-VN') : ''}
                  </span>
                </div>
                <p className="text-slate-200">{e.message}</p>
              </div>
            ))}
          </div>
        </section>

        {/* Version Snapshots */}
        <section className="rounded-2xl border border-slate-800 bg-surface-900 p-5 space-y-3">
          <h2 className="text-base font-bold text-slate-100 flex items-center gap-2">
            <History className="h-4 w-4 text-emerald-400" />
            Lịch sử phiên bản ({data?.snapshots.length ?? 0})
          </h2>
          <div className="space-y-2 max-h-96 overflow-y-auto pr-1">
            {(data?.snapshots || []).map((s) => (
              <div key={s.id} className="rounded-xl border border-slate-800 bg-surface-850 p-3 text-xs">
                <div className="flex items-center justify-between">
                  <span className="font-mono font-bold text-emerald-300">v{s.version}</span>
                  <span className="text-[11px] text-slate-500">
                    {s.created_at ? new Date(s.created_at).toLocaleString('vi-VN') : ''}
                  </span>
                </div>
                <p className="mt-1 text-slate-300">{s.reason}</p>
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}
