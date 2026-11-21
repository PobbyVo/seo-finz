'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { Check, ClipboardCheck, HelpCircle, X } from 'lucide-react';
import { useProject } from '@/context/ProjectContext';
import { ApiError, apiRequest } from '@/lib/api';
import type { ApprovalItem, StandardizedError } from '@/lib/types';
import { ErrorBanner } from '@/components/ErrorBanner';
import { StatusBadge } from '@/components/StatusBadge';

export default function ApprovalsPage() {
  const { activeProject, refreshProjects } = useProject();
  const [approvals, setApprovals] = useState<ApprovalItem[]>([]);
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<StandardizedError | null>(null);
  const currentPidRef = useRef<string | null>(null);
  currentPidRef.current = activeProject?.id ?? null;

  const loadApprovals = useCallback(async () => {
    if (!activeProject) return;
    const reqPid = activeProject.id;
    try {
      const data = await apiRequest<{ approvals: ApprovalItem[] }>(
        `/api/v1/projects/${reqPid}/approvals`
      );
      if (currentPidRef.current === reqPid) setApprovals(data.approvals);
    } catch (err) {
      if (currentPidRef.current === reqPid && err instanceof ApiError && err.structured) setError(err.structured);
    }
  }, [activeProject]);

  useEffect(() => {
    setApprovals([]);
    setError(null);
    void loadApprovals();
  }, [loadApprovals]);

  if (!activeProject) {
    return (
      <div className="rounded-2xl border border-slate-800 bg-surface-900 p-8 text-center text-sm text-slate-300">
        Chưa chọn dự án. <Link href="/projects" className="text-sky-400 underline">Chọn dự án trước</Link>.
      </div>
    );
  }

  const handleDecide = async (id: string, decision: 'APPROVED' | 'REJECTED' | 'NEED_MORE_EVIDENCE') => {
    setBusyId(id);
    setError(null);
    try {
      await apiRequest(`/api/v1/projects/${activeProject.id}/approvals/${id}`, {
        method: 'POST',
        body: JSON.stringify({
          decision,
          decision_note: notes[id] || '',
          decided_by: 'Chuyên viên SEO',
        }),
      });
      await loadApprovals();
      await refreshProjects(activeProject.id);
    } catch (err) {
      if (err instanceof ApiError && err.structured) setError(err.structured);
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-100">Chờ phê duyệt quyết định SEO (Human-in-the-Loop)</h1>
        <p className="mt-1 text-sm text-slate-400">
          AI không bao giờ tự phê duyệt thay đổi keyword gốc, mở chủ đề mới, gộp/tách bài hoặc chốt Keyword Mapping.
          Phê duyệt để nghiên cứu tiếp (<code>RESEARCH_ONLY</code>) tách biệt hoàn toàn với phê duyệt xuất Brief chính thức (<code>BRIEF_ELIGIBILITY</code>).
        </p>
      </div>

      <ErrorBanner error={error} onDismiss={() => setError(null)} />

      {approvals.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-slate-700 bg-surface-900/50 p-10 text-center text-sm text-slate-400">
          Không có quyết định nào đang chờ phê duyệt cho dự án <strong className="text-slate-200">{activeProject.code}</strong>.
        </div>
      ) : (
        <div className="space-y-4">
          {approvals.map((a) => (
            <article key={a.id} className="rounded-2xl border border-slate-800 bg-surface-900 p-5 space-y-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="space-y-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <ClipboardCheck className="h-4 w-4 text-amber-400" />
                    <span className="font-mono text-xs text-slate-400">{a.approval_type}</span>
                    <span className="rounded bg-slate-800 px-2 py-0.5 font-mono text-[11px] text-sky-300">
                      scope: {a.scope}
                    </span>
                    <StatusBadge status={a.status} />
                  </div>
                  <h2 className="text-base font-bold text-slate-100">{a.title}</h2>
                </div>
                <span className="font-mono text-xs text-slate-500">
                  v{a.version}
                  {a.target_revision ? ` · map rev #${a.target_revision}` : ''}
                  {a.target_fingerprint ? ` · fp:${a.target_fingerprint.slice(0, 8)}` : ''}
                </span>
              </div>

              <div className="grid gap-3 md:grid-cols-2 text-xs">
                <div className="rounded-xl border border-slate-800 bg-surface-850 p-3">
                  <div className="text-slate-400 mb-1 font-semibold">Giá trị gốc</div>
                  <div className="text-slate-200">{a.original_value || '—'}</div>
                </div>
                <div className="rounded-xl border border-sky-500/25 bg-sky-950/15 p-3">
                  <div className="text-sky-300 mb-1 font-semibold">Giá trị đề xuất</div>
                  <div className="text-sky-100 font-medium">{a.proposed_value}</div>
                </div>
              </div>

              <div className="text-xs space-y-1.5 text-slate-300">
                <p><strong className="text-slate-200">Lý do:</strong> {a.rationale}</p>
                <p><strong className="text-slate-200">Mức ảnh hưởng:</strong> {a.impact}</p>
                {a.evidence.length > 0 && (
                  <div>
                    <strong className="text-slate-200">Bằng chứng đính kèm:</strong>
                    <ul className="mt-1 list-disc list-inside text-slate-400 space-y-0.5">
                      {a.evidence.map((e, i) => <li key={i}>{e}</li>)}
                    </ul>
                  </div>
                )}
              </div>

              {a.status === 'PENDING' ? (
                <div className="space-y-3 pt-3 border-t border-slate-800">
                  <input
                    value={notes[a.id] || ''}
                    onChange={(e) => setNotes((prev) => ({ ...prev, [a.id]: e.target.value }))}
                    placeholder="Ghi chú quyết định phê duyệt (tùy chọn)…"
                    className="finz-input text-xs"
                  />
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      disabled={busyId === a.id}
                      onClick={() => void handleDecide(a.id, 'APPROVED')}
                      className="inline-flex items-center gap-1.5 rounded-xl bg-emerald-500 px-4 py-2 text-xs font-semibold text-slate-950 hover:bg-emerald-400 disabled:opacity-50"
                    >
                      <Check className="h-4 w-4" /> Phê duyệt
                    </button>
                    <button
                      type="button"
                      disabled={busyId === a.id}
                      onClick={() => void handleDecide(a.id, 'NEED_MORE_EVIDENCE')}
                      className="inline-flex items-center gap-1.5 rounded-xl border border-amber-500/40 bg-amber-500/15 px-4 py-2 text-xs font-semibold text-amber-200 hover:bg-amber-500/25 disabled:opacity-50"
                    >
                      <HelpCircle className="h-4 w-4" /> Yêu cầu bổ sung bằng chứng
                    </button>
                    <button
                      type="button"
                      disabled={busyId === a.id}
                      onClick={() => void handleDecide(a.id, 'REJECTED')}
                      className="inline-flex items-center gap-1.5 rounded-xl border border-rose-500/40 bg-rose-950/30 px-4 py-2 text-xs font-semibold text-rose-200 hover:bg-rose-950/60 disabled:opacity-50"
                    >
                      <X className="h-4 w-4" /> Từ chối
                    </button>
                  </div>
                </div>
              ) : (
                <div className="pt-2 border-t border-slate-800 text-xs text-slate-400">
                  Quyết định bởi <strong className="text-slate-200">{a.decided_by || 'SEO'}</strong> vào{' '}
                  {a.decided_at ? new Date(a.decided_at).toLocaleString('vi-VN') : '—'}
                  {a.decision_note ? ` · Ghi chú: "${a.decision_note}"` : ''}
                </div>
              )}
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
