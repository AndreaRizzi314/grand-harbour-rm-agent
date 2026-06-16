from __future__ import annotations

import json
from pathlib import Path
import secrets
from typing import Any
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sse_starlette.sse import EventSourceResponse

from otel_rm.agent.factory import create_revenue_manager_agent
from otel_rm.agent.health import current_health_payload
from otel_rm.config import get_settings


PACKAGE_ROOT = Path(__file__).resolve().parent
security = HTTPBasic()
app = FastAPI(title="Grand Harbour Revenue Manager Agent")


def model_required_message(question: str) -> str:
    try:
        health_payload = current_health_payload()
        health_line = (
            f"The loaded dataset is healthy: revision {health_payload.get('dataset_revision')} "
            f"with fingerprint {health_payload.get('db_fingerprint')}."
        )
    except Exception:
        health_line = "The web app is running, but the database health check is unavailable."
    return (
        "I received your question, but live agent reasoning is disabled because "
        "OPENAI_API_KEY is not configured on this deployment. "
        f"{health_line} "
        "Set OPENAI_API_KEY in Render and redeploy to enable the full Deep Agents "
        "revenue-manager workflow with tool calls, subagents, skills, and HITL gates. "
        f"Question received: {question}"
    )


def chat_model_end_event(text: str) -> dict[str, str]:
    return {
        "event": "on_chat_model_end",
        "data": json.dumps({"data": {"output": {"content": [{"text": text}]}}}),
    }


def require_basic_auth(credentials: HTTPBasicCredentials = Depends(security)) -> str:
    settings = get_settings()
    if (
        not secrets.compare_digest(credentials.username, settings.basic_auth_username)
        or not secrets.compare_digest(credentials.password, settings.basic_auth_password)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


@app.get("/ready")
def ready() -> dict[str, str]:
    return {"status": "ready"}


@app.get("/health")
def health(_: str = Depends(require_basic_auth)) -> dict[str, object]:
    return current_health_payload()


@app.get("/", response_class=HTMLResponse)
def index(_: str = Depends(require_basic_auth)) -> str:
    return (PACKAGE_ROOT / "web" / "index.html").read_text(encoding="utf-8")


@app.get("/api/chat/stream")
async def chat_stream(
    q: str,
    thread_id: str | None = None,
    _: str = Depends(require_basic_auth),
):
    settings = get_settings()
    thread_id = thread_id or str(uuid4())
    if not settings.openai_api_key:
        async def fallback_generator():
            yield chat_model_end_event(model_required_message(q))
            yield {"event": "on_chain_end", "data": json.dumps({"thread_id": thread_id})}

        return EventSourceResponse(fallback_generator())

    bundle = create_revenue_manager_agent()
    agent = bundle.agent
    payload = {"messages": [{"role": "user", "content": q}]}
    config = {"configurable": {"thread_id": thread_id}}

    async def event_generator():
        try:
            async for event in agent.astream_events(payload, config=config, version="v2"):
                yield {
                    "event": event.get("event", "message"),
                    "data": json.dumps(event, default=str),
                }
        except Exception as exc:  # pragma: no cover - deployment-facing fallback
            yield {
                "event": "error",
                "data": json.dumps({"error": str(exc)}),
            }

    return EventSourceResponse(event_generator())


@app.get("/api/chat")
async def chat_once(
    q: str,
    thread_id: str | None = None,
    _: str = Depends(require_basic_auth),
) -> dict[str, Any]:
    settings = get_settings()
    thread_id = thread_id or str(uuid4())
    if not settings.openai_api_key:
        return {
            "status": "model_configuration_required",
            "thread_id": thread_id,
            "messages": [{"role": "assistant", "content": model_required_message(q)}],
        }

    bundle = create_revenue_manager_agent()
    agent = bundle.agent
    try:
        response = await agent.ainvoke(
            {"messages": [{"role": "user", "content": q}]},
            config={"configurable": {"thread_id": thread_id}},
        )
    except Exception as exc:  # pragma: no cover - deployment-facing fallback
        return {
            "status": "agent_error",
            "thread_id": thread_id,
            "messages": [
                {
                    "role": "assistant",
                    "content": (
                        "I could not complete that request safely. Please check that any stay month "
                        "uses YYYY-MM with a valid month 01-12, for example 2025-07. "
                        f"Runtime detail: {exc}"
                    ),
                }
            ],
        }
    return jsonable_encoder(response)
