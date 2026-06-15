# ARCHITECTURE.md

## 1. ETL boundary

- **Extract:** `scripts/run_etl.py` uses Playwright to paginate the rendered reservation list at 100 reservations per page, opens every detail page, and also scrapes `/reference` and `/verify`.
- **Transform:** rows are enforced at `reservation_id x stay_date` grain, typed into ETL models, and lookup/reference tables are loaded before facts.
- **Load:** Postgres is loaded idempotently with truncate-and-reload plus a `load_manifest` row hash.
- **Verify:** `etl/LOAD_PROOF.json` records row counts, hashes, anchor date, and aggregates that reconcile to `/verify`; final anchor date is `2026-06-15`.

## 2. Database and views

- Hosted Postgres provider: Neon.
- `sql/VIEWS.sql` sits between tools and raw tables. It creates `vw_stay_night_history`, `vw_stay_night_base` for posted non-cancelled OTB, and `vw_segment_stay_night` for segment analysis.

## 3. Tool layer

- Five required tools: `get_otb_summary` uses `vw_stay_night_base`/history; `get_segment_mix` uses `vw_segment_stay_night`; `get_pickup_delta` uses `vw_segment_stay_night`; `get_as_of_otb` uses `vw_stay_night_history`; `get_block_vs_transient_mix` uses `vw_stay_night_base`.
- Defaults: OTB excludes `reservation_status = 'Cancelled'` and `financial_status = 'Provisional'`; provisional/cancelled rows require explicit caveats.
- Arbitrary SQL is not exposed because grain, date-basis, cancellation, and revenue-field rules must stay inside semantic tools.
- Grain definitions live in `tools/METRIC_DEFINITIONS.md`.

## 4. Deep Agents wiring

| Building block | Your use |
|---|---|
| Tools | Five required tools plus additive semantic helpers; no `run_sql` |
| Skills | 7 `SKILL.md` files with progressive disclosure |
| Subagents | `segment-analyst` handles segment, block/transient, corporate-share, and concentration work |
| Planning | Multi-part GM prompts decompose into multiple tool calls and subagent tasks |
| Memory / filesystem | `/memory/AGENTS.md`, filesystem backend, store, and checkpointer |
| Human-in-the-loop | `get_as_of_otb` is behind `interrupt_on` approval |
| Model & system prompt | GPT-5 via env key, revenue-manager persona, concise commercial answers |

## 5. Skill to tool routing matrix

| Skill | Primary tool(s) | Judgment? |
|---|---|---|
| `otb-summary-triage` | `get_otb_summary` | Y |
| `pickup-pace-diagnosis` | `get_pickup_delta` | Y |
| `ota-dependency-check` | `get_segment_mix` | Y |
| `block-concentration-review` | `get_block_vs_transient_mix` | Y |
| `asof-snapshot-guardrail` | `get_as_of_otb` | Y |
| `macro-shift-segmentation` | `get_segment_mix` | Y |
| `grain-and-date-guardrails` | `get_otb_summary`, `get_segment_mix` | Y |

## 6. Agent tests

- `tests/test_agent.py` asserts the required tool surface, no `run_sql`, HITL on `get_as_of_otb`, segment subagent routing, filesystem skill loading, memory, and multi-tool trace.
- `tests/test_skills.py` validates skill frontmatter, unique routing, topic coverage, guardrails, and at least 3 judgment skills with thresholds/actions.

## 7. Deployment topology

- Render hosts the FastAPI agent backend and packaged custom streaming UI; Neon hosts Postgres.
- `/ready` is public for Render; `/`, `/health`, `/api/chat`, and `/api/chat/stream` use basic auth.
- `/health` returns `db_fingerprint`, `dataset_revision`, `row_hash`, `financial_status_posted_only_rows`, and `status`.
- `DATABASE_URL`, `OPENAI_API_KEY`, auth credentials, and model settings live in Render environment variables, never in git.

## 8. Out of scope

- I did not expose arbitrary SQL or a schema-browsing SQL agent; the submission intentionally favors a semantic tool layer.
