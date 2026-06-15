from __future__ import annotations

import json
from pathlib import Path
import secrets
from typing import Any
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sse_starlette.sse import EventSourceResponse

from otel_rm.agent.factory import create_revenue_manager_agent
from otel_rm.agent.health import current_health_payload
from otel_rm.config import get_settings


ROOT = Path(__file__).resolve().parents[2]
security = HTTPBasic()
app = FastAPI(title="Grand Harbour Revenue Manager Agent")


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
    return (ROOT / "web" / "index.html").read_text(encoding="utf-8")


@app.get("/api/chat/stream")
async def chat_stream(
    q: str,
    thread_id: str | None = None,
    _: str = Depends(require_basic_auth),
):
    bundle = create_revenue_manager_agent()
    agent = bundle.agent
    thread_id = thread_id or str(uuid4())
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
    bundle = create_revenue_manager_agent()
    agent = bundle.agent
    response = await agent.ainvoke(
        {"messages": [{"role": "user", "content": q}]},
        config={"configurable": {"thread_id": thread_id or str(uuid4())}},
    )
    return response
