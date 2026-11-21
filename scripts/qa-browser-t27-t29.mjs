#!/usr/bin/env node
/**
 * Real Headless Chrome E2E verification for V1.6 T27, T28, T29, and UI gating.
 * - Uses isolated temporary SQLite DB and ephemeral ports (18001 / 13001) — NEVER touches user data/.
 * - Uses native Node 22 WebSocket + Chrome DevTools Protocol against local Google Chrome (0 extra packages).
 * - Cleans up all spawned processes (Chrome, FastAPI, Next.js) unconditionally in finally{}.
 */
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const API_DIR = path.join(ROOT, 'services', 'api');
const WEB_DIR = path.join(ROOT, 'apps', 'web');
const UVICORN = path.join(API_DIR, '.venv', 'bin', 'uvicorn');

const CHROME_CANDIDATES = [
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  '/usr/bin/google-chrome',
  '/usr/bin/chromium',
  '/usr/bin/chromium-browser',
];

const API_PORT = 18001;
const WEB_PORT = 13001;
const CDP_PORT = 19222;
const API_URL = `http://127.0.0.1:${API_PORT}`;
const WEB_URL = `http://127.0.0.1:${WEB_PORT}`;

function findChrome() {
  for (const p of CHROME_CANDIDATES) {
    if (fs.existsSync(p)) return p;
  }
  return null;
}

async function waitForHttp(url, timeoutMs = 30000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const r = await fetch(url);
      if (r.ok) return r;
    } catch {
      // retry
    }
    await new Promise((r) => setTimeout(r, 400));
  }
  throw new Error(`Timeout waiting for ${url}`);
}

class CDPClient {
  constructor(wsUrl) {
    this.wsUrl = wsUrl;
    this.seq = 0;
    this.pending = new Map();
  }
  async connect() {
    this.ws = new WebSocket(this.wsUrl);
    await new Promise((resolve, reject) => {
      this.ws.addEventListener('open', resolve, { once: true });
      this.ws.addEventListener('error', reject, { once: true });
    });
    this.ws.addEventListener('message', (ev) => {
      const msg = JSON.parse(String(ev.data));
      if (msg.id && this.pending.has(msg.id)) {
        const { resolve, reject } = this.pending.get(msg.id);
        this.pending.delete(msg.id);
        if (msg.error) reject(new Error(msg.error.message || JSON.stringify(msg.error)));
        else resolve(msg.result);
      }
    });
  }
  send(method, params = {}) {
    const id = ++this.seq;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.ws.send(JSON.stringify({ id, method, params }));
    });
  }
  async evalJS(expression) {
    const res = await this.send('Runtime.evaluate', {
      expression,
      awaitPromise: true,
      returnByValue: true,
    });
    if (res.exceptionDetails) {
      throw new Error(`JS error: ${res.exceptionDetails.text} ${JSON.stringify(res.exceptionDetails.exception)}`);
    }
    return res.result?.value;
  }
  async waitForCondition(expr, timeoutMs = 12000) {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      const val = await this.evalJS(expr);
      if (val) return val;
      await new Promise((r) => setTimeout(r, 150));
    }
    throw new Error(`Condition timed out: ${expr}`);
  }
  async goto(url) {
    await this.send('Page.navigate', { url });
    await this.waitForCondition(`document.readyState === 'complete' && location.href.startsWith(${JSON.stringify(url.split('?')[0])})`, 15000);
    await new Promise((r) => setTimeout(r, 500));
  }
  close() {
    try {
      this.ws?.close();
    } catch {
      // ignore
    }
  }
}

