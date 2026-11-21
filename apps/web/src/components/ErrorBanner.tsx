'use client';

import Link from 'next/link';
import { AlertTriangle, ArrowRight } from 'lucide-react';
import type { StandardizedError } from '@/lib/types';

export function ErrorBanner({
  error,
  onDismiss,
}: {
  error: StandardizedError | null;
  onDismiss?: () => void;
}) {
  if (!error) return null;
  return (
    <div
      role="alert"
      className="rounded-xl border border-rose-500/35 bg-rose-950/35 p-4 text-sm text-rose-100 shadow-lg"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-rose-400" aria-hidden="true" />
          <div className="space-y-1.5">
            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded bg-rose-500/20 px-2 py-0.5 font-mono text-xs font-semibold text-rose-200">
                {error.code}
              </span>
              <span className="font-semibold text-rose-100">Cần xử lý trước khi tiếp tục</span>
            </div>
            <p className="text-rose-100/95">
              <strong className="text-rose-200">Nguyên nhân:</strong> {error.reason}
            </p>
            <p className="text-rose-200/85">
              <strong className="text-rose-200">Ảnh hưởng:</strong> {error.impact}
            </p>
            <p className="text-slate-200">
              <strong className="text-sky-300">Cách giải quyết:</strong> {error.solution}
            </p>
            <div className="flex flex-wrap items-center gap-3 pt-1">
              {error.cta_href && error.cta_href !== '#' && (
                <Link
                  href={error.cta_href}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-rose-500/25 px-3 py-1.5 text-xs font-semibold text-rose-100 hover:bg-rose-500/35 border border-rose-400/40 transition"
                >
                  {error.cta_label || 'Đi tới nơi xử lý'}
                  <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
                </Link>
              )}
              <span className="text-xs text-slate-400">Hành động tiếp theo: {error.next_action}</span>
            </div>
          </div>
        </div>
        {onDismiss && (
          <button
            type="button"
            onClick={onDismiss}
            className="rounded-md px-2 py-1 text-xs text-rose-200/80 hover:bg-rose-500/20 hover:text-white"
            aria-label="Đóng thông báo lỗi"
          >
            ✕
          </button>
        )}
      </div>
    </div>
  );
}
