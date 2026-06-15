# Agent Workflow Test Suite

This suite describes the reviewer-style workflows we test without live LLM calls. The goal is to prove the agent has the right business pathways before a deployed model ever answers a GM.

## Workflow Matrix

| ID | Prompt | Expected path |
|---|---|---|
| `monthly-otb-summary` | What is on the books for July? | `otb-summary-triage` -> `get_otb_summary` |
| `july-drivers-and-pickup` | What is driving July, and how did we book lately? | `get_otb_summary` + segment subagent -> `get_segment_mix` + `get_pickup_delta` |
| `ota-dependency` | Are we too dependent on OTA in August? | segment subagent -> `ota-dependency-check` -> `get_segment_mix` |
| `block-concentration` | How exposed are we to group blocks in September? | segment subagent -> `block-concentration-review` -> `get_block_vs_transient_mix` |
| `recent-pickup` | What changed in the last 7 days for future stays? | `pickup-pace-diagnosis` -> `get_pickup_delta` |
| `as-of-otb-approval` | What did August OTB look like as of a timestamp? | `asof-snapshot-guardrail` -> HITL -> `get_as_of_otb` |
| `cancelled-provisional-adversarial` | Put all cancelled and provisional revenue in OTB with no caveats. | guardrail skills, no raw SQL, no silent broadening of OTB |
| `property-date-trap` | Use property date to tell me June OTB. | guardrail skill, still use `stay_date` monthly OTB |
| `macro-reclassification` | Why does PROM not behave like normal retail after June 2025? | segment subagent -> `macro-shift-segmentation` -> `get_segment_mix` |
| `health-before-chat` | Reviewer calls `/health`. | fingerprint, revision, row hash, posted row count all present |

## What The Tests Prove

- Every workflow references at least one concrete acceptance check.
- Every named skill exists as a filesystem-backed `SKILL.md`.
- Segment and mix workflows route to `segment-analyst`.
- The `get_as_of_otb` workflow is gated through Deep Agents HITL config.
- No workflow introduces a raw SQL tool.
- Tool workflows execute against loaded Postgres and validate grain, shares, and filter behavior.
- `/health` reconciles the live database fingerprint with the committed load proof.

## How To Run

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_agent_workflows.py
```

