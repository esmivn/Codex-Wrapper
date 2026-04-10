# Sandbox PoC

This directory is for testing whether Codex Linux sandboxing can run inside a
containerized Codex Wrapper deployment.

## Goal

Validate a deployment that can:

- run Codex with Linux sandboxing enabled
- keep file access limited to a single workspace root
- avoid weakening the container boundary more than necessary

## Current Findings

- The current runtime image is based on `python:3.11-slim`.
- The current service defaults to `danger-full-access`.
- The current remote container does not successfully run `codex sandbox linux`.
- The observed failure is:

```text
bwrap: No permissions to create a new namespace
```

This suggests the blocker is not only the base image. The effective runtime
permissions and namespace/seccomp configuration also matter.

## PoC Direction

The experiment should answer these questions:

1. Does installing `bubblewrap` inside the image change anything by itself?
2. Which Docker runtime options are required for `codex sandbox linux` to work?
3. Can we keep a strong container boundary while still allowing Codex sandbox
   to initialize?
4. Is this approach better than per-user isolated containers?

## Expected Outputs

- one or more throwaway Dockerfiles or compose snippets
- a repeatable checklist for validating sandbox startup
- a recommendation on whether this path is worth adopting

## Files

- `Dockerfile.debian`: Debian Bookworm PoC image with `bubblewrap`
- `Dockerfile.ubuntu`: Ubuntu 24.04 PoC image with `bubblewrap`
- `verify-sandbox.sh`: runs a small sandbox capability check inside the container
- `run-matrix.sh`: launches a few runtime variants to compare behavior

## Quick Start

Build one image:

```bash
docker build -f poc/sandbox/Dockerfile.debian -t codex-sandbox-poc:debian .
```

Or:

```bash
docker build -f poc/sandbox/Dockerfile.ubuntu -t codex-sandbox-poc:ubuntu .
```

Run the comparison matrix:

```bash
bash poc/sandbox/run-matrix.sh codex-sandbox-poc:debian
```

## What To Look For

The important transitions are:

1. `bwrap` is present inside the image.
2. `codex sandbox linux --help` works.
3. `codex sandbox linux --full-auto sh -lc 'echo ok'` succeeds.
4. The command can create files only in the mounted workspace.

If step 1 succeeds but step 3 still fails, the problem is likely in Docker
runtime permissions rather than the Linux distribution itself.

## Observed Result On This Machine

Using Docker Desktop on this machine, both PoC images behaved the same way:

- `baseline`: failed with `bwrap: No permissions to create new namespace`
- `--security-opt seccomp=unconfined`: succeeded
- `--privileged`: succeeded

This strongly suggests:

- the base image is not the main blocker
- Docker's default seccomp/runtime restrictions are the main blocker
- adding `bubblewrap` to the image is necessary, but not sufficient

At least on this setup, both of these images are viable candidates for running
Codex Linux sandboxing once the runtime is adjusted:

- `debian:bookworm-slim`
- `ubuntu:24.04`

The Ubuntu PoC was then tightened further to run as a non-root user. That
variant also worked with:

- `ubuntu:24.04`
- `bubblewrap` installed
- non-root user (`uid=1000`, `gid=1000`)
- `--security-opt seccomp=unconfined`

The probe confirmed:

- writes in `/workspace` succeeded
- writes in `/tmp` succeeded
- writes in `/etc` were blocked
