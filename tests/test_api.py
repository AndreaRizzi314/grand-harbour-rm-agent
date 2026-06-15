from __future__ import annotations

from fastapi.testclient import TestClient

from otel_rm.api import app
from otel_rm.config import get_settings


def test_chat_without_openai_key_is_graceful(monkeypatch):
    monkeypatch.setenv("BASIC_AUTH_USERNAME", "user")
    monkeypatch.setenv("BASIC_AUTH_PASSWORD", "pass")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    get_settings.cache_clear()

    client = TestClient(app)
    response = client.get(
        "/api/chat",
        params={"q": "What is today's hotel health?"},
        auth=("user", "pass"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "model_configuration_required"
    assert "OPENAI_API_KEY is not configured" in payload["messages"][0]["content"]

    get_settings.cache_clear()
