# Grand Harbour Revenue Manager Agent

## Repo structure

- `src/otel_rm/etl`: scraper, models, load logic
- `src/otel_rm/tools`: required tool layer plus semantic helpers for room type ADR, cancellations, OTB trend, corporate share, and company concentration
- `src/otel_rm/agent`: Deep Agents factory and health payload
- `skills/`: on-demand skill pack
- `memory/AGENTS.md`: long term operating memory
- `src/otel_rm/web/index.html`: packaged streaming UI shell
- `scripts/run_etl.py`: scrape and load command
- `scripts/compute_load_fingerprint.py`: `LOAD_PROOF` generator
- `render.yaml`: Render deployment configuration

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

Set the Python version to `3.12.13`. The repo includes `.python-version`, and Render also supports setting `PYTHON_VERSION=3.12.13` as an environment variable.

Build command:

```bash
python -m pip install --upgrade pip setuptools wheel && python -m pip install .
```

Start command:

```bash
uvicorn otel_rm.api:app --host 0.0.0.0 --port $PORT
```

## Current verified load

- Scrape date: `2026-06-15`
- `reservation_ids_count`: `254`
- `pages_scraped`: `3`
- `loaded_stay_rows`: `516`
- `posted_stay_rows`: `258`
- `dataset_revision`: `2026.06.12.2`
- `reservation_stay_status_sha256`: `e98695ff7148e8579b26ed482597c2e06d59d724056a4dcb8b2a23823819ebb8`
