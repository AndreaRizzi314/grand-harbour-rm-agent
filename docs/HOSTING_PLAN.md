# Hosting Plan

Use a two-service deployment:

- Hosted Postgres on Neon or Supabase
- FastAPI agent backend plus UI on Render or Railway

The UI is served by the backend at `/`, so there is no separate frontend deployment.

## Recommended Path

Use Neon Postgres for the database and Render Web Service for the app.

Render should run:

```bash
uvicorn otel_rm.api:app --host 0.0.0.0 --port $PORT
```

The repository includes `render.yaml`, `Procfile`, and `runtime.txt` so Render can
deploy the app directly after the GitHub repo is connected.

## Environment Variables

Set these privately in the deployment platform:

```text
DATABASE_URL=<hosted postgres url>
OPENAI_API_KEY=<private model key>
OPENAI_MODEL=openai:gpt-5
BASIC_AUTH_USERNAME=<submission username>
BASIC_AUTH_PASSWORD=<strong submission password>
```

Do not commit real credentials. `.env.example` should remain blank for secrets.

## Day-Of-Submission Data Refresh

The data site is anchor-date dependent. On the actual submission day:

1. Point local `DATABASE_URL` at the hosted Postgres database.
2. Re-run ETL against the live data site.
3. Regenerate `etl/SCRAPE_MANIFEST.json` and `etl/LOAD_PROOF.json`.
4. Re-run tests.
5. Push the updated proof artifacts before final submission.

PowerShell example:

```powershell
$env:DATABASE_URL="postgresql://..."
.\.venv\Scripts\python.exe scripts\run_etl.py
.\.venv\Scripts\python.exe scripts\compute_load_fingerprint.py --manifest etl\SCRAPE_MANIFEST.json --output etl\LOAD_PROOF.json
.\.venv\Scripts\python.exe -m pytest
```

## Verification Checklist

Before submitting:

- `/health` returns `status = ok`
- `/ready` returns `status = ready` without auth for platform health checks
- `/health` `db_fingerprint` matches `etl/LOAD_PROOF.json` `reservation_stay_status_sha256`
- `/health` `dataset_revision` matches `etl/LOAD_PROOF.json`
- `/health` `row_hash` matches `etl/LOAD_PROOF.json` `load_manifest_row_hash`
- `/health` `financial_status_posted_only_rows` matches `etl/LOAD_PROOF.json` `aggregates.posted_stay_rows`
- `/` loads behind basic auth
- A real GM question streams tool and skill events
- Live app is expected to remain available for at least 7 days after submission

## Submission Payload

Send privately through the intake channel:

- Solution repo URL
- Live agent URL
- Basic-auth username and password

Never include model API keys or database credentials in the submission message or repository.
