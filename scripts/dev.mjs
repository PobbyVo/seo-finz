#!/usr/bin/env node
/**
 * FinZ SEO Workbench — Single-command launcher (`npm run dev`).
 * Bootstraps Python venv + Next.js deps if missing, runs safe SQLite Alembic migration,
 * and launches both FastAPI (127.0.0.1:8000) and Next.js (127.0.0.1:3000) together.
 */
import { spawn, spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const ROOT = path.resolve(__dirname, '..');
const API_DIR = path.join(ROOT, 'services', 'api');
const WEB_DIR = path.join(ROOT, 'apps', 'web');
const VENV_DIR = path.join(API_DIR, '.venv');
const IS_WIN = process.platform === 'win32';
const VENV_PYTHON = IS_WIN
  ? path.join(VENV_DIR, 'Scripts', 'python.exe')
  : path.join(VENV_DIR, 'bin', 'python');
const VENV_UVICORN = IS_WIN
  ? path.join(VENV_DIR, 'Scripts', 'uvicorn.exe')
  : path.join(VENV_DIR, 'bin', 'uvicorn');
const VENV_ALEMBIC = IS_WIN
  ? path.join(VENV_DIR, 'Scripts', 'alembic.exe')
  : path.join(VENV_DIR, 'bin', 'alembic');

const API_PORT = process.env.FINZ_API_PORT || '8000';
const WEB_PORT = process.env.FINZ_WEB_PORT || '3000';
const SETUP_ONLY = process.argv.includes('--setup-only');

const C = {
  reset: '\x1b[0m',
  dim: '\x1b[2m',
  cyan: '\x1b[36m',
  violet: '\x1b[35m',
  green: '\x1b[32m',
  yellow: '\x1b[33m',
  red: '\x1b[31m',
};

function log(tag, color, msg) {
  const ts = new Date().toLocaleTimeString('vi-VN', { hour12: false });
  process.stdout.write(`${C.dim}${ts}${C.reset} ${color}[${tag}]${C.reset} ${msg}\n`);
}

function runSync(cmd, args, cwd, label) {
  log('SETUP', C.yellow, `${label}...`);
  const res = spawnSync(cmd, args, { cwd, stdio: 'inherit', shell: IS_WIN });
  if (res.status !== 0) {
    log('ERROR', C.red, `${label} thất bại (exit ${res.status}).`);
    process.exit(res.status || 1);
  }
}

function findSystemPython() {
  for (const candidate of IS_WIN ? ['py', 'python', 'python3'] : ['python3', 'python']) {
    const check = spawnSync(candidate, ['--version'], { stdio: 'pipe' });
    if (check.status === 0) return candidate;
  }
  log('ERROR', C.red, 'Không tìm thấy Python 3 trong PATH. Vui lòng cài Python 3.11+.');
  process.exit(1);
}

function ensureBackendSetup() {
  if (!fs.existsSync(VENV_PYTHON)) {
    const sysPy = findSystemPython();
    runSync(sysPy, ['-m', 'venv', VENV_DIR], API_DIR, 'Tạo Python virtual environment (services/api/.venv)');
  }
  const checkFastApi = spawnSync(VENV_PYTHON, ['-c', 'import fastapi, sqlalchemy, alembic, openpyxl, keyring, httpx'], {
    cwd: API_DIR,
    stdio: 'pipe',
  });
  if (checkFastApi.status !== 0) {
    runSync(VENV_PYTHON, ['-m', 'pip', 'install', '--upgrade', 'pip'], API_DIR, 'Cập nhật pip');
    runSync(VENV_PYTHON, ['-m', 'pip', 'install', '-r', 'requirements.txt'], API_DIR, 'Cài đặt thư viện backend FastAPI');
  }
  runSync(VENV_ALEMBIC, ['upgrade', 'head'], API_DIR, 'Chạy Alembic migration cho SQLite');
}

function ensureFrontendSetup() {
  const nextBin = path.join(WEB_DIR, 'node_modules', '.bin', IS_WIN ? 'next.cmd' : 'next');
  if (!fs.existsSync(nextBin)) {
    runSync(IS_WIN ? 'npm.cmd' : 'npm', ['install'], WEB_DIR, 'Cài đặt thư viện frontend Next.js');
  }
}

function pipePrefixed(stream, tag, color) {
  let buf = '';
  stream.on('data', (chunk) => {
    buf += chunk.toString();
    const lines = buf.split(/\r?\n/);
    buf = lines.pop() ?? '';
    for (const line of lines) {
      if (line.trim().length > 0) log(tag, color, line);
    }
  });
}

function main() {
  log('FINZ', C.green, 'Khởi động FinZ SEO Workbench V2.0 (Dark Mode, Local-First)...');
  ensureBackendSetup();
  ensureFrontendSetup();

  if (SETUP_ONLY) {
    log('FINZ', C.green, 'Hoàn tất thiết lập môi trường!');
    return;
  }

  const children = [];
  let shuttingDown = false;

  const shutdown = (signal) => {
    if (shuttingDown) return;
    shuttingDown = true;
    log('FINZ', C.yellow, `Nhận tín hiệu ${signal}, đang dừng backend & frontend...`);
    for (const child of children) {
      if (!child.killed) {
        try {
          child.kill('SIGTERM');
        } catch {
          // ignore
        }
      }
    }
    setTimeout(() => process.exit(0), 600);
  };

  process.on('SIGINT', () => shutdown('SIGINT'));
  process.on('SIGTERM', () => shutdown('SIGTERM'));

  log('API', C.cyan, `Khởi chạy FastAPI tại http://127.0.0.1:${API_PORT}`);
  const apiProc = spawn(
    VENV_UVICORN,
    ['app.main:app', '--host', '127.0.0.1', '--port', API_PORT, '--reload'],
    {
      cwd: API_DIR,
      env: {
        ...process.env,
        PYTHONUNBUFFERED: '1',
        FINZ_API_PORT: API_PORT,
        FINZ_WEB_ORIGIN: `http://127.0.0.1:${WEB_PORT},http://localhost:${WEB_PORT}`,
      },
    }
  );
  children.push(apiProc);
  pipePrefixed(apiProc.stdout, 'API', C.cyan);
  pipePrefixed(apiProc.stderr, 'API', C.cyan);

  log('WEB', C.violet, `Khởi chạy Next.js tại http://127.0.0.1:${WEB_PORT}`);
  const webProc = spawn(
    IS_WIN ? 'npm.cmd' : 'npm',
    ['run', 'dev', '--', '--hostname', '127.0.0.1', '--port', WEB_PORT],
    {
      cwd: WEB_DIR,
      env: {
        ...process.env,
        NEXT_PUBLIC_API_BASE: `http://127.0.0.1:${API_PORT}`,
        FINZ_API_INTERNAL_URL: `http://127.0.0.1:${API_PORT}`,
      },
    }
  );
  children.push(webProc);
  pipePrefixed(webProc.stdout, 'WEB', C.violet);
  pipePrefixed(webProc.stderr, 'WEB', C.violet);

  apiProc.on('exit', (code) => {
    if (!shuttingDown) {
      log('API', C.red, `Backend đã thoát với mã ${code}. Dừng hệ thống...`);
      shutdown('API_EXIT');
    }
  });
  webProc.on('exit', (code) => {
    if (!shuttingDown) {
      log('WEB', C.red, `Frontend đã thoát với mã ${code}. Dừng hệ thống...`);
      shutdown('WEB_EXIT');
    }
  });

  log('FINZ', C.green, `Sẵn sàng! Mở trình duyệt tại: http://127.0.0.1:${WEB_PORT}  (API Docs: http://127.0.0.1:${API_PORT}/docs)`);
}

main();
