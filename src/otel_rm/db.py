from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import psycopg
from psycopg.rows import dict_row

from otel_rm.config import get_settings


def get_connection():
    """Create a new psycopg connection using the configured database URL."""
    return psycopg.connect(get_settings().database_url, row_factory=dict_row)


@contextmanager
def connection_cursor() -> Iterator[psycopg.Cursor]:
    """Yield a cursor inside a committed transaction block."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            yield cur
        conn.commit()

