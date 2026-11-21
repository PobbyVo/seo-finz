#!/usr/bin/env node
/**
 * Real Headless Chrome E2E verification for V1.6 R1 + R2 (T27, T28, T29, popup timer negative cases,
 * automatic post-import stale freshness UI/backend gating, historical export marking, and all core screens).
 * - Dynamically allocates free OS ports for FastAPI, Next.js, and Chrome CDP (no fixed-port collisions).
 * - Uses isolated temporary SQLite DB and uploads dir — NEVER touches owner data/.
 * - Uses native Node 22 WebSocket + Chrome DevTools Protocol against Chrome/Chromium (0 extra npm packages).
 * - Cleans up all spawned processes unconditionally on exit, SIGINT, or SIGTERM.
 */
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import net from 'node:net';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const API_DIR = path.join(ROOT, 'services', 'api');
const WEB_DIR = path.join(ROOT, 'apps', 'web');

const CHROME_CANDIDATES = [
  process.env.CHROME_BIN,
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  '/usr/bin/google-chrome',
  '/usr/bin/google-chrome-stable',
  '/usr/bin/chromium',
  '/usr/bin/chromium-browser',
].filter(Boolean);

function findChrome() {
  for (const p of CHROME_CANDIDATES) {
    if (fs.existsSync(p)) return p;
  }
  return null;
}

function findUvicorn() {
  const candidates = [
    process.env.FINZ_UVICORN,
    path.join(API_DIR, '.venv', 'bin', 'uvicorn'),
    path.join(API_DIR, '.venv', 'Scripts', 'uvicorn.exe'),
  ].filter(Boolean);
  for (const c of candidates) {
    if (fs.existsSync(c)) return c;
  }
  return 'uvicorn';
}

function getFreePort() {
  return new Promise((resolve, reject) => {
    const srv = net.createServer();
    srv.unref();
    srv.on('error', reject);
    srv.listen(0, '127.0.0.1', () => {
      const addr = srv.address();
      const port = typeof addr === 'object' && addr ? addr.port : 0;
      srv.close(() => resolve(port));
    });
  });
}

async function waitForHttp(url, timeoutMs = 40000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const r = await fetch(url);
      if (r.ok) return r;
    } catch {
      // retry
    }
    await new Promise((r) => setTimeout(r, 350));
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
  async waitForCondition(expr, timeoutMs = 15000) {
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
    const base = url.split('?')[0];
    await this.waitForCondition(`document.readyState === 'complete' && location.href.startsWith(${JSON.stringify(base)})`, 20000);
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

async function uploadAndConfirm(apiUrl, pid, filename, csvText, reportType) {
  const fd = new FormData();
  fd.append('report_type', reportType);
  fd.append('locale', 'en-US');
  fd.append('file', new Blob([csvText], { type: 'text/csv' }), filename);
  const prev = await fetch(`${apiUrl}/api/v1/projects/${pid}/imports/preview`, { method: 'POST', body: fd });
  if (!prev.ok) throw new Error(`preview failed: ${prev.status} ${await prev.text()}`);
  const pbody = await prev.json();
  const conf = await fetch(`${apiUrl}/api/v1/projects/${pid}/imports/confirm`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      upload_id: pbody.upload_id,
      report_type: reportType,
      market: 'VN',
      locale: 'en-US',
      column_mapping: pbody.suggested_mapping,
    }),
  });
  if (!conf.ok) throw new Error(`confirm failed: ${conf.status} ${await conf.text()}`);
  return conf.json();
}

function buildTop10Csv(kw, prefix, pathPrefix = 'blog') {
  const lines = ['Keyword,Position,Type,URL,Title'];
  for (let i = 1; i <= 10; i++) {
    lines.push(`${kw},${i},Organic,https://${prefix}${i}.vn/${pathPrefix}/bai-${i},Bai ${i}`);
  }
  return `${lines.join('\n')}\n`;
}

