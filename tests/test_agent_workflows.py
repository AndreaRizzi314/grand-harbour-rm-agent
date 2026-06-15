from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from otel_rm.agent.factory import create_revenue_manager_agent
from otel_rm.agent.workflows import WORKFLOWS, AgentWorkflow
from otel_rm.api import app
from otel_rm.tools.required import (
    get_as_of_otb,
    get_block_vs_transient_mix,
    get_otb_summary,
    get_pickup_delta,
    get_segment_mix,
)


ROOT = Path(__file__).resolve().parents[1]
TOOL_FUNCTIONS = {
    "get_otb_summary": get_otb_summary,
    "get_segment_mix": get_segment_mix,
    "get_pickup_delta": get_pickup_delta,
    "get_as_of_otb": get_as_of_otb,
    "get_block_vs_transient_mix": get_block_vs_transient_mix,
}


def skill_names() -> set[str]:
    return {path.parent.name for path in (ROOT / "skills").glob("*/SKILL.md")}


def test_workflow_suite_is_comprehensive():
    ids = [workflow.id for workflow in WORKFLOWS]
    assert len(WORKFLOWS) >= 10
    assert len(ids) == len(set(ids))
    assert {workflow.kind for workflow in WORKFLOWS} >= {
        "tool",
        "subagent",
        "hitl",
        "guardrail",
        "api",
    }
    assert all(workflow.acceptance_checks for workflow in WORKFLOWS)


def test_workflow_skills_exist_and_no_raw_sql_tool_is_introduced():
    existing_skills = skill_names()
    for workflow in WORKFLOWS:
        assert set(workflow.expected_skills).issubset(existing_skills)
        assert "run_sql" not in [tool.name for tool in workflow.expected_tools]
        assert "run_sql" not in workflow.forbidden_tools or "run_sql" in workflow.forbidden_tools


def test_subagent_workflows_route_to_segment_specialist():
    bundle = create_revenue_manager_agent()
    subagent_names = {subagent["name"] for subagent in bundle.subagents}
    for workflow in WORKFLOWS:
        if workflow.kind == "subagent":
            assert workflow.expected_subagent == "segment-analyst"
            assert workflow.expected_subagent in subagent_names


def test_hitl_workflow_gates_as_of_otb():
    bundle = create_revenue_manager_agent()
    hitl_workflows = [workflow for workflow in WORKFLOWS if workflow.requires_human_approval]
    assert hitl_workflows
    for workflow in hitl_workflows:
        assert any(tool.name == "get_as_of_otb" for tool in workflow.expected_tools)
        assert bundle.interrupt_on.get("get_as_of_otb") is True


def test_tool_workflows_execute_expected_tools():
    executable = [
        workflow
        for workflow in WORKFLOWS
        if workflow.kind in {"tool", "subagent", "hitl"}
    ]
    for workflow in executable:
        for invocation in workflow.expected_tools:
            result = TOOL_FUNCTIONS[invocation.name](**invocation.args)
            assert isinstance(result, dict)
            assert result
            assert "grain" in result or invocation.name == "get_segment_mix"


def test_monthly_otb_workflow_acceptance():
    workflow = workflow_by_id_for_test("monthly-otb-summary")
    result = run_first_tool(workflow)
    assert result["row_count"] >= result["reservation_count"]
    assert result["room_nights"] >= result["reservation_count"]
    assert result["room_revenue"] <= result["total_revenue"]
    assert result["exclude_cancelled"] is True


def test_composite_workflow_uses_multiple_distinct_tools():
    workflow = workflow_by_id_for_test("july-drivers-and-pickup")
    tool_names = [invocation.name for invocation in workflow.expected_tools]
    assert len(set(tool_names)) >= 3
    for invocation in workflow.expected_tools:
        assert TOOL_FUNCTIONS[invocation.name](**invocation.args)


def test_ota_dependency_workflow_has_ota_segment():
    workflow = workflow_by_id_for_test("ota-dependency")
    result = run_first_tool(workflow)
    ota = next(
        (segment for segment in result["segments"] if segment["market_code"] == "OTA"),
        None,
    )
    assert ota is not None
    assert 0.0 < ota["share_of_revenue"] < 1.0


def test_block_concentration_workflow_reconciles_mix():
    workflow = workflow_by_id_for_test("block-concentration")
    mix = run_first_tool(workflow)
    summary = get_otb_summary("2026-09")
    assert mix["block_room_nights"] + mix["transient_room_nights"] == summary["room_nights"]
    assert mix["top3_company_revenue_share"] <= 1.0
    assert mix["top_companies"] == sorted(
        mix["top_companies"],
        key=lambda item: item["total_revenue"],
        reverse=True,
    )


def test_guardrail_workflows_have_forbidden_sql_and_default_otb_policy():
    for workflow_id in ["cancelled-provisional-adversarial", "property-date-trap"]:
        workflow = workflow_by_id_for_test(workflow_id)
        assert "run_sql" in workflow.forbidden_tools
        result = run_first_tool(workflow)
        assert result["exclude_cancelled"] is True


def test_health_workflow_reconciles_load_proof(load_proof):
    client = TestClient(app)
    ready_response = client.get("/ready")
    assert ready_response.status_code == 200
    assert ready_response.json() == {"status": "ready"}

    response = client.get("/health", auth=("gm", "change-me"))
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["db_fingerprint"] == load_proof["reservation_stay_status_sha256"]
    assert payload["dataset_revision"] == load_proof["dataset_revision"]
    assert payload["row_hash"] == load_proof["load_manifest_row_hash"]
    assert (
        payload["financial_status_posted_only_rows"]
        == load_proof["aggregates"]["posted_stay_rows"]
    )


def workflow_by_id_for_test(workflow_id: str) -> AgentWorkflow:
    for workflow in WORKFLOWS:
        if workflow.id == workflow_id:
            return workflow
    raise AssertionError(f"Missing workflow {workflow_id}")


def run_first_tool(workflow: AgentWorkflow) -> dict:
    invocation = workflow.expected_tools[0]
    return TOOL_FUNCTIONS[invocation.name](**invocation.args)
