"""Run repeatable local performance baselines."""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_ROOT = REPO_ROOT / "frontend"


def _npm_command() -> str:
    return "npm.cmd" if os.name == "nt" else "npm"


def _backend_python() -> str:
    candidate = REPO_ROOT / "backend" / ".venv" / "Scripts" / "python.exe"
    return str(candidate if candidate.exists() else Path(sys.executable))


def _run(label: str, command: list[str], cwd: Path) -> None:
    print(f"\n== {label} ==")
    print(" ".join(command))
    subprocess.run(command, cwd=cwd, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run LearnPath performance baselines")
    parser.add_argument("--skip-backend", action="store_true", help="Skip backend graph API timing tests")
    parser.add_argument("--skip-frontend-knowledge", action="store_true", help="Skip Knowledge first-screen request tests")
    parser.add_argument("--skip-frontend-bundle", action="store_true", help="Skip frontend production build and bundle budget")
    args = parser.parse_args()

    if not args.skip_backend:
        _run(
            "backend graph API performance",
            [_backend_python(), "-m", "pytest", "backend/tests/test_performance_baseline.py", "-q", "-s"],
            REPO_ROOT,
        )
    if not args.skip_frontend_knowledge:
        _run("frontend Knowledge request baseline", [_npm_command(), "run", "perf:knowledge"], FRONTEND_ROOT)
    if not args.skip_frontend_bundle:
        _run("frontend bundle budget", [_npm_command(), "run", "perf:bundle"], FRONTEND_ROOT)

    print("\nPerformance baselines passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
