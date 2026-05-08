#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKEND="$REPO_ROOT/backend"
FRONTEND="$REPO_ROOT/frontend"
PYTHON_BIN="${PYTHON_BIN:-$BACKEND/.venv/Scripts/python.exe}"
NPM_BIN="${NPM_BIN:-npm}"
EVIDENCE_SCRIPT="$SCRIPT_DIR/final_check_evidence.py"
MODE="${1:-all}"

usage() {
  cat <<'USAGE'
Usage: bash scripts/final_check.sh [all|evidence-only|skip-frontend|audit-log]

all            Run backend tests, frontend tests, frontend build, then print formal experiment validation report.
evidence-only  Print formal experiment validation report only.
skip-frontend  Run backend tests and print formal experiment validation report.
audit-log      Print screenshot-friendly experiment process log only.
USAGE
}

run_step() {
  local title="$1"
  shift
  printf '\n========== %s ==========' "$title"
  printf '\n'
  "$@"
}

require_file() {
  local file_path="$1"
  if [[ ! -f "$file_path" ]]; then
    printf 'Missing required file: %s\n' "$file_path" >&2
    exit 1
  fi
}

backend_tests() {
  require_file "$PYTHON_BIN"
  PYTHONPATH="$BACKEND" "$PYTHON_BIN" -m pytest "$BACKEND/tests" -q
}

frontend_tests() {
  "$NPM_BIN" --prefix "$FRONTEND" run test:run
}

frontend_build() {
  "$NPM_BIN" --prefix "$FRONTEND" run build
}

print_evidence_summary() {
  require_file "$PYTHON_BIN"
  require_file "$EVIDENCE_SCRIPT"
  REPO_ROOT="$REPO_ROOT" PYTHONIOENCODING="utf-8" "$PYTHON_BIN" "$EVIDENCE_SCRIPT"
}

print_audit_log() {
  require_file "$PYTHON_BIN"
  require_file "$EVIDENCE_SCRIPT"
  REPO_ROOT="$REPO_ROOT" PYTHONIOENCODING="utf-8" "$PYTHON_BIN" "$EVIDENCE_SCRIPT" --audit-log
}

case "$MODE" in
  all)
    run_step "后端全量测试" backend_tests
    run_step "前端 Vitest" frontend_tests
    run_step "前端生产构建" frontend_build
    run_step "论文实验数据验证报告" print_evidence_summary
    ;;
  evidence-only|--evidence-only)
    run_step "论文实验数据验证报告" print_evidence_summary
    ;;
  skip-frontend|--skip-frontend)
    run_step "后端全量测试" backend_tests
    run_step "论文实验数据验证报告" print_evidence_summary
    ;;
  audit-log|--audit-log)
    run_step "Paper experiment audit log" print_audit_log
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    usage >&2
    exit 1
    ;;
esac
