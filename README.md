# Grand Harbour Revenue Manager Agent

Standalone solution repository for the OTel AI Build Challenge. This repository is intended to be the submission repo, not a fork of the brief.

## What is included

- Browser-based Playwright ETL that scrapes the live rendered data site
- Idempotent Postgres load with `load_manifest`
- Required semantic views in `sql/VIEWS.sql`
- All five required agent-facing tools with fixed business semantics
- Deep Agents harness with:
  - filesystem-backed skills
  - memory file
  - segment-mix subagent
  - HITL gate on `get_as_of_otb`
- Required artifacts:
  - `ATTESTATION.md`
  - `ARCHITECTURE.md`
  - `etl/SCRAPE_MANIFEST.json`
  - `etl/LOAD_PROOF.json`
  - `tools/METRIC_DEFINITIONS.md`
  - `tests/test_etl.py`
  - `tests/test_tools.py`
  - `tests/test_skills.py`
  - `tests/test_agent.py`

## Repo structure

- `src/otel_rm/etl`: scraper, models, load logic
- `src/otel_rm/tools`: required tool layer
- `src/otel_rm/agent`: Deep Agents factory and health payload
- `skills/`: on-demand skill pack
- `memory/AGENTS.md`: long-term operating memory
- `web/index.html`: minimal streaming UI shell
- `scripts/run_etl.py`: scrape and load command
- `scripts/compute_load_fingerprint.py`: `LOAD_PROOF` generator
- `docs/AGENT_WORKFLOWS.md`: reviewer-style workflow test matrix
- `docs/HOSTING_PLAN.md`: planned production hosting checklist
- `render.yaml`, `Procfile`, `runtime.txt`: Render deployment configuration

## Local setup

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
.\.venv\Scripts\python.exe -m pip install --no-build-isolation -e .[dev]
.\.venv\Scripts\python.exe -m playwright install chromium
Copy-Item .env.example .env
```

## Load the database

```powershell
docker compose up -d
.\.venv\Scripts\python.exe scripts\run_etl.py
.\.venv\Scripts\python.exe scripts\compute_load_fingerprint.py --manifest etl\SCRAPE_MANIFEST.json --output etl\LOAD_PROOF.json
```

## Run tests

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Run only the agent workflow suite:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_agent_workflows.py
```

## Run the app

Set `OPENAI_API_KEY` in `.env`, then start:

```powershell
.\.venv\Scripts\python.exe -m uvicorn otel_rm.api:app --host 0.0.0.0 --port 8000
```

The app is protected with HTTP basic auth from `.env`, streams tool and skill events from `/api/chat/stream`, and exposes `GET /health`.

## Render settings

Set the Python version to `3.12.13`. The repo includes both `runtime.txt` and `.python-version`, but Render also supports setting `PYTHON_VERSION=3.12.13` as an environment variable.

Build command:

```bash
python -m pip install --upgrade pip setuptools wheel && python -m pip install .
```

Start command:

```bash
uvicorn otel_rm.api:app --host 0.0.0.0 --port $PORT
```

## Current verified load

- Scrape date: `2026-06-14`
- `reservation_ids_count`: `254`
- `pages_scraped`: `3`
- `dataset_revision`: `2026.06.12.2`
- `reservation_stay_status_sha256`: `da950a13c377457604338e9823100d4d641b409937f7515d79c9a41081ddc1dd`

## Deployment notes

To satisfy the brief fully in production, deploy:

- a hosted Postgres loaded by this ETL
- the FastAPI app with `OPENAI_API_KEY`
- the web UI behind HTTP basic auth

The `/health` response is designed to match the brief fields:

- `db_fingerprint`
- `dataset_revision`
- `row_hash`
- `financial_status_posted_only_rows`
