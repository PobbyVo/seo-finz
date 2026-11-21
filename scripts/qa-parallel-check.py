#!/usr/bin/env python3
"""
Bounded serial vs parallel pytest determinism verifier.
- Runs full pytest suite serially as reference.
- Runs independent test modules in bounded parallel workers (min(4, cpu_count)) with isolated per-worker TMPDIR.
- Compares passed/failed outcomes and fails closed if serial vs parallel outcomes diverge!
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYTEST = ROOT / "services" / "api" / ".venv" / "bin" / "pytest"
TEST_DIR = ROOT / "services" / "api" / "tests"


def run_module(mod_path: Path, worker_tmp: Path) -> dict:
    env = os.environ.copy()
    env["TMPDIR"] = str(worker_tmp)
    env["TEMP"] = str(worker_tmp)
    env["TMP"] = str(worker_tmp)
    started = time.perf_counter()
    proc = subprocess.run(
        [str(PYTEST), str(mod_path), "-q", "--tb=short"],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    elapsed = round(time.perf_counter() - started, 3)
    return {
        "module": mod_path.name,
        "exit_code": proc.returncode,
        "elapsed_s": elapsed,
        "stdout_tail": proc.stdout.strip().splitlines()[-3:] if proc.stdout.strip() else [],
        "stderr_tail": proc.stderr.strip().splitlines()[-3:] if proc.stderr.strip() else [],
    }


def main() -> int:
    modules = sorted(TEST_DIR.glob("test_*.py"))
    max_workers = min(4, os.cpu_count() or 2)

    # 1. Serial reference run
    serial_start = time.perf_counter()
    serial_proc = subprocess.run(
        [str(PYTEST), str(TEST_DIR), "-q", "--tb=short"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=180,
    )
    serial_elapsed = round(time.perf_counter() - serial_start, 3)

    # 2. Bounded parallel run across independent test modules with per-worker isolated tmp dirs
    parallel_start = time.perf_counter()
    parallel_results: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="finz-parallel-qa-") as base_tmp:
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {}
            for idx, mod in enumerate(modules):
                wtmp = Path(base_tmp) / f"worker_{idx}"
                wtmp.mkdir(parents=True, exist_ok=True)
                futures[pool.submit(run_module, mod, wtmp)] = mod
            for fut in as_completed(futures):
                parallel_results.append(fut.result())
    parallel_elapsed = round(time.perf_counter() - parallel_start, 3)
    parallel_results.sort(key=lambda r: r["module"])

    parallel_exit = 0 if all(r["exit_code"] == 0 for r in parallel_results) else 1
    parity = serial_proc.returncode == parallel_exit == 0

    report = {
        "cpu_count": os.cpu_count(),
        "bounded_workers": max_workers,
        "modules_count": len(modules),
        "serial": {
            "exit_code": serial_proc.returncode,
            "elapsed_s": serial_elapsed,
            "summary": serial_proc.stdout.strip().splitlines()[-2:] if serial_proc.stdout.strip() else [],
        },
        "parallel": {
            "exit_code": parallel_exit,
            "elapsed_s": parallel_elapsed,
            "modules": parallel_results,
        },
        "serial_parallel_parity": parity,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if parity else 1


if __name__ == "__main__":
    raise SystemExit(main())
