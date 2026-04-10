#!/usr/bin/env bash
set -euo pipefail

echo "== identity =="
id
echo

echo "== tools =="
command -v codex
command -v bwrap
codex --version || true
bwrap --version || true
echo

echo "== kernel hints =="
uname -a
if command -v sysctl >/dev/null 2>&1; then
  sysctl kernel.unprivileged_userns_clone 2>/dev/null || true
fi
echo

echo "== codex sandbox help =="
codex sandbox linux --help | sed -n '1,20p'
echo

mkdir -p /workspace/probe
cd /workspace/probe

echo "== sandbox execution probe =="
if codex sandbox linux --full-auto sh -lc '
  set -e
  pwd
  touch sandbox-ok
  touch /tmp/sandbox-tmp-ok
  if touch /etc/codex-sandbox-should-fail 2>/dev/null; then
    echo system_write_unexpected
    exit 1
  fi
  echo workspace_write_ok
  echo tmp_write_ok
  echo system_write_blocked
'; then
  echo
  echo "sandbox_probe=success"
  exit 0
fi

echo
echo "sandbox_probe=failed"
exit 1
