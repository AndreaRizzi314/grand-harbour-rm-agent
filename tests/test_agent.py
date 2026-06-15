from __future__ import annotations

import json
from pathlib import Path

from otel_rm.agent.factory import create_revenue_manager_agent


ROOT = Path(__file__).resolve().parents[1]


def test_tool_surface_is_fixed():
    bundle = create_revenue_manager_agent()
    assert bundle.revenue_tool_names == [
        "get_otb_summary",
        "get_segment_mix",
        "get_pickup_delta",
        "get_as_of_otb",
        "get_block_vs_transient_mix",
    ]
    assert "run_sql" not in bundle.revenue_tool_names


def test_get_as_of_otb_is_human_gated():
    bundle = create_revenue_manager_agent()
    assert bundle.interrupt_on.get("get_as_of_otb") is True


def test_segment_work_is_isolated_to_subagent():
    bundle = create_revenue_manager_agent()
    subagent = bundle.subagents[0]
    assert subagent["name"] == "segment-analyst"
    assert {tool.name for tool in subagent["tools"]} == {
        "get_segment_mix",
        "get_block_vs_transient_mix",
    }


def test_composite_trace_shows_multi_tool_decomposition():
    fixture = json.loads((ROOT / "tests" / "fixtures" / "composite_trace.json").read_text(encoding="utf-8"))
    assert len(set(fixture["tool_calls"])) >= 2
    assert "get_otb_summary" in fixture["tool_calls"]
    assert "get_pickup_delta" in fixture["tool_calls"]


def test_skill_loading_is_on_demand():
    bundle = create_revenue_manager_agent()
    assert bundle.skill_sources == ["/skills"]
    assert (ROOT / "skills").is_dir()


def test_memory_or_filesystem_is_configured():
    bundle = create_revenue_manager_agent()
    assert bundle.memory_paths == ["/memory/AGENTS.md"]
    assert bundle.backend is not None
    assert bundle.store is not None

