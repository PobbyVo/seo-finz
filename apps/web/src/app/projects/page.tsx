'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Download, FolderPlus, HardDrive, Trash2 } from 'lucide-react';
import { useProject } from '@/context/ProjectContext';
import { ApiError, apiRequest } from '@/lib/api';
import type { ProjectItem, StandardizedError } from '@/lib/types';
import { ErrorBanner } from '@/components/ErrorBanner';
import { StatusBadge } from '@/components/StatusBadge';

export default function ProjectsPage() {
  const { projects, activeProjectId, setActiveProjectId, refreshProjects, showCompletionPopup } = useProject();
  const router = useRouter();
  const [code, setCode] = useState('');
  const [name, setName] = useState('');
  const [pillarName, setPillarName] = useState('');
  const [primaryKeyword, setPrimaryKeyword] = useState('');
  const [businessGoal, setBusinessGoal] = useState('');
  const [targetAudience, setTargetAudience] = useState('');
  const [market, setMarket] = useState('VN');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<StandardizedError | null>(null);
  const [backupNotice, setBackupNotice] = useState<string | null>(null);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const res = await apiRequest<{
        saved: boolean;
        navigation_eligible: boolean;
        next_step_href: string;
        project: ProjectItem;
      }>('/api/v1/projects', {
        method: 'POST',
        body: JSON.stringify({
          code: code.trim().toUpperCase(),
          name: name.trim(),
          pillar_name: pillarName.trim(),
          topic_pillar_code: code.trim().toUpperCase(),
          topic_pillar_name: name.trim(),
          primary_keyword: primaryKeyword.trim(),
          business_goal: businessGoal.trim(),
          target_audience: targetAudience.trim(),
          market,
          language: 'vi',
        }),
      });
      await refreshProjects(res.project.id);
      setCode('');
      setName('');
      setPillarName('');
      setPrimaryKeyword('');
      setBusinessGoal('');
      setTargetAudience('');
      showCompletionPopup({
        title: `Đã tạo dự án ${res.project.code}`,
        message: `Dự án "${res.project.name}" đã được ghi nhận vào SQLite (v1).`,
        nextStepLabel: res.navigation_eligible ? 'Bước 02 — Bản đồ nhu cầu AI' : 'Bước 01 — Thiết lập chủ đề',
        nextStepHref: res.next_step_href,
        navigationEligible: true,
      });
    } catch (err) {
      if (err instanceof ApiError && err.structured) setError(err.structured);
      else setError({ code: 'DB_SAVE_FAILED', reason: String(err), impact: 'Chưa tạo được dự án.', solution: 'Kiểm tra backend.', next_action: 'Thử lại.' });
    } finally {
      setSubmitting(false);
    }
  };

  const handleBackup = async (project: ProjectItem) => {
    setBackupNotice(null);
    try {
      const res = await apiRequest<{
        sqlite_backup_filename: string | null;
        contains_api_keys: boolean;
        project_snapshot: ProjectItem;
      }>(`/api/v1/projects/${project.id}/backup`, { method: 'POST' });
      const blob = new Blob([JSON.stringify(res.project_snapshot, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${project.code}_safe_snapshot_v${project.version}.json`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      setBackupNotice(
        `Đã sao lưu SQLite (${res.sqlite_backup_filename || 'local'}) và tải xuống snapshot JSON an toàn (contains_api_keys: false).`
      );
    } catch (err) {
      if (err instanceof ApiError && err.structured) setError(err.structured);
    }
  };

  const handleDelete = async (project: ProjectItem) => {
    if (!window.confirm(`Xóa dự án [${project.code}] ${project.name}? Hệ thống sẽ tự sao lưu SQLite trước khi xóa.`)) return;
    try {
      await apiRequest(`/api/v1/projects/${project.id}`, { method: 'DELETE' });
      await refreshProjects();
    } catch (err) {
      if (err instanceof ApiError && err.structured) setError(err.structured);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-100">Quản lý nhiều dự án SEO</h1>
        <p className="mt-1 text-sm text-slate-400">
          Mỗi dự án (P01, P08, P25, Z42…) vận hành độc lập hoàn toàn trong SQLite, không hardcode bất kỳ chủ đề mẫu nào.
        </p>
      </div>

      <ErrorBanner error={error} onDismiss={() => setError(null)} />
      {backupNotice && (
        <div className="rounded-xl border border-emerald-500/35 bg-emerald-950/30 p-3.5 text-sm text-emerald-200">
          {backupNotice}
        </div>
      )}

      {/* Create Project Form */}
      <form onSubmit={handleCreate} className="rounded-2xl border border-slate-800 bg-surface-900 p-5 space-y-4">
        <div className="flex items-center gap-2 text-base font-bold text-slate-100">
          <FolderPlus className="h-5 w-5 text-sky-400" />
          Tạo dự án mới
        </div>
        <div className="grid gap-4 md:grid-cols-3">
          <div>
            <label htmlFor="prj-code" className="block text-xs font-semibold text-slate-300 mb-1">
              Mã dự án / Topic Pillar *
            </label>
            <span id="prj-code-hint" className="block text-[11px] text-slate-500 mb-1">Ví dụ: P01, P08, P25, Z42</span>
            <input
              id="prj-code"
              required
              aria-describedby="prj-code-hint"
              data-error="prj-code-err"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              placeholder="P08"
              className="finz-input"
            />
            <div id="prj-code-err" className="field-error-msg">Vui lòng nhập mã dự án (ví dụ: P08).</div>
          </div>

          <div className="md:col-span-2">
            <label htmlFor="prj-name" className="block text-xs font-semibold text-slate-300 mb-1">
              Tên dự án / Topic Pillar *
            </label>
            <span id="prj-name-hint" className="block text-[11px] text-slate-500 mb-1">Mô tả rõ cụm chủ đề cần nghiên cứu</span>
            <input
              id="prj-name"
              required
              aria-describedby="prj-name-hint"
              data-error="prj-name-err"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Ví dụ: Bảo hiểm xã hội doanh nghiệp"
              className="finz-input"
            />
            <div id="prj-name-err" className="field-error-msg">Vui lòng nhập tên dự án.</div>
          </div>

          <div>
            <label htmlFor="prj-pillar" className="block text-xs font-semibold text-slate-300 mb-1">
              Pillar lớn
            </label>
            <input
              id="prj-pillar"
              value={pillarName}
              onChange={(e) => setPillarName(e.target.value)}
              placeholder="Ví dụ: Nhân sự & Thuế"
              className="finz-input"
            />
          </div>

          <div>
            <label htmlFor="prj-pk" className="block text-xs font-semibold text-slate-300 mb-1">
              Keyword chính gốc (có thể nhập sau ở Bước 01)
            </label>
            <input
              id="prj-pk"
              value={primaryKeyword}
              onChange={(e) => setPrimaryKeyword(e.target.value)}
              placeholder="Ví dụ: mức đóng bhxh bắt buộc"
              className="finz-input"
            />
          </div>

          <div>
            <label htmlFor="prj-market" className="block text-xs font-semibold text-slate-300 mb-1">
              Thị trường
            </label>
            <select id="prj-market" value={market} onChange={(e) => setMarket(e.target.value)} className="finz-select">
              <option value="VN">VN (Việt Nam)</option>
              <option value="US">US (United States)</option>
              <option value="SG">SG (Singapore)</option>
              <option value="GLOBAL">GLOBAL</option>
            </select>
          </div>

          <div className="md:col-span-2">
            <label htmlFor="prj-goal" className="block text-xs font-semibold text-slate-300 mb-1">
              Mục tiêu kinh doanh (hệ thống không tự suy đoán)
            </label>
            <input
              id="prj-goal"
              value={businessGoal}
              onChange={(e) => setBusinessGoal(e.target.value)}
              placeholder="Ví dụ: Tạo lead B2B đăng ký tư vấn kế toán doanh nghiệp"
              className="finz-input"
            />
          </div>

          <div>
            <label htmlFor="prj-aud" className="block text-xs font-semibold text-slate-300 mb-1">
              Đối tượng độc giả
            </label>
            <input
              id="prj-aud"
              value={targetAudience}
              onChange={(e) => setTargetAudience(e.target.value)}
              placeholder="Ví dụ: Kế toán trưởng & HR SME"
              className="finz-input"
            />
          </div>
        </div>

        <div className="flex justify-end">
          <button
            type="submit"
            disabled={submitting}
            className="rounded-xl bg-sky-500 px-5 py-2.5 text-sm font-semibold text-slate-950 hover:bg-sky-400 disabled:opacity-50 transition"
          >
            {submitting ? 'Đang lưu SQLite…' : 'Tạo dự án & lưu SQLite'}
          </button>
        </div>
      </form>

      {/* Project List */}
      <section className="space-y-3">
        <h2 className="text-base font-bold text-slate-100">Danh sách dự án trong SQLite ({projects.length})</h2>
        {projects.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-slate-700 bg-surface-900/50 p-8 text-center text-sm text-slate-400">
            Chưa có dự án nào. Hãy tạo dự án ở biểu mẫu phía trên.
          </div>
        ) : (
          <div className="grid gap-4 md:grid-cols-2">
            {projects.map((p) => {
              const isCurrent = p.id === activeProjectId;
              return (
                <div
                  key={p.id}
                  className={`rounded-2xl border p-4 transition ${
                    isCurrent
                      ? 'border-sky-500/50 bg-sky-950/20'
                      : 'border-slate-800 bg-surface-900 hover:border-slate-700'
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="rounded bg-slate-800 px-2 py-0.5 font-mono text-xs font-bold text-sky-300">
                          {p.code}
                        </span>
                        <h3 className="font-bold text-slate-100">{p.name}</h3>
                      </div>
                      <p className="mt-1 text-xs text-slate-400">
                        Keyword gốc: <strong className="text-slate-200">{p.primary_keyword_original || '(chưa có)'}</strong> · v{p.version}
                      </p>
                    </div>
                    <StatusBadge status={p.workflow?.evidence_summary?.serp_status || 'SERP_NOT_VERIFIED'} />
                  </div>

                  <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-slate-400">
                    <span>Nhu cầu: {p.workflow?.counts?.demand_groups ?? 0}</span>
                    <span>·</span>
                    <span>Batch Semrush: {p.workflow?.counts?.research_batches ?? 0}</span>
                    <span>·</span>
                    <span>Chờ duyệt: {p.workflow?.counts?.pending_approvals ?? 0}</span>
                  </div>

                  <div className="mt-4 flex flex-wrap items-center gap-2">
                    <button
                      type="button"
                      onClick={() => {
                        setActiveProjectId(p.id);
                        router.push('/');
                      }}
                      className="rounded-lg bg-sky-500/20 border border-sky-500/35 px-3 py-1.5 text-xs font-semibold text-sky-200 hover:bg-sky-500/30"
                    >
                      {isCurrent ? 'Đang chọn · Mở Tổng quan' : 'Chọn dự án này'}
                    </button>
                    <button
                      type="button"
                      onClick={() => void handleBackup(p)}
                      className="inline-flex items-center gap-1 rounded-lg border border-slate-700 bg-surface-850 px-3 py-1.5 text-xs text-slate-300 hover:bg-slate-800"
                    >
                      <Download className="h-3.5 w-3.5" />
                      Backup an toàn
                    </button>
                    <button
                      type="button"
                      onClick={() => void handleDelete(p)}
                      className="inline-flex items-center gap-1 rounded-lg border border-rose-500/30 bg-rose-950/25 px-3 py-1.5 text-xs text-rose-300 hover:bg-rose-950/50 ml-auto"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                      Xóa
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </section>

      <div className="rounded-xl border border-slate-800 bg-surface-900/70 p-4 text-xs text-slate-400 flex items-center gap-2.5">
        <HardDrive className="h-4 w-4 text-slate-500 shrink-0" />
        Dữ liệu dự án và file tải lên được lưu cục bộ trong thư mục <code className="text-slate-200">data/</code>; bản sao lưu JSON không bao giờ chứa API key.
      </div>
    </div>
  );
}
