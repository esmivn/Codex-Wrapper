#!/usr/bin/env bash
set -euo pipefail

IMAGE="${1:-codex-sandbox-poc:debian}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK_DIR="${ROOT_DIR}/workspace"

mkdir -p "${WORK_DIR}"

run_case() {
  local label="$1"
  shift
  echo
  echo "=== ${label} ==="
  docker run --rm \
    -v "${WORK_DIR}:/workspace" \
    "$@" \
    "${IMAGE}" || true
}

run_case "baseline"
run_case "seccomp-unconfined" --security-opt seccomp=unconfined
run_case "privileged" --privileged

cat <<'EOF'

Interpretation:
- baseline fails, seccomp-unconfined succeeds:
  default Docker seccomp/profile is likely the blocker.
- baseline and seccomp-unconfined fail, privileged succeeds:
  namespace/capability restrictions are still blocking sandbox setup.
- all variants fail:
  the issue is likely not just Docker runtime flags.
EOF
