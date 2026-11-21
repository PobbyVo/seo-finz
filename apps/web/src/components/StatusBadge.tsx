'use client';

const STATUS_META: Record<string, { label: string; cls: string }> = {
  NOT_STARTED: { label: 'Chưa bắt đầu', cls: 'bg-slate-800/80 text-slate-400 border-slate-700' },
  READY: { label: 'Sẵn sàng', cls: 'bg-sky-500/15 text-sky-300 border-sky-500/35' },
  RUNNING: { label: 'Đang chạy', cls: 'bg-violet-500/15 text-violet-300 border-violet-500/35' },
  WAITING_USER: { label: 'Chờ người dùng', cls: 'bg-amber-500/15 text-amber-300 border-amber-500/35' },
  REVIEW_REQUIRED: { label: 'Cần xem xét', cls: 'bg-orange-500/15 text-orange-300 border-orange-500/35' },
  HOLD: { label: 'Tạm giữ (HOLD)', cls: 'bg-amber-500/20 text-amber-200 border-amber-400/40' },
  ERROR: { label: 'Lỗi', cls: 'bg-rose-500/15 text-rose-300 border-rose-500/35' },
  FAILED: { label: 'Chưa đạt', cls: 'bg-rose-500/15 text-rose-300 border-rose-500/35' },
  WARNING: { label: 'Cảnh báo', cls: 'bg-amber-500/15 text-amber-300 border-amber-500/35' },
  PASSED: { label: 'Đạt kiểm tra', cls: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/35' },
  PROCESS_COMPLETED: { label: 'Hoàn thành thao tác', cls: 'bg-cyan-500/15 text-cyan-300 border-cyan-500/35' },
  QUALITY_APPROVED: { label: 'Đạt kiểm duyệt', cls: 'bg-emerald-500/20 text-emerald-200 border-emerald-400/45' },
  CONNECTED: { label: 'Đã kết nối', cls: 'bg-emerald-500/20 text-emerald-200 border-emerald-400/40' },
  READY_TO_TEST: { label: 'Sẵn sàng kiểm tra', cls: 'bg-sky-500/15 text-sky-300 border-sky-500/35' },
  TESTING: { label: 'Đang kiểm tra…', cls: 'bg-violet-500/15 text-violet-300 border-violet-500/35' },
  NOT_CONFIGURED: { label: 'Chưa cấu hình', cls: 'bg-slate-800 text-slate-400 border-slate-700' },
  RESEARCH_CANDIDATE: { label: 'Ứng viên nghiên cứu', cls: 'bg-sky-500/15 text-sky-300 border-sky-500/35' },
  RESEARCH_REQUIRED: { label: 'Cần nghiên cứu thêm', cls: 'bg-amber-500/15 text-amber-300 border-amber-500/35' },
  METRICS_AVAILABLE: { label: 'Đã có Metrics', cls: 'bg-cyan-500/15 text-cyan-300 border-cyan-500/35' },
  SERP_NOT_VERIFIED: { label: 'SERP_NOT_VERIFIED', cls: 'bg-amber-500/20 text-amber-200 border-amber-400/40' },
  PARTIAL_SERP_EVIDENCE: { label: 'SERP một phần (chưa đủ)', cls: 'bg-orange-500/20 text-orange-200 border-orange-400/40' },
  SERP_VERIFIED: { label: 'SERP đã xác minh', cls: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/35' },
  TOP_10_VERIFIED: { label: 'Top 10 SERP đã kiểm chứng', cls: 'bg-emerald-500/25 text-emerald-200 border-emerald-400/50' },
  STALE_SUPERSEDED: { label: 'Cần duyệt lại', cls: 'bg-amber-500/25 text-amber-200 border-amber-400/50' },
  SUPERSEDED: { label: 'Hết hiệu lực (đã thay thế)', cls: 'bg-slate-800 text-slate-400 border-slate-700' },
  STALE_NEEDS_REGENERATION: { label: 'Brief cũ · Cần tạo lại', cls: 'bg-rose-500/20 text-rose-200 border-rose-400/40' },
  LOW_VOLUME_BUT_RELEVANT: { label: 'Vol thấp · Sát B2B', cls: 'bg-indigo-500/20 text-indigo-200 border-indigo-400/40' },
  OUT_OF_SCOPE: { label: 'Ngoài phạm vi', cls: 'bg-slate-800 text-slate-400 border-slate-700' },
  UNCERTAIN: { label: 'UNCERTAIN (kiểm tra nguồn)', cls: 'bg-rose-500/20 text-rose-200 border-rose-400/40' },
  PENDING_APPROVAL: { label: 'Chờ phê duyệt', cls: 'bg-amber-500/15 text-amber-200 border-amber-400/40' },
  PENDING: { label: 'Đang chờ duyệt', cls: 'bg-amber-500/15 text-amber-200 border-amber-400/40' },
  APPROVED: { label: 'Đã phê duyệt', cls: 'bg-emerald-500/20 text-emerald-200 border-emerald-400/40' },
  REJECTED: { label: 'Từ chối', cls: 'bg-rose-500/15 text-rose-300 border-rose-500/35' },
  NEED_MORE_EVIDENCE: { label: 'Cần thêm bằng chứng', cls: 'bg-orange-500/15 text-orange-300 border-orange-500/35' },
  READY_FOR_BRIEF: { label: 'Sẵn sàng Brief', cls: 'bg-emerald-500/20 text-emerald-200 border-emerald-400/50' },
  OFFICIAL: { label: 'CHÍNH THỨC', cls: 'bg-emerald-500/20 text-emerald-200 border-emerald-400/50' },
  DRAFT: { label: 'DỰ THẢO', cls: 'bg-amber-500/20 text-amber-200 border-amber-400/40' },
  IMPORTED: { label: 'Đã nhập SQLite', cls: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/35' },
  MAPPING_REQUIRED: { label: 'Cần ghép cột', cls: 'bg-sky-500/15 text-sky-300 border-sky-500/35' },
};

export function StatusBadge({ status, className = '' }: { status: string; className?: string }) {
  const key = (status || 'NOT_STARTED').toUpperCase();
  const meta = STATUS_META[key] || {
    label: status,
    cls: 'bg-slate-800 text-slate-300 border-slate-700',
  };
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium tracking-tight ${meta.cls} ${className}`}
    >
      {meta.label}
    </span>
  );
}