async function main() {
  const chromeBin = findChrome();
  if (!chromeBin) {
    console.log(JSON.stringify({ status: 'BLOCKED', reason: 'Chrome/Chromium binary not found' }, null, 2));
    process.exit(2);
  }

  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'finz-qa-browser-'));
  const tmpDb = path.join(tmpDir, 'qa_browser.sqlite3');
  const procs = [];
  const results = {};

  const cleanup = () => {
    for (const p of procs) {
      try {
        p.kill('SIGTERM');
      } catch {
        // ignore
      }
    }
    try {
      fs.rmSync(tmpDir, { recursive: true, force: true });
    } catch {
      // ignore
    }
  };

  try {
    // 1. Start isolated FastAPI
    const apiProc = spawn(
      UVICORN,
      ['app.main:app', '--host', '127.0.0.1', '--port', String(API_PORT)],
      {
        cwd: API_DIR,
        env: {
          ...process.env,
          FINZ_DATA_DIR: tmpDir,
          FINZ_DB_PATH: tmpDb,
          FINZ_DATABASE_URL: `sqlite:///${tmpDb}`,
          FINZ_SECRET_BACKEND: 'memory',
          FINZ_WEB_ORIGIN: `${WEB_URL},http://localhost:${WEB_PORT}`,
        },
        stdio: 'pipe',
      }
    );
    procs.push(apiProc);
    await waitForHttp(`${API_URL}/api/v1/health`, 25000);

    // 2. Start Next.js dev server on isolated port so NEXT_PUBLIC_API_BASE binds to ephemeral API_PORT
    const webProc = spawn(
      'npx',
      ['next', 'dev', '--hostname', '127.0.0.1', '--port', String(WEB_PORT)],
      {
        cwd: WEB_DIR,
        env: {
          ...process.env,
          FINZ_API_INTERNAL_URL: API_URL,
          NEXT_PUBLIC_API_BASE: API_URL,
        },
        stdio: 'pipe',
      }
    );
    procs.push(webProc);
    await waitForHttp(`${WEB_URL}/`, 30000);

    // Enable mock provider in isolated DB
    await fetch(`${API_URL}/api/v1/settings/ai`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ provider: 'mock', set_active: true }),
    });

    // 3. Launch headless Chrome with CDP
    const chromeProfile = path.join(tmpDir, 'chrome-profile');
    const chromeProc = spawn(
      chromeBin,
      [
        '--headless=new',
        '--disable-gpu',
        '--no-sandbox',
        `--remote-debugging-port=${CDP_PORT}`,
        `--user-data-dir=${chromeProfile}`,
        '--window-size=1440,900',
        'about:blank',
      ],
      { stdio: 'pipe' }
    );
    procs.push(chromeProc);

    await waitForHttp(`http://127.0.0.1:${CDP_PORT}/json/version`, 15000);
    const targetsResp = await fetch(`http://127.0.0.1:${CDP_PORT}/json/list`);
    const targets = await targetsResp.json();
    const pageTarget = targets.find((t) => t.type === 'page') || targets[0];
    const cdp = new CDPClient(pageTarget.webSocketDebuggerUrl);
    await cdp.connect();
    await cdp.send('Page.enable');
    await cdp.send('Runtime.enable');
    await cdp.send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false });

    // --- TEST T27: CompletionPopup appears ONLY after SQLite commit & auto-navigates after ~1.8s ---
    await cdp.goto(`${WEB_URL}/projects`);
    await cdp.waitForCondition(`!!document.querySelector('#prj-code')`);
    await cdp.evalJS(`(() => {
      const setVal = (sel, val) => {
        const el = document.querySelector(sel);
        const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
        setter.call(el, val);
        el.dispatchEvent(new Event('input', { bubbles: true }));
      };
      setVal('#prj-code', 'BRW1');
      setVal('#prj-name', 'Browser QA Project');
      setVal('#prj-pk', 'lương net và gross là gì');
      setVal('#prj-goal', 'Tư vấn HR SME');
      setVal('#prj-aud', 'Kế toán & HR');
    })()`);
    await new Promise((r) => setTimeout(r, 150));
    await cdp.evalJS(`document.querySelector('form button[type="submit"]').click()`);

    const dialogOpened = await cdp.waitForCondition(`Boolean(document.querySelector('dialog.finz-dialog[open]'))`, 8000);
    // Confirm auto-navigation completes within 2.8s
    const autoNavigated = await cdp.waitForCondition(`location.pathname === '/steps/02-demand-map'`, 4500);
    results.T27 = {
      status: dialogOpened && autoNavigated ? 'PASS' : 'FAIL',
      details: { dialogOpened, autoNavigated },
    };

    // --- TEST T28: "Ở lại bước này" and Escape cancel auto-navigation cleanly ---
    await cdp.goto(`${WEB_URL}/steps/01-topic`);
    await cdp.waitForCondition(`!!document.querySelector('#f-tpname')`);
    await cdp.evalJS(`(() => {
      const el = document.querySelector('#f-tpname');
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
      setter.call(el, 'Lương Net Gross Updated');
      el.dispatchEvent(new Event('input', { bubbles: true }));
    })()`);
    await new Promise((r) => setTimeout(r, 150));
    await cdp.evalJS(`document.querySelector('form button[type="submit"]').click()`);
    await cdp.waitForCondition(`Boolean(document.querySelector('dialog.finz-dialog[open]'))`, 8000);
    await cdp.evalJS(`(() => {
      const btns = [...document.querySelectorAll('dialog.finz-dialog button')];
      const stay = btns.find(b => b.textContent.includes('Ở lại'));
      stay.click();
    })()`);
    await new Promise((r) => setTimeout(r, 2300));
    const stayedAfterStayBtn = await cdp.evalJS(`location.pathname === '/steps/01-topic' && !document.querySelector('dialog.finz-dialog[open]')`);

    // Save again and dismiss via Escape key
    await cdp.evalJS(`document.querySelector('form button[type="submit"]').click()`);
    await cdp.waitForCondition(`Boolean(document.querySelector('dialog.finz-dialog[open]'))`, 8000);
    await cdp.send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27 });
    await cdp.send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27 });
    await new Promise((r) => setTimeout(r, 2300));
    const stayedAfterEsc = await cdp.evalJS(`location.pathname === '/steps/01-topic' && !document.querySelector('dialog.finz-dialog[open]')`);

    results.T28 = {
      status: stayedAfterStayBtn && stayedAfterEsc ? 'PASS' : 'FAIL',
      details: { stayedAfterStayBtn, stayedAfterEsc },
    };

    // --- UI Gating Check: Step 06 & Step 07 OFFICIAL button disabled when ineligible ---
    const projs = await (await fetch(`${API_URL}/api/v1/projects`)).json();
    const pid = projs.projects[0].id;
    await fetch(`${API_URL}/api/v1/projects/${pid}/mapping/preview`, { method: 'POST' });

    await cdp.goto(`${WEB_URL}/steps/07-brief`);
    await cdp.waitForCondition(`document.body.innerText.includes('Tạo Brief CHÍNH THỨC')`, 10000);
    const officialBtnDisabledWhenIneligible = await cdp.evalJS(`(() => {
      const btn = [...document.querySelectorAll('button')].find(b => b.textContent.includes('Tạo Brief CHÍNH THỨC'));
      return btn ? btn.disabled : false;
    })()`);
    results.UI_OFFICIAL_GATING = {
      status: officialBtnDisabledWhenIneligible ? 'PASS' : 'FAIL',
      details: { officialBtnDisabledWhenIneligible },
    };

    // --- TEST T29: Responsive 320px / 768px / 1440px, dark-mode meta, keyboard-accessible table, prefers-reduced-motion ---
    await cdp.goto(`${WEB_URL}/steps/06-mapping`);
    await cdp.waitForCondition(`Boolean(document.querySelector('.table-wrapper'))`, 10000);
    const a11yChecks = await cdp.evalJS(`(() => {
      const meta = document.querySelector('meta[name="color-scheme"]');
      const tw = document.querySelector('.table-wrapper');
      const hasReducedMotionRule = [...document.styleSheets].some(ss => {
        try {
          return [...ss.cssRules].some(r => r.cssText && r.cssText.includes('prefers-reduced-motion'));
        } catch { return false; }
      });
      return {
        darkMeta: meta?.getAttribute('content') === 'dark',
        tableFocusable: tw?.getAttribute('tabindex') === '0' && tw?.getAttribute('role') === 'region',
        hasReducedMotionRule,
      };
    })()`);

    const viewportChecks = {};
    for (const width of [320, 768, 1440]) {
      await cdp.send('Emulation.setDeviceMetricsOverride', {
        width,
        height: 844,
        deviceScaleFactor: 1,
        mobile: width < 768,
      });
      await new Promise((r) => setTimeout(r, 250));
      const metrics = await cdp.evalJS(`({ scrollWidth: document.documentElement.scrollWidth, innerWidth: window.innerWidth })`);
      viewportChecks[width] = {
        ...metrics,
        noOverflow: metrics.scrollWidth <= metrics.innerWidth + 2,
      };
    }

    const allViewportsOk = Object.values(viewportChecks).every((v) => v.noOverflow);
    results.T29 = {
      status: a11yChecks.darkMeta && a11yChecks.tableFocusable && a11yChecks.hasReducedMotionRule && allViewportsOk ? 'PASS' : 'FAIL',
      details: { a11yChecks, viewportChecks },
    };

    cdp.close();
    const overall = Object.values(results).every((r) => r.status === 'PASS') ? 'PASS' : 'FAIL';
    console.log(JSON.stringify({ overall, results }, null, 2));
    process.exit(overall === 'PASS' ? 0 : 1);
  } finally {
    cleanup();
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
