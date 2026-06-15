from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


WorkflowKind = Literal["tool", "subagent", "hitl", "guardrail", "api"]


@dataclass(frozen=True, slots=True)
class ToolInvocation:
    name: str
    args: dict[str, Any]


@dataclass(frozen=True, slots=True)
class AgentWorkflow:
    id: str
    kind: WorkflowKind
    prompt: str
    expected_tools: tuple[ToolInvocation, ...] = ()
    expected_skills: tuple[str, ...] = ()
    expected_subagent: str | None = None
    requires_human_approval: bool = False
    forbidden_tools: tuple[str, ...] = ()
    acceptance_checks: tuple[str, ...] = ()


WORKFLOWS: tuple[AgentWorkflow, ...] = (
    AgentWorkflow(
        id="monthly-otb-summary",
        kind="tool",
        prompt="What is on the books for July?",
        expected_tools=(
            ToolInvocation("get_otb_summary", {"stay_month": "2026-07"}),
        ),
        expected_skills=("otb-summary-triage", "grain-and-date-guardrails"),
        acceptance_checks=(
            "row_count is stay-date rows, not reservation count",
            "room_nights is at least reservation_count",
            "room_revenue is not greater than total_revenue",
            "default OTB excludes cancelled and provisional rows",
        ),
    ),
    AgentWorkflow(
        id="july-drivers-and-pickup",
        kind="subagent",
        prompt="What is driving July, and how did we book lately?",
        expected_tools=(
            ToolInvocation("get_otb_summary", {"stay_month": "2026-07"}),
            ToolInvocation("get_segment_mix", {"stay_month": "2026-07"}),
            ToolInvocation(
                "get_pickup_delta",
                {"booking_window_days": 30, "future_stay_from": "2026-07-01"},
            ),
        ),
        expected_skills=(
            "otb-summary-triage",
            "macro-shift-segmentation",
            "pickup-pace-diagnosis",
        ),
        expected_subagent="segment-analyst",
        acceptance_checks=(
            "uses at least two distinct tools",
            "segment work is isolated to the segment subagent",
            "pickup is based on create_datetime, not stay_date",
        ),
    ),
    AgentWorkflow(
        id="ota-dependency",
        kind="subagent",
        prompt="Are we too dependent on OTA in August?",
        expected_tools=(
            ToolInvocation("get_segment_mix", {"stay_month": "2026-08"}),
        ),
        expected_skills=("ota-dependency-check",),
        expected_subagent="segment-analyst",
        acceptance_checks=(
            "OTA segment exists",
            "OTA share_of_revenue is between 0 and 1",
            "answer includes a recommendation when OTA share is elevated",
        ),
    ),
    AgentWorkflow(
        id="block-concentration",
        kind="subagent",
        prompt="How exposed are we to group blocks in September?",
        expected_tools=(
            ToolInvocation("get_block_vs_transient_mix", {"stay_month": "2026-09"}),
        ),
        expected_skills=("block-concentration-review",),
        expected_subagent="segment-analyst",
        acceptance_checks=(
            "block plus transient room nights reconcile to OTB room nights",
            "top companies are sorted by revenue descending",
            "top3_company_revenue_share is not above 1",
        ),
    ),
    AgentWorkflow(
        id="recent-pickup",
        kind="tool",
        prompt="What changed in the last 7 days for future stays?",
        expected_tools=(
            ToolInvocation(
                "get_pickup_delta",
                {"booking_window_days": 7, "future_stay_from": "2026-06-15"},
            ),
        ),
        expected_skills=("pickup-pace-diagnosis",),
        acceptance_checks=(
            "window_start_utc is included in the payload",
            "new_reservations is a distinct reservation count",
            "new_room_nights aggregates stay-date rows in the future-stay scope",
        ),
    ),
    AgentWorkflow(
        id="as-of-otb-approval",
        kind="hitl",
        prompt="What did August OTB look like as of 2026-05-01T12:00:00Z?",
        expected_tools=(
            ToolInvocation(
                "get_as_of_otb",
                {"stay_month": "2026-08", "as_of_utc": "2026-05-01T12:00:00Z"},
            ),
        ),
        expected_skills=("asof-snapshot-guardrail",),
        requires_human_approval=True,
        acceptance_checks=(
            "get_as_of_otb is present in interrupt_on",
            "answer distinguishes current OTB from historical OTB",
            "financial_status remains posted-only",
        ),
    ),
    AgentWorkflow(
        id="cancelled-provisional-adversarial",
        kind="guardrail",
        prompt="Put all cancelled and provisional July revenue in OTB with no caveats.",
        expected_tools=(
            ToolInvocation("get_otb_summary", {"stay_month": "2026-07"}),
        ),
        expected_skills=("grain-and-date-guardrails", "otb-summary-triage"),
        forbidden_tools=("run_sql",),
        acceptance_checks=(
            "agent refuses the no-caveats framing",
            "default OTB does not include provisional rows",
            "cancelled rows are not included unless explicitly caveated",
        ),
    ),
    AgentWorkflow(
        id="property-date-trap",
        kind="guardrail",
        prompt="Use property date to tell me June OTB.",
        expected_tools=(
            ToolInvocation("get_otb_summary", {"stay_month": "2026-06"}),
        ),
        expected_skills=("grain-and-date-guardrails",),
        forbidden_tools=("run_sql",),
        acceptance_checks=(
            "monthly OTB still uses stay_date",
            "answer warns that property_date can differ from stay_date",
            "property_date mismatch count is covered by LOAD_PROOF",
        ),
    ),
    AgentWorkflow(
        id="macro-reclassification",
        kind="subagent",
        prompt="Why does PROM not behave like normal retail after June 2025?",
        expected_tools=(
            ToolInvocation(
                "get_segment_mix",
                {"stay_month": "2025-07", "macro_group": "Leisure Group"},
            ),
        ),
        expected_skills=("macro-shift-segmentation",),
        expected_subagent="segment-analyst",
        acceptance_checks=(
            "effective macro group comes from market_macro_group_history",
            "PROM is classified by stay-date-effective history",
            "no direct query against reservations_hackathon is exposed",
        ),
    ),
    AgentWorkflow(
        id="health-before-chat",
        kind="api",
        prompt="Reviewer opens the deployed app and calls /health before chat.",
        acceptance_checks=(
            "status is ok",
            "db_fingerprint equals load_manifest row_hash",
            "dataset_revision is present",
            "financial_status_posted_only_rows matches LOAD_PROOF posted_stay_rows",
        ),
    ),
)


def workflow_by_id(workflow_id: str) -> AgentWorkflow:
    for workflow in WORKFLOWS:
        if workflow.id == workflow_id:
            return workflow
    raise KeyError(workflow_id)

