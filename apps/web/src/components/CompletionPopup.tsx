'use client';

import { useEffect, useId, useRef, useState } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { ArrowRight, X } from 'lucide-react';
import { useProject } from '@/context/ProjectContext';

const AUTO_NAV_MS = 1800;

/**
 * Business Completion Popup (Section 09, T27, T28):
 * - Uses native <dialog> opened via showModal() (no role="dialog" / aria-modal / body overflow lock).
 * - Only triggered after backend confirms SQLite commit.
 * - Auto-navigates after 1.8s when navigationEligible === true.
 * - Cancelled cleanly on "Ở lại bước này", Escape, route change, project switch, or unmount.
 */
export function CompletionPopup() {
  const { completionPopup, closeCompletionPopup, activeProjectId } = useProject();
  const router = useRouter();
  const pathname = usePathname();
  const titleId = useId();
  const dialogRef = useRef<HTMLDialogElement | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const prevPathnameRef = useRef(pathname);
  const prevProjectIdRef = useRef<string | null>(activeProjectId);
  const [countdownActive, setCountdownActive] = useState(false);

  const clearTimer = () => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    setCountdownActive(false);
  };

  // Cancel timer on actual route change or switching away from an existing project
  useEffect(() => {
    const routeChanged = prevPathnameRef.current !== pathname;
    const switchedExistingProject =
      prevProjectIdRef.current !== null && prevProjectIdRef.current !== activeProjectId;
    prevPathnameRef.current = pathname;
    prevProjectIdRef.current = activeProjectId;

    if (routeChanged || switchedExistingProject) {
      clearTimer();
      closeCompletionPopup();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathname, activeProjectId]);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;

    if (completionPopup) {
      if (!dialog.open) {
        dialog.showModal();
      }
      clearTimer();
      if (completionPopup.navigationEligible && completionPopup.nextStepHref) {
        const targetHref = completionPopup.nextStepHref;
        setCountdownActive(true);
        timerRef.current = setTimeout(() => {
          clearTimer();
          if (dialog.open) dialog.close('auto');
          closeCompletionPopup();
          router.push(targetHref);
        }, AUTO_NAV_MS);
      }
    } else if (dialog.open) {
      clearTimer();
      dialog.close();
    }

    return () => {
      clearTimer();
    };
  }, [completionPopup, closeCompletionPopup, router]);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    const onClose = () => {
      clearTimer();
      // Reset returnValue per dialog guide so stale return values never leak
      dialog.returnValue = '';
      closeCompletionPopup();
    };
    const onCancel = () => {
      clearTimer();
    };
    dialog.addEventListener('close', onClose);
    dialog.addEventListener('cancel', onCancel);
    return () => {
      dialog.removeEventListener('close', onClose);
      dialog.removeEventListener('cancel', onCancel);
    };
  }, [closeCompletionPopup]);

  const handleStay = () => {
    clearTimer();
    dialogRef.current?.close('stay');
    closeCompletionPopup();
  };

  const handleGoNow = () => {
    clearTimer();
    const href = completionPopup?.nextStepHref;
    dialogRef.current?.close('go');
    closeCompletionPopup();
    if (href) router.push(href);
  };

  return (
    <dialog ref={dialogRef} aria-labelledby={titleId} className="finz-dialog">
      {completionPopup && (
        <div className="p-6">
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-emerald-500/15 ring-1 ring-emerald-400/40">
                <svg className="h-7 w-7 text-emerald-400" viewBox="0 0 52 52" fill="none" aria-hidden="true">
                  <circle
                    className="finz-check-circle"
                    cx="26"
                    cy="26"
                    r="24"
                    stroke="currentColor"
                    strokeWidth="3"
                  />
                  <path
                    className="finz-check-mark"
                    d="M15 27L22.5 34.5L38 19"
                    stroke="currentColor"
                    strokeWidth="3.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </div>
              <div>
                <h2 id={titleId} className="text-base font-semibold text-slate-100">
                  {completionPopup.title}
                </h2>
                <p className="text-xs text-emerald-300/90">Đã xác nhận lưu SQLite thành công</p>
              </div>
            </div>
            <button
              type="button"
              onClick={handleStay}
              aria-label="Đóng hộp thoại"
              className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-800 hover:text-slate-100"
            >
              <X className="h-4 w-4" aria-hidden="true" />
            </button>
          </div>

          <p className="mt-4 text-sm leading-relaxed text-slate-300">{completionPopup.message}</p>

          {countdownActive && completionPopup.nextStepHref && (
            <p className="mt-3 rounded-lg border border-sky-500/25 bg-sky-500/10 px-3 py-2 text-xs text-sky-200">
              Tự động chuyển sang <strong>{completionPopup.nextStepLabel || 'bước tiếp theo'}</strong> sau ~1,8 giây…
              Nhấn <kbd className="rounded bg-slate-800 px-1.5 py-0.5 font-mono text-[11px]">Esc</kbd> hoặc{' '}
              <strong>Ở lại bước này</strong> để hủy.
            </p>
          )}

          <div className="mt-5 flex flex-wrap items-center justify-end gap-2.5">
            <button
              type="button"
              onClick={handleStay}
              className="rounded-lg border border-slate-700 bg-slate-800/80 px-4 py-2 text-sm font-medium text-slate-200 hover:bg-slate-700 transition"
            >
              Ở lại bước này
            </button>
            {completionPopup.nextStepHref && (
              <button
                type="button"
                autoFocus
                onClick={handleGoNow}
                className="inline-flex items-center gap-1.5 rounded-lg bg-sky-500 px-4 py-2 text-sm font-semibold text-slate-950 hover:bg-sky-400 transition"
              >
                Đi tiếp ngay
                <ArrowRight className="h-4 w-4" aria-hidden="true" />
              </button>
            )}
          </div>
        </div>
      )}
    </dialog>
  );
}
