from __future__ import annotations

import json
from pathlib import Path

import psycopg
import pytest

from otel_rm.config import get_settings


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def db_conn():
    conn = psycopg.connect(get_settings().database_url, row_factory=psycopg.rows.dict_row)
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture(scope="session")
def scrape_manifest() -> dict:
    return json.loads((ROOT / "etl" / "SCRAPE_MANIFEST.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def load_proof() -> dict:
    return json.loads((ROOT / "etl" / "LOAD_PROOF.json").read_text(encoding="utf-8"))

