#!/usr/bin/env python3
"""
Bounded serial vs parallel pytest determinism verifier (R2 upgraded).
- Runs full pytest suite serially as reference and parses EVERY individual test nodeid + outcome.
- Runs independent test modules in bounded parallel workers (min(4, cpu_count)) with isolated per-worker TMPDIR,
  while keeping destructive/migration modules serialized on isolated temp directories.
- Compares EXACT per-test-case outcomes (nodeid -> PASSED/FAILED/SKIPPED), NOT only exit code 0!
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENV_PYTEST = ROOT / "services" / "api" / ".venv" / "bin" / "pytest"
TEST_DIR = ROOT / "services" / "api" / "tests"

# Migration/backup modules run serially in their own isolated temp dir (never sharing DB state)
SERIAL_ONLY_MODULES = {
    "test_p1_backup_migration_uploads_e2e.py",
    "test_r2_p1_backup_f2_downgrade.py",
}

_CASE_RE = re.compile(r"^(services/api/tests/\S+::\S+)\s+(PASSED|FAILED|SKIPPED|ERROR|XFAIL|XPASS)\b")


def resolve_pytest_cmd() -> list[str]:
    if VENV_PYTEST.exists():
        return [str(VENV_PYTEST)]
    return [sys.executable, "-m", "pytest"]


def parse_case_outcomes(stdout: str) -> dict[str, str]:
    outcomes: dict[str, str] = {}
    for line in stdout.splitlines():
        m = _CASE_RE.match(line.strip())
        if m:
            outcomes[m.group(1)] = m.group(2)
    return outcomes


def run_module(pytest_cmd: list[str], mod_path: Path, worker_tmp: Path) -> dict:
    env = os.environ.copy()
    env["TMPDIR"] = str(worker_tmp)
    env["TEMP"] = str(worker_tmp)
    env["TMP"] = str(worker_tmp)
    env["FINZ_SECRET_BACKEND"] = "memory"
    started = time.perf_counter()
    proc = subprocess.run(
        [*pytest_cmd, str(mod_path), "-v", "--tb=short"],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=150,
    )
    elapsed = round(time.perf_counter() - started, 3)
    cases = parse_case_outcomes(proc.stdout)
    return {
        "module": mod_path.name,
        "exit_code": proc.returncode,
        "elapsed_s": elapsed,
        "cases": cases,
        "cases_count": len(cases),
        "stdout_tail": proc.stdout.strip().splitlines()[-3:] if proc.stdout.strip() else [],
        "stderr_tail": proc.stderr.strip().splitlines()[-3:] if proc.stderr.strip() else [],
    }


def main() -> int:
    pytest_cmd = resolve_pytest_cmd()
    modules = sorted(TEST_DIR.glob("test_*.py"))
    max_workers = min(4, os.cpu_count() or 2)

    # 1. Serial reference run (hermetic temp dir)
    serial_start = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="finz-serial-qa-") as serial_tmp:
        env = os.environ.copy()
        env["TMPDIR"] = serial_tmp
        env["TEMP"] = serial_tmp
        env["TMP"] = serial_tmp
        env["FINZ_SECRET_BACKEND"] = "memory"
        serial_proc = subprocess.run(
            [*pytest_cmd, str(TEST_DIR), "-v", "--tb=short"],
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=240,
        )
    serial_elapsed = round(time.perf_counter() - serial_start, 3)
    serial_cases = parse_case_outcomes(serial_proc.stdout)

    # 2. Bounded parallel run across independent API test modules + serialized migration/backup modules
    parallel_mods = [m for m in modules if m.name not in SERIAL_ONLY_MODULES]
    serial_only_mods = [m for m in modules if m.name in SERIAL_ONLY_MODULES]

    parallel_start = time.perf_counter()
    parallel_results: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="finz-parallel-qa-") as base_tmp:
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {}
            for idx, mod in enumerate(parallel_mods):
                wtmp = Path(base_tmp) / f"worker_{idx}"
                wtmp.mkdir(parents=True, exist_ok=True)
                futures[pool.submit(run_module, pytest_cmd, mod, wtmp)] = mod
            for fut in as_completed(futures):
                parallel_results.append(fut.result())

        # Run migration/backup modules serially in their own isolated worker directories
        for idx, mod in enumerate(serial_only_mods, start=len(parallel_mods)):
            wtmp = Path(base_tmp) / f"serial_mig_{idx}"
            wtmp.mkdir(parents=True, exist_ok=True)
            parallel_results.append(run_module(pytest_cmd, mod, wtmp))

    parallel_elapsed = round(time.perf_counter() - parallel_start, 3)
    parallel_results.sort(key=lambda r: r["module"])

    parallel_cases: dict[str, str] = {}
    for r in parallel_results:
        parallel_cases.update(r["cases"])

    parallel_exit = 0 if all(r["exit_code"] == 0 for r in parallel_results) else 1
    case_identity_parity = bool(serial_cases) and (serial_cases == parallel_cases)
    parity = (serial_proc.returncode == parallel_exit == 0) and case_identity_parity

    divergences = {
        k: {"serial": serial_cases.get(k), "parallel": parallel_cases.get(k)}
        for k in sorted(set(serial_cases) | set(parallel_cases))
        if serial_cases.get(k) != parallel_cases.get(k)
    }

    report = {
        "python": sys.version.split()[0],
        "cpu_count": os.cpu_count(),
        "bounded_workers": max_workers,
        "modules_count": len(modules),
        "parallel_modules_count": len(parallel_mods),
        "serialized_migration_modules": sorted(m.name for m in serial_only_mods),
        "serial": {
            "exit_code": serial_proc.returncode,
            "elapsed_s": serial_elapsed,
            "cases_count": len(serial_cases),
            "passed_count": sum(1 for v in serial_cases.values() if v == "PASSED"),
            "summary": serial_proc.stdout.strip().splitlines()[-2:] if serial_proc.stdout.strip() else [],
        },
        "parallel": {
            "exit_code": parallel_exit,
            "elapsed_s": parallel_elapsed,
            "cases_count": len(parallel_cases),
            "passed_count": sum(1 for v in parallel_cases.values() if v == "PASSED"),
            "modules": [
                {k: v for k, v in r.items() if k != "cases"}
                for r in parallel_results
            ],
        },
        "case_identity_parity": case_identity_parity,
        "divergences": divergences,
        "serial_parallel_parity": parity,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if parity else 1


if __name__ == "__main__":
    raise SystemExit(main())
