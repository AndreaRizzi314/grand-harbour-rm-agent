# ARCHITECTURE.md

## 1. ETL boundary

- **Extract:** `ReservationScraper.scrape_reservation_index()` opens `/reservations`, waits for table rows, parses each row's detail link, then clicks `data-testid="next-page"` until it is disabled. Each detail URL is opened in a new Playwright page; `RESERVATION FIELDS` are parsed into reservation level fields and the first table is parsed into stay rows. `/reference` tabs and `/verify` are scraped in the same run.
- **Transform:** detail page stay rows become typed `ReservationRecord` objects at `reservation_id x stay_date` grain. Reference tabs become lookup rows. Raw commercial rate plan strings are canonicalized before the load.
- **Load:** `load_dataset()` prepares schema, truncates fact/lookup/manifest tables, inserts lookups then stay rows, and writes `load_manifest(dataset_revision, scraped_at, source_url, row_hash)`.
- **Verify:** `SCRAPE_MANIFEST.json` stores page count, reservation ID count, and ID hash; `LOAD_PROOF.json` stores DB row counts, aggregates, `/verify` values, and manifest validation. Final run scraped 3 pages / 254 reservations / 516 stay rows with anchor date `2026-06-15`.

## 2. Database and views

- Hosted Postgres provider: Neon.
- `sql/VIEWS.sql` sits between tools and raw tables. It creates `vw_stay_night_history`, `vw_stay_night_base` for posted non-cancelled OTB, and `vw_segment_stay_night` for segment analysis.

## 3. Tool layer

- Five required tools: `get_otb_summary(stay_month, exclude_cancelled)` uses current base/history; `get_segment_mix(stay_month, macro_group)` uses effective macro groups; `get_pickup_delta(booking_window_days, future_stay_from)` uses `create_datetime`; `get_as_of_otb(stay_month, as_of_utc)` reconstructs historical OTB; `get_block_vs_transient_mix(stay_month)` uses `is_block`.
- Defaults: current OTB uses `vw_stay_night_base`, so `reservation_status = 'Cancelled'` and `financial_status = 'Provisional'` are excluded; provisional/cancelled rows require explicit caveats.
- Arbitrary SQL is not exposed because grain, date-basis, cancellation, and revenue field rules must stay inside semantic tools.
- Grain definitions live in `tools/METRIC_DEFINITIONS.md`.

## 4. Deep Agents wiring

| Building block | Implementation |
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

- `tests/test_agent.py` asserts the exact five required tool names, no `run_sql`, HITL on `get_as_of_otb`, segment subagent routing, filesystem skill loading, memory, and multi-tool trace.
- `tests/test_skills.py` validates skill frontmatter, unique routing, topic coverage, adversarial guardrails, and at least 3 judgment skills with thresholds/actions.
- `tests/test_tools.py` runs against loaded Postgres and checks grain, cancellations/provisional exclusions, pickup windows, as-of snapshots, property date traps, block reconciliation, and extra semantic helpers.

## 7. Deployment topology

- Render hosts the FastAPI agent backend and packaged custom streaming UI. Neon hosts Postgres.
- `/ready` is public for Render; `/`, `/health`, `/api/chat`, and `/api/chat/stream` use basic auth.
- `/health` returns `db_fingerprint`, `dataset_revision`, `row_hash`, `financial_status_posted_only_rows`, and `status`.
- `DATABASE_URL`, `OPENAI_API_KEY`, auth credentials, and model settings live in Render environment variables, never in git.

## 8. Out of scope

- I did not expose arbitrary SQL or a schema browsing SQL agent. I am intentionally favoring a semantic tool layer.
