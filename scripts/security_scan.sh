#!/usr/bin/env bash
# WorkforceOS dependency and code security scan (Phase 4).
#
#   ./scripts/security_scan.sh            run every available scanner
#   ./scripts/security_scan.sh --strict   exit non-zero if any scanner reports findings
#
# Runs from the project root. Uses backend/.venv if it exists, otherwise whatever
# python3 is on PATH. Reports go to ./security-reports/<date>/ (git-ignored).
#
# Scanners:
#   bandit     static analysis of OUR Python code      (pip install -r backend/requirements-security.txt)
#   pip-audit  known vulnerabilities in Python packages (same file)
#   npm audit  known vulnerabilities in npm packages    (comes with npm)
#   trivy      filesystem scan of lockfiles + secrets   (optional: https://trivy.dev, see docs/SECURITY.md)
#
# A clean report means "no KNOWN issue matched", not "secure". See docs/SECURITY_ASSESSMENT.md.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
STRICT=0; [[ "${1:-}" == "--strict" ]] && STRICT=1
OUT="security-reports/$(date +%Y-%m-%d_%H%M%S)"
mkdir -p "$OUT"

if [[ -x backend/.venv/bin/python ]]; then PY=backend/.venv/bin/python; else PY=python3; fi
found=0
section() { printf '\n==== %s ====\n' "$1"; }
missing() { printf 'SKIPPED: %s is not installed. %s\n' "$1" "$2"; }

section "bandit (Python code)"
if $PY -m bandit --version >/dev/null 2>&1; then
  # -ll: medium severity and above; tests are excluded (they use assert and fake passwords on purpose)
  $PY -m bandit -r backend/app -ll -q -f txt -o "$OUT/bandit.txt"; rc=$?
  $PY -m bandit -r backend/app -q -f json -o "$OUT/bandit.json" >/dev/null 2>&1
  cat "$OUT/bandit.txt"
  [[ $rc -ne 0 ]] && found=1
else missing bandit "pip install -r backend/requirements-security.txt"; fi

section "pip-audit (Python packages)"
if $PY -m pip_audit --version >/dev/null 2>&1; then
  $PY -m pip_audit -r backend/requirements.txt --progress-spinner off 2>&1 | tee "$OUT/pip-audit.txt"; rc=${PIPESTATUS[0]}
  [[ $rc -ne 0 ]] && found=1
else missing pip-audit "pip install -r backend/requirements-security.txt"; fi

section "npm audit (frontend packages)"
if command -v npm >/dev/null; then
  (cd frontend && npm audit --omit=dev 2>&1) | tee "$OUT/npm-audit-production.txt"; rc=${PIPESTATUS[0]}
  [[ $rc -ne 0 ]] && found=1
  echo "--- including development tools (Vite, Vitest, ...): ---"
  (cd frontend && npm audit 2>&1) | tee "$OUT/npm-audit-all.txt" | tail -n 5
else missing npm "Install Node.js 20+"; fi

section "trivy (lockfiles + accidentally committed secrets)"
if command -v trivy >/dev/null; then
  trivy fs --scanners vuln,secret,misconfig --skip-dirs frontend/node_modules --skip-dirs backend/.venv \
        --skip-dirs security-reports --exit-code 1 . 2>&1 | tee "$OUT/trivy.txt"; rc=${PIPESTATUS[0]}
  [[ $rc -ne 0 ]] && found=1
else missing trivy "Optional. Install: see docs/SECURITY.md (Dependency scanning)."; fi

section "summary"
echo "Reports saved in $OUT/"
if [[ $found -eq 1 ]]; then
  echo "At least one scanner reported something. Read the reports, then record each item in docs/SECURITY_ASSESSMENT.md (fixed, accepted, or not applicable, and why)."
  [[ $STRICT -eq 1 ]] && exit 1
else
  echo "No known issues matched. That is not proof of security: scanners only know published problems."
fi
exit 0