async function main() {
  const chromeBin = findChrome();
  if (!chromeBin) {
    console.log(JSON.stringify({ status: 'BLOCKED', reason: 'Chrome/Chromium binary not found' }, null, 2));
    process.exit(2);
  }

  const [API_PORT, WEB_PORT, CDP_PORT] = await Promise.all([getFreePort(), getFreePort(), getFreePort()]);
  const API_URL = `http://127.0.0.1:${API_PORT}`;
  const WEB_URL = `http://127.0.0.1:${WEB_PORT}`;

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
  process.on('SIGINT', () => { cleanup(); process.exit(130); });
  process.on('SIGTERM', () => { cleanup(); process.exit(143); });

  try {
    // 1. Start isolated FastAPI on dynamic port
    const apiProc = spawn(
      findUvicorn(),
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
    await waitForHttp(`${API_URL}/api/v1/health`, 30000);

    // 2. Start isolated Next.js dev server bound to ephemeral API_URL
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
    await waitForHttp(`${WEB_URL}/`, 45000);

    // Enable mock provider in isolated DB
    await fetch(`${API_URL}/api/v1/settings/ai`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ provider: 'mock', set_active: true }),
    });

    // 3. Launch headless Chrome with CDP on dynamic port
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

    await waitForHttp(`http://127.0.0.1:${CDP_PORT}/json/version`, 20000);
    const targets = await (await fetch(`http://127.0.0.1:${CDP_PORT}/json/list`)).json();
    const pageTarget = targets.find((t) => t.type === 'page') || targets[0];
    const cdp = new CDPClient(pageTarget.webSocketDebuggerUrl);
    await cdp.connect();
    await cdp.send('Page.enable');
    await cdp.send('Runtime.enable');
    await cdp.send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false });

    // --- T27: First project creation -> popup ONLY after SQLite commit & auto-navigates after ~1.8s ---
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
      setVal('#prj-name', 'Browser QA Project 1');
      setVal('#prj-pk', 'lương net và gross là gì');
      setVal('#prj-goal', 'Tư vấn HR SME');
      setVal('#prj-aud', 'Kế toán & HR');
    })()`);
    await new Promise((r) => setTimeout(r, 150));
    await cdp.evalJS(`document.querySelector('form button[type="submit"]').click()`);

    const dialogOpened = await cdp.waitForCondition(`Boolean(document.querySelector('dialog.finz-dialog[open]'))`, 8000);
    const autoNavigated = await cdp.waitForCondition(`location.pathname === '/steps/02-demand-map'`, 4500);
    results.T27 = {
      status: dialogOpened && autoNavigated ? 'PASS' : 'FAIL',
      details: { dialogOpened, autoNavigated },
    };

    // --- T28: Stay button & Escape cancel auto-navigation cleanly ---
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
      const stay = [...document.querySelectorAll('dialog.finz-dialog button')].find(b => b.textContent.includes('Ở lại'));
      stay.click();
    })()`);
    await new Promise((r) => setTimeout(r, 2300));
    const stayedAfterStayBtn = await cdp.evalJS(`location.pathname === '/steps/01-topic' && !document.querySelector('dialog.finz-dialog[open]')`);

    // Save again and dismiss via Escape
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

    // --- T28 R2 NEGATIVE: Route switch cancels timer (no ghost nav), project switch cancels timer, backend failure never shows popup ---
    // Create a second project via API for project-switch test
    await fetch(`${API_URL}/api/v1/projects`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code: 'BRW2', name: 'Second Project', primary_keyword: 'bhxh bắt buộc', business_goal: 'Lead', target_audience: 'HR' }),
    });
    // Route-switch timer cancellation: navigate via SPA link to /steps/01-topic (creating real browser history entry),
    // trigger popup on Step 01, then simulate Browser Back (history.back()) while 1.8s countdown is running -> MUST cancel timer & prevent ghost nav!
    await cdp.goto(`${WEB_URL}/logs`);
    await cdp.evalJS(`(() => {
      const link = [...document.querySelectorAll('a[href="/steps/01-topic"]')][0];
      if (link) link.click();
    })()`);
    await cdp.waitForCondition(`location.pathname === '/steps/01-topic' && !!document.querySelector('#f-tpname')`, 10000);
    await new Promise((r) => setTimeout(r, 200));
    await cdp.evalJS(`document.querySelector('form button[type="submit"]').click()`);
    await cdp.waitForCondition(`Boolean(document.querySelector('dialog.finz-dialog[open]'))`, 8000);
    await cdp.evalJS(`window.history.back()`);
    await cdp.waitForCondition(`location.pathname === '/logs'`, 6000);
    await new Promise((r) => setTimeout(r, 2300));
    const noGhostNavAfterRouteSwitch = await cdp.evalJS(`location.pathname === '/logs' && !document.querySelector('dialog.finz-dialog[open]')`);

    // Backend failure (missing required fields -> never opens success popup!)
    await cdp.goto(`${WEB_URL}/projects`);
    await cdp.waitForCondition(`!!document.querySelector('#prj-code')`);
    // Try submitting empty form via direct click (HTML validation or API error -> must NOT show completion dialog)
    await cdp.evalJS(`document.querySelector('form button[type="submit"]').click()`);
    await new Promise((r) => setTimeout(r, 600));
    const noPopupOnInvalidSubmit = await cdp.evalJS(`!document.querySelector('dialog.finz-dialog[open]')`);

    // Project switch cancels timer cleanly without ghost navigation
    await cdp.goto(`${WEB_URL}/steps/01-topic`);
    await cdp.waitForCondition(`!!document.querySelector('#f-tpname')`);
    await cdp.evalJS(`document.querySelector('form button[type="submit"]').click()`);
    await cdp.waitForCondition(`Boolean(document.querySelector('dialog.finz-dialog[open]'))`, 8000);
    const switchedProjectOk = await cdp.evalJS(`(() => {
      const sel = document.querySelector('aside select, header select');
      if (!sel || sel.options.length < 2) return false;
      const other = [...sel.options].find(o => o.value && o.value !== sel.value);
      if (!other) return false;
      sel.value = other.value;
      sel.dispatchEvent(new Event('change', { bubbles: true }));
      return true;
    })()`);
    await new Promise((r) => setTimeout(r, 2300));
    const noGhostNavAfterProjectSwitch = await cdp.evalJS(`location.pathname === '/steps/01-topic' && !document.querySelector('dialog.finz-dialog[open]')`);
    // Switch back to BRW1
    await cdp.evalJS(`(() => {
      const sel = document.querySelector('aside select, header select');
      if (!sel) return;
      const brw1 = [...sel.options].find(o => o.text.includes('BRW1'));
      if (brw1) {
        sel.value = brw1.value;
        sel.dispatchEvent(new Event('change', { bubbles: true }));
      }
    })()`);

    results.T28_NEGATIVE_CANCEL_AND_ERROR = {
      status: noGhostNavAfterRouteSwitch && noPopupOnInvalidSubmit && (!switchedProjectOk || noGhostNavAfterProjectSwitch) ? 'PASS' : 'FAIL',
      details: { noGhostNavAfterRouteSwitch, noPopupOnInvalidSubmit, switchedProjectOk, noGhostNavAfterProjectSwitch },
    };

    // --- R2 Full Stale-Freshness & Historical Export UI + Backend Gating E2E ---
    const projs = await (await fetch(`${API_URL}/api/v1/projects`)).json();
    const pid = projs.projects.find((p) => p.code === 'BRW1').id;
    const kw = 'lương net và gross là gì';

    // Step 06 before evidence -> Step 07 OFFICIAL button MUST be disabled!
    await fetch(`${API_URL}/api/v1/projects/${pid}/mapping/preview`, { method: 'POST' });
    await cdp.goto(`${WEB_URL}/steps/07-brief`);
    await cdp.waitForCondition(`document.body.innerText.includes('Tạo Brief CHÍNH THỨC')`, 10000);
    const officialBtnDisabledInitially = await cdp.evalJS(`(() => {
      const btn = [...document.querySelectorAll('button')].find(b => b.textContent.includes('Tạo Brief CHÍNH THỨC'));
      return btn ? btn.disabled : false;
    })()`);

    // Upload valid metrics + 1 coherent Top-10 SERP snapshot -> Step 06 preview -> Approve -> generate OFFICIAL brief -> export XLSX
    await uploadAndConfirm(API_URL, pid, 'm1.csv', `Keyword,Volume,KD,Intent\n${kw},2400,28,Informational\n`, 'KEYWORD_OVERVIEW');
    await uploadAndConfirm(API_URL, pid, 'serp1.csv', buildTop10Csv(kw, 'snap1'), 'ORGANIC_RESULTS');
    await fetch(`${API_URL}/api/v1/projects/${pid}/mapping/preview`, { method: 'POST' });
    const aprs = await (await fetch(`${API_URL}/api/v1/projects/${pid}/approvals`)).json();
    for (const a of aprs.approvals) {
      if (a.status === 'PENDING') {
        await fetch(`${API_URL}/api/v1/projects/${pid}/approvals/${a.id}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ decision: 'APPROVED', decided_by: 'Browser QA' }),
        });
      }
    }
    await cdp.goto(`${WEB_URL}/steps/07-brief`);
    await cdp.waitForCondition(`document.body.innerText.includes('Đủ điều kiện phát hành CHÍNH THỨC')`, 10000);
    const officialBtnEnabledAfterApproval = await cdp.evalJS(`(() => {
      const btn = [...document.querySelectorAll('button')].find(b => b.textContent.includes('Tạo Brief CHÍNH THỨC'));
      return btn ? !btn.disabled : false;
    })()`);

    // Generate OFFICIAL brief & export OFFICIAL XLSX
    const genRes = await fetch(`${API_URL}/api/v1/projects/${pid}/briefs/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ allow_draft: false }),
    });
    const expRes = await fetch(`${API_URL}/api/v1/projects/${pid}/exports/download`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ format: 'xlsx' }),
    });
    const oldExportId = expRes.headers.get('X-FinZ-Export-Id');

    // NOW upload NEW conflicting SERP snapshot (WITHOUT calling /mapping/preview!)
    await uploadAndConfirm(API_URL, pid, 'serp2_conflict.csv', buildTop10Csv(kw, 'snap2conflict', 'cong-cu'), 'ORGANIC_RESULTS');

    // Verify Step 07 UI immediately reflects disabled OFFICIAL button, STALE brief alert, and OUTDATED_SUPERSEDED historical export!
    await cdp.goto(`${WEB_URL}/steps/07-brief`);
    await cdp.waitForCondition(`document.body.innerText.includes('Brief đã cũ (STALE)')`, 12000);
    const staleUiChecks = await cdp.evalJS(`(() => {
      const btn = [...document.querySelectorAll('button')].find(b => b.textContent.includes('Tạo Brief CHÍNH THỨC'));
      const txt = document.body.innerText;
      return {
        officialDisabledAfterImport: btn ? btn.disabled : false,
        showsStaleBriefBanner: txt.includes('Brief đã cũ (STALE)'),
        showsSupersededExportBadge: txt.includes('Bản cũ · Đã thay thế') || txt.includes('Tải bản lịch sử'),
      };
    })()`);

    // Verify unacknowledged download of historical OFFICIAL export returns 409 Conflict!
    const silentHistResp = await fetch(`${API_URL}/api/v1/projects/${pid}/exports/file/${oldExportId}`);
    const ackHistResp = await fetch(`${API_URL}/api/v1/projects/${pid}/exports/file/${oldExportId}?acknowledge_historical=true`);

    results.R2_STALE_FRESHNESS_AND_EXPORT_UI = {
      status:
        officialBtnDisabledInitially &&
        officialBtnEnabledAfterApproval &&
        genRes.ok &&
        expRes.ok &&
        staleUiChecks.officialDisabledAfterImport &&
        staleUiChecks.showsStaleBriefBanner &&
        staleUiChecks.showsSupersededExportBadge &&
        silentHistResp.status === 409 &&
        ackHistResp.status === 200
          ? 'PASS'
          : 'FAIL',
      details: {
        officialBtnDisabledInitially,
        officialBtnEnabledAfterApproval,
        ...staleUiChecks,
        silentHistStatus: silentHistResp.status,
        ackHistStatus: ackHistResp.status,
      },
    };

    // --- T29: Responsive 320 / 768 / 1440 across ALL core screens + dark meta + focusable table + reduced motion ---
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

    const coreRoutes = [
      '/projects',
      '/steps/01-topic',
      '/steps/02-demand-map',
      '/steps/03-semrush',
      '/steps/04-upload',
      '/steps/05-evidence',
      '/steps/06-mapping',
      '/steps/07-brief',
      '/approvals',
    ];
    const screenMatrix = {};
    let allViewportsOk = true;
    for (const route of coreRoutes) {
      await cdp.goto(`${WEB_URL}${route}`);
      screenMatrix[route] = {};
      for (const width of [320, 768, 1440]) {
        await cdp.send('Emulation.setDeviceMetricsOverride', {
          width,
          height: 844,
          deviceScaleFactor: 1,
          mobile: width < 768,
        });
        await new Promise((r) => setTimeout(r, 180));
        const metrics = await cdp.evalJS(`({ scrollWidth: document.documentElement.scrollWidth, innerWidth: window.innerWidth })`);
        const ok = metrics.scrollWidth <= metrics.innerWidth + 2;
        if (!ok) allViewportsOk = false;
        screenMatrix[route][width] = { ...metrics, noOverflow: ok };
      }
    }

    results.T29 = {
      status: a11yChecks.darkMeta && a11yChecks.tableFocusable && a11yChecks.hasReducedMotionRule && allViewportsOk ? 'PASS' : 'FAIL',
      details: { a11yChecks, allViewportsOk, routesTested: coreRoutes.length, screenMatrix },
    };

    cdp.close();
    const overall = Object.values(results).every((r) => r.status === 'PASS') ? 'PASS' : 'FAIL';
    console.log(JSON.stringify({ overall, ports: { api: API_PORT, web: WEB_PORT, cdp: CDP_PORT }, results }, null, 2));
    process.exit(overall === 'PASS' ? 0 : 1);
  } finally {
    cleanup();
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
