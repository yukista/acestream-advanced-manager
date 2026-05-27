# AI Prompt Context

This file is optimized to give future AI prompts clear project context quickly.

## What this repository is

A multi-service Ace Stream monitoring stack:

- health-checker API: probes hashes and produces short clips
- backend API: stores channels, schedules checks, serves channel state
- frontend app: channel management and playback UI
- MariaDB: channel persistence

## Source of truth files

- Health-checker: `app/main.py`
- Backend: `backend/app/main.py`
- Frontend entry: `frontend/src/App.jsx`
- Compose orchestration: `docker-compose.yml`

## Runtime architecture

- Frontend talks to backend on `:8001`
- Backend talks to one or more health-checkers on `:8000` containers
- Backend persists to MariaDB
- Health-checker runs Ace Stream engine + FastAPI in one container

## Common commands

Start all services:

```powershell
docker compose -f docker-compose.yml up -d --build
```

Stop all services:

```powershell
docker compose -f docker-compose.yml down
```

Import channels from clashsports data:

```powershell
./import_channels.ps1
```

## Current cleanup decisions

- Removed legacy duplicate PowerShell import/test scripts.
- Kept one canonical importer: `import_channels.ps1`.
- Removed benchmark and probe result artifacts committed in repo.

## Prompt templates for future AI work

### 1) Safe cleanup

"Review this repo and propose a safe cleanup. Only remove files that are unreferenced by runtime or docs. Show a delete list first, then apply changes, then update README."

### 2) Backend change

"Implement this backend change in `backend/app/main.py`, keep API compatibility, and run a quick validation of imports and obvious syntax issues."

### 3) Frontend bugfix

"Fix this issue in `frontend/src/App.jsx` and related components. Keep existing UX patterns. Summarize changed files and behavior impact."

### 4) Ops check

"Audit `docker-compose.yml`, Dockerfiles, and env vars for production risks. Prioritize reliability and startup order issues."

### 5) Data import improvements

"Improve `import_channels.ps1` with idempotency, better logging, and clear exit codes. Keep compatibility with backend `POST /channels`."

## Rules for future prompts

- Do not delete runtime files (`app`, `backend`, `frontend`, Dockerfiles, compose) without explicit confirmation.
- Prefer minimal diffs and preserve existing API contracts.
- If unsure whether a file is used, search references first and ask before deleting.
