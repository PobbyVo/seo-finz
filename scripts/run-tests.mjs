#!/usr/bin/env node
import { spawnSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const IS_WIN = process.platform === 'win32';
const PYTEST = IS_WIN
  ? path.join(ROOT, 'services', 'api', '.venv', 'Scripts', 'pytest.exe')
  : path.join(ROOT, 'services', 'api', '.venv', 'bin', 'pytest');

const r1 = spawnSync(PYTEST, ['tests', '-v'], {
  cwd: path.join(ROOT, 'services', 'api'),
  stdio: 'inherit',
});
if (r1.status !== 0) process.exit(r1.status || 1);

const r2 = spawnSync(IS_WIN ? 'npm.cmd' : 'npm', ['--prefix', 'apps/web', 'run', 'typecheck'], {
  cwd: ROOT,
  stdio: 'inherit',
});
process.exit(r2.status || 0);
