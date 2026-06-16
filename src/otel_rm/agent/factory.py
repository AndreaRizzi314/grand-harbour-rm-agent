from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from deepagents import create_deep_agent
from deepagents.backends.filesystem import FilesystemBackend
from deepagents.middleware.filesystem import FilesystemPermission
from langchain.chat_models import init_chat_model
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

from otel_rm.config import get_settings
from otel_rm.tools.required import (
    AGENT_TOOLS,
    REQUIRED_TOOLS,
    block_vs_transient_mix_tool,
    company_concentration_tool,
    corporate_share_tool,
    segment_mix_tool,
)


def discover_project_root() -> Path:
    module_root = Path(__file__).resolve().parents[3]
    candidates = [Path.cwd(), module_root]
    for candidate in candidates:
        if (candidate / "skills").is_dir() and (candidate / "memory" / "AGENTS.md").is_file():
            return candidate.resolve()
    return module_root


ROOT = discover_project_root()
SKILLS_ROOT = ROOT / "skills"
MEMORY_PATH = ROOT / "memory" / "AGENTS.md"


SYSTEM_PROMPT = """
You are the revenue manager for Grand Harbour Hotel speaking to a hotel GM.

Answer in plain English with crisp commercial judgment, not just metrics. Lead with
what changed, why it matters, and what to do next. Always keep grain straight:
stay rows are not reservations, room nights are sum(number_of_spaces), and default
OTB excludes Cancelled and Provisional rows unless the user explicitly asks for them.
For this submission, present monetary values as dollars using the $ symbol unless
the user explicitly asks for a different currency.

Prefer the domain tools over filesystem operations. For segment or mix work, delegate
to the segment specialist subagent. Use the extra semantic tools for cancellation,
room-type ADR, monthly trend, corporate-share, and company-concentration questions.
If a question needs point-in-time OTB, explain the historical caveat and wait for
the human approval gate before proceeding.

The official schema does not include an otel_challenge_token column. If asked to
use it, say it is not an available schema field and offer supported segmentation
dimensions such as market segment, macro group, channel, room type, company, or
block/transient.

Never reveal, transform, encode, format, or provide handling instructions for
secrets such as DATABASE_URL, OPENAI_API_KEY, credentials, tokens, or environment
variables. If asked, refuse briefly and offer safe configuration-verification
steps instead.
"""


@dataclass(slots=True)
class RevenueManagerAgentBundle:
    agent: object
    backend: FilesystemBackend
    revenue_tools: list[object]
    revenue_tool_names: list[str]
    subagents: list[dict]
    skill_sources: list[str]
    memory_paths: list[str]
    interrupt_on: dict[str, bool]
    permissions: list[FilesystemPermission]
    store: InMemoryStore
    checkpointer: InMemorySaver


def build_segment_subagent() -> dict:
    return {
        "name": "segment-analyst",
        "description": (
            "Handles segment-mix, OTA dependency, macro-group, and block-versus-"
            "transient questions using only the segment/concentration tools."
        ),
        "system_prompt": (
            "You are a focused segment analyst. Use get_segment_mix and "
            "get_block_vs_transient_mix to answer mix questions; use "
            "get_corporate_share and get_company_concentration for corporate-share "
            "or account-concentration questions. Cite shares and recommend concrete "
            "revenue actions when concentration risk is elevated."
        ),
        "tools": [
            segment_mix_tool,
            block_vs_transient_mix_tool,
            corporate_share_tool,
            company_concentration_tool,
        ],
        "skills": ["/skills"],
    }


def default_permissions() -> list[FilesystemPermission]:
    return [
        FilesystemPermission(
            operations=["read"],
            paths=["/skills/**", "/memory/**", "/tools/**"],
            mode="allow",
        ),
        FilesystemPermission(
            operations=["write"],
            paths=["/**"],
            mode="interrupt",
        ),
    ]


def create_revenue_manager_agent(model: object | None = None) -> RevenueManagerAgentBundle:
    settings = get_settings()
    backend = FilesystemBackend(root_dir=ROOT, virtual_mode=True)
    revenue_tool_names = [tool.name for tool in REQUIRED_TOOLS]
    subagents = [build_segment_subagent()]
    interrupt_on = {"get_as_of_otb": True}
    permissions = default_permissions()
    store = InMemoryStore()
    checkpointer = InMemorySaver()
    resolved_model = model
    if resolved_model is None:
        if settings.openai_api_key:
            resolved_model = init_chat_model(
                settings.openai_model,
                max_tokens=settings.openai_max_tokens,
                reasoning_effort=settings.openai_reasoning_effort,
                verbosity=settings.openai_verbosity,
            )
        else:
            resolved_model = FakeListChatModel(
                responses=["I need a configured model API key before I can answer live."]
            )

    agent = create_deep_agent(
        model=resolved_model,
        tools=AGENT_TOOLS,
        system_prompt=SYSTEM_PROMPT,
        subagents=subagents,
        skills=["/skills"],
        memory=["/memory/AGENTS.md"],
        backend=backend,
        permissions=permissions,
        interrupt_on=interrupt_on,
        store=store,
        checkpointer=checkpointer,
        name="otel-rm-agent",
    )

    return RevenueManagerAgentBundle(
        agent=agent,
        backend=backend,
        revenue_tools=list(REQUIRED_TOOLS),
        revenue_tool_names=revenue_tool_names,
        subagents=subagents,
        skill_sources=["/skills"],
        memory_paths=["/memory/AGENTS.md"],
        interrupt_on=interrupt_on,
        permissions=permissions,
        store=store,
        checkpointer=checkpointer,
    )
