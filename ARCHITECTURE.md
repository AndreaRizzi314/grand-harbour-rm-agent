# Revenue Manager Agent Architecture

## Flow

1. `scripts/run_etl.py` scrapes the rendered list, every reservation detail page, `/reference`, and `/verify` with Playwright.
2. The ETL canonicalizes raw commercial rate codes into the eight reference `rate_plan_lookup` rows, loads Postgres idempotently, and appends `load_manifest`.
3. `sql/VIEWS.sql` creates:
   - `vw_stay_night_history`: all stay rows plus stay-date-effective macro group
   - `vw_stay_night_base`: posted, non-cancelled default OTB universe
   - `vw_segment_stay_night`: current segment-analysis surface
4. `src/otel_rm/tools/required.py` exposes the five required tools with grain-safe SQL plus additive semantic tools for room-type ADR, cancellation analysis, monthly OTB trend, corporate share, and company concentration.
5. `src/otel_rm/agent/factory.py` builds a Deep Agent with:
   - revenue-manager system prompt
   - filesystem-backed skills from `/skills`
   - memory from `/memory/AGENTS.md`
   - `segment-analyst` subagent for mix work
   - HITL interrupt on `get_as_of_otb`

## Skill → Tool Routing

| Skill | Primary tool(s) | Notes |
|---|---|---|
| `otb-summary-triage` | `get_otb_summary` | Month framing, grain caveats |
| `pickup-pace-diagnosis` | `get_pickup_delta` | Booking-window logic and recent pace |
| `ota-dependency-check` | `get_segment_mix` | OTA concentration and retail mix |
| `block-concentration-review` | `get_block_vs_transient_mix` | Block share and top-company exposure |
| `asof-snapshot-guardrail` | `get_as_of_otb` | Historical snapshot + HITL |
| `macro-shift-segmentation` | `get_segment_mix` | Effective macro-group history |
| `grain-and-date-guardrails` | `get_otb_summary`, `get_segment_mix` | Trap prevention |

## Required Decisions

- Subagent: segment and mix questions are isolated to the `segment-analyst` subagent, which only receives `get_segment_mix` and `get_block_vs_transient_mix`.
- HITL: `get_as_of_otb` is explicitly gated through `interrupt_on={"get_as_of_otb": True}`.
- Memory/filesystem: Deep Agents loads `/memory/AGENTS.md`, stores thread state with a checkpointer, and uses a filesystem backend so skills are loaded progressively rather than stuffed into one prompt.
- No raw SQL tool: the model only receives the five business tools; SQL stays inside application code.
