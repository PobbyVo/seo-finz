'use client';

import { useEffect } from 'react';

/**
 * Syncs native `:user-invalid` visual validation with `aria-invalid` and `aria-describedby`
 * plus one polite page-level live announcer (validate-input-after-interaction guide).
 */
export function FormAriaSync() {
  useEffect(() => {
    const announcer = document.createElement('div');
    announcer.setAttribute('aria-live', 'polite');
    announcer.className = 'visually-hidden';
    document.body.append(announcer);

    let timer: ReturnType<typeof setTimeout> | null = null;
    const flagged = new WeakSet<Element>();
    const announced = new WeakSet<Element>();

    const linkError = (el: HTMLElement, shown: boolean) => {
      const errorId = el.dataset.error;
      if (!errorId) return;
      const ids = (el.getAttribute('aria-describedby') || '')
        .split(/\s+/)
        .filter((id) => id && id !== errorId);
      if (shown) ids.push(errorId);
      if (ids.length) el.setAttribute('aria-describedby', ids.join(' '));
      else el.removeAttribute('aria-describedby');
    };

    const syncAria = (target: EventTarget | null, announce = false) => {
      if (!(target instanceof HTMLElement)) return;
      if (!target.matches('input, select, textarea')) return;

      let invalid = false;
      try {
        invalid = target.matches(':user-invalid');
      } catch {
        invalid = target.classList.contains('user-invalid-fallback');
      }

      if (invalid) {
        if (announce && !announced.has(target) && target.dataset.error) {
          const errNode = document.getElementById(target.dataset.error);
          if (errNode) {
            if (timer) clearTimeout(timer);
            announcer.textContent = '';
            timer = setTimeout(() => {
              announcer.textContent = errNode.textContent?.trim() || '';
            }, 400);
            announced.add(target);
          }
        }
        target.setAttribute('aria-invalid', 'true');
        linkError(target, true);
        flagged.add(target);
      } else if (flagged.has(target) || target.getAttribute('aria-invalid') !== 'true') {
        target.setAttribute('aria-invalid', 'false');
        linkError(target, false);
        flagged.delete(target);
        announced.delete(target);
      }
    };

    const onBlur = (e: Event) => syncAria(e.target, true);
    const onInput = (e: Event) => {
      if (e.target instanceof HTMLElement && e.target.hasAttribute('aria-invalid')) {
        syncAria(e.target, false);
      }
    };
    const onChange = (e: Event) => syncAria(e.target, true);
    const onInvalid = (e: Event) => {
      if (e.target instanceof Element) announced.add(e.target);
      syncAria(e.target, false);
    };

    document.addEventListener('blur', onBlur, true);
    document.addEventListener('input', onInput);
    document.addEventListener('change', onChange, true);
    document.addEventListener('invalid', onInvalid, true);

    return () => {
      if (timer) clearTimeout(timer);
      document.removeEventListener('blur', onBlur, true);
      document.removeEventListener('input', onInput);
      document.removeEventListener('change', onChange, true);
      document.removeEventListener('invalid', onInvalid, true);
      announcer.remove();
    };
  }, []);

  return null;
}
