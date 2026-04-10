#!/usr/bin/env bash
set -euo pipefail

REMOTE_TARGET="${1:-}"
REMOTE_DIR="${2:-\$HOME/codex-wrapper-deploy}"
IMAGE_TAG="${IMAGE_TAG:-codex-wrapper:sandbox-amd64}"

if [[ -z "${REMOTE_TARGET}" ]]; then
  echo "usage: $0 <ssh-target> [remote-dir]" >&2
  echo "example: $0 'ssh -i ~/.ssh/id_ed25519_aa3090 kaleo@10.0.0.7'" >&2
  exit 1
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "${ROOT_DIR}"

docker buildx build --platform linux/amd64 -t "${IMAGE_TAG}" --load .

eval "${REMOTE_TARGET} 'mkdir -p ${REMOTE_DIR}'"

tar -C "${ROOT_DIR}" -cf - deploy/remote/compose.yaml deploy/remote/.env.example \
  | eval "${REMOTE_TARGET} 'tar -xf - -C ${REMOTE_DIR}'"

docker save "${IMAGE_TAG}" | eval "${REMOTE_TARGET} 'sudo -n docker load'"

eval "${REMOTE_TARGET} 'cd ${REMOTE_DIR}/deploy/remote && sudo -n docker compose -f compose.yaml up -d'"
