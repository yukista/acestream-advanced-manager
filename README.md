# Ace Stream Channel Health

Monorepo with:

- A health-checker service (FastAPI) that probes Ace Stream hashes and generates clips.
- A backend API (FastAPI + MariaDB) that stores channels and orchestrates checks.
- A frontend (React + Vite) to manage channels and playback.

## Services

- `health-checker` (`app/main.py`) on port `8000`
- `backend` (`backend/app/main.py`) on port `8001`
- `frontend` (`frontend`) on port `3001`
- `mariadb` for channel persistence

`docker-compose.yml` starts 8 health-checker instances plus backend, frontend, and database.

## Run with Docker

```powershell
docker compose -f docker-compose.yml up -d --build
```

Main URLs:

- Frontend: `http://localhost:3001`
- Backend docs: `http://localhost:8001/docs`
- Health-checker docs: `http://localhost:8000/docs`

## Import channels

Use the canonical importer script:

```powershell
./import_channels.ps1
```

Optional params:

```powershell
./import_channels.ps1 -SourceFile clashsports.json -BackendBaseUrl http://127.0.0.1:8001 -DelayMs 50
```

What it does:

- Reads `clashsports.json`
- Validates `acestream://` hashes (`40` hex chars)
- Deduplicates by hash
- Inserts into backend endpoint `POST /channels`

## Project notes

- Legacy one-off scripts and benchmark/result artifacts were removed in this cleanup.
- Keep temporary outputs out of the repo (store them in a local ignored folder).

## AI prompt guide

See `AI_PROMPT_CONTEXT.md` for a prompt-ready guide with architecture, commands, and recommended prompt templates for future AI sessions.
