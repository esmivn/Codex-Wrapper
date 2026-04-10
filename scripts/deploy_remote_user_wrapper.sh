#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 4 || $# -gt 6 ]]; then
  echo "Usage: $0 <ssh-target> <user-id> <host-workspace-dir> <host-port> [image-name] [codex-auth-dir]" >&2
  exit 1
fi

SSH_TARGET="$1"
USER_ID="$2"
HOST_WORKSPACE_DIR="$3"
HOST_PORT="$4"
IMAGE_NAME="${5:-codex-wrapper:sandbox-amd64}"
CODEX_AUTH_DIR="${6:-\$HOME/.codex}"

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REMOTE_DIR="codex-wrapper-${USER_ID}-deploy"
TMP_ENV="$(mktemp)"
trap 'rm -f "$TMP_ENV"' EXIT

cat > "$TMP_ENV" <<EOF
USER_ID=${USER_ID}
HOST_PORT=${HOST_PORT}
USER_WORKSPACE_HOST_DIR=${HOST_WORKSPACE_DIR}
CODEX_AUTH_DIR=${CODEX_AUTH_DIR}
IMAGE_NAME=${IMAGE_NAME}
CODEX_APPROVAL_POLICY=never
CODEX_SANDBOX_MODE=workspace-write
CODEX_ALLOW_DANGER_FULL_ACCESS=0
EOF

ssh "$SSH_TARGET" "mkdir -p ~/${REMOTE_DIR}"
scp "$REPO_ROOT/deploy/user-isolated/compose.yaml" "$SSH_TARGET:~/${REMOTE_DIR}/compose.yaml"
scp "$TMP_ENV" "$SSH_TARGET:~/${REMOTE_DIR}/.env"
ssh "$SSH_TARGET" "mkdir -p '${HOST_WORKSPACE_DIR}' && cd ~/${REMOTE_DIR} && sudo -n docker compose -f compose.yaml up -d"
