from __future__ import annotations

from datetime import UTC, datetime
import hashlib

from otel_rm.db import connection_cursor


def current_health_payload() -> dict[str, object]:
    with connection_cursor() as cur:
        cur.execute(
            """
            select
              dataset_revision,
              row_hash,
              scraped_at::date as anchor_date
            from public.load_manifest
            order by load_id desc
            limit 1
            """
        )
        manifest_row = cur.fetchone()
        if manifest_row is None:
            return {
                "status": "not_loaded",
                "checked_at": datetime.now(UTC).isoformat(),
            }

        cur.execute(
            """
            select reservation_id, stay_date::text, financial_status
            from public.reservations_hackathon
            order by reservation_id, stay_date, financial_status
            """
        )
        payload = "\n".join(
            f"{row['reservation_id']}|{row['stay_date']}|{row['financial_status']}"
            for row in cur.fetchall()
        ).encode("utf-8")
        db_fingerprint = hashlib.sha256(payload).hexdigest()

        cur.execute(
            """
            select count(*) as posted_rows
            from public.reservations_hackathon
            where reservation_status <> 'Cancelled'
              and financial_status = 'Posted'
              and stay_date >= %s
            """,
            (manifest_row["anchor_date"],),
        )
        posted_rows = cur.fetchone()["posted_rows"]

    return {
        "status": "ok",
        "checked_at": datetime.now(UTC).isoformat(),
        "db_fingerprint": db_fingerprint,
        "dataset_revision": manifest_row["dataset_revision"],
        "row_hash": manifest_row["row_hash"],
        "financial_status_posted_only_rows": int(posted_rows),
    }

