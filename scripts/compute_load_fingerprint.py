#!/usr/bin/env python3
"""
Compute a deterministic load fingerprint after ETL.

Usage:
  python scripts/compute_load_fingerprint.py
  python scripts/compute_load_fingerprint.py --output etl/LOAD_PROOF.json
  python scripts/compute_load_fingerprint.py --manifest etl/SCRAPE_MANIFEST.json

Requires psycopg (pip install psycopg[binary]) or set DATABASE_URL.
Default connection matches docker-compose.yml in this repo.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import date, datetime, timezone
from typing import Any

DEFAULT_DATABASE_URL = (
    "postgresql://hackathon:hackathon@localhost:5432/hotel_hackathon"
)

TABLES = [
    "reservations_hackathon",
    "room_type_lookup",
    "rate_plan_lookup",
    "market_code_lookup",
    "market_macro_group_history",
    "channel_code_lookup",
    "load_manifest",
]


def connect(database_url: str):
    try:
        import psycopg
    except ImportError as exc:
        raise SystemExit(
            "psycopg is required: pip install 'psycopg[binary]'"
        ) from exc

    return psycopg.connect(database_url)


def fetch_row_counts(conn) -> dict[str, int]:
    counts: dict[str, int] = {}
    with conn.cursor() as cur:
        for table in TABLES:
            cur.execute(f"select count(*) from public.{table}")
            row = cur.fetchone()
            counts[table] = int(row[0]) if row else 0
    return counts


def fetch_pair_hash(conn) -> str:
    with conn.cursor() as cur:
        cur.execute(
            """
            select reservation_id, stay_date::text, financial_status
            from public.reservations_hackathon
            order by reservation_id, stay_date, financial_status
            """
        )
        lines = [
            f"{reservation_id}|{stay_date}|{financial_status}"
            for reservation_id, stay_date, financial_status in cur.fetchall()
        ]
    payload = "\n".join(lines).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def fetch_latest_manifest(conn) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(
            """
            select dataset_revision, row_hash, scraped_at::text
            from public.load_manifest
            order by load_id desc
            limit 1
            """
        )
        row = cur.fetchone()
    if not row:
        return {
            "dataset_revision": None,
            "row_hash": None,
            "scraped_at": None,
        }
    dataset_revision, row_hash, scraped_at = row
    return {
        "dataset_revision": dataset_revision,
        "row_hash": row_hash,
        "scraped_at": scraped_at,
    }


def fetch_aggregates(conn, anchor_date: date) -> dict[str, Any]:
    """Aggregates candidates should reconcile with the data site /verify page."""
    with conn.cursor() as cur:
        cur.execute(
            """
            select
              count(*) filter (
                where reservation_status <> 'Cancelled'
                  and financial_status = 'Posted'
                  and stay_date >= %(anchor_date)s
              ) as posted_stay_rows,
              count(distinct reservation_id) filter (
                where reservation_status <> 'Cancelled'
                  and financial_status = 'Posted'
                  and stay_date >= %(anchor_date)s
              ) as posted_reservations,
              coalesce(
                sum(number_of_spaces) filter (
                  where reservation_status <> 'Cancelled'
                    and financial_status = 'Posted'
                    and stay_date >= %(anchor_date)s
                ),
                0
              ) as posted_otb_room_nights,
              count(*) filter (where financial_status = 'Provisional') as provisional_row_count,
              coalesce(
                sum(daily_room_revenue_before_tax) filter (
                  where reservation_status <> 'Cancelled'
                    and financial_status = 'Posted'
                    and stay_date >= %(anchor_date)s
                ),
                0
              )::numeric(14, 2) as posted_room_revenue,
              coalesce(
                sum(number_of_spaces) filter (
                  where reservation_status <> 'Cancelled'
                    and stay_date >= %(anchor_date)s
                ),
                0
              ) as active_room_nights
            from public.reservations_hackathon
            """
            ,
            {"anchor_date": anchor_date},
        )
        row = cur.fetchone()
        if row is None:
            raise RuntimeError("Failed to compute aggregates")

        (
            posted_stay_rows,
            posted_reservations,
            posted_otb_room_nights,
            provisional_row_count,
            posted_room_revenue,
            active_room_nights,
        ) = row

        cur.execute(
            """
            select coalesce(sum(daily_total_revenue_before_tax), 0)::numeric(14, 2)
            from public.reservations_hackathon
            where reservation_status <> 'Cancelled'
              and financial_status = 'Posted'
              and stay_date >= %(july_start)s
              and stay_date < %(august_start)s
            """
            ,
            {
                "july_start": date(anchor_date.year, 7, 1),
                "august_start": date(anchor_date.year, 8, 1),
            },
        )
        july_total_revenue_row = cur.fetchone()
        july_total_revenue = (
            float(july_total_revenue_row[0]) if july_total_revenue_row else 0.0
        )

        cur.execute(
            """
            select count(distinct reservation_id)
            from public.reservations_hackathon
            where reservation_status = 'Cancelled'
            """
        )
        cancelled_reservations_row = cur.fetchone()
        cancelled_reservations = (
            int(cancelled_reservations_row[0]) if cancelled_reservations_row else 0
        )

        cur.execute(
            """
            select count(*)
            from public.reservations_hackathon
            where property_date <> stay_date
            """
        )
        property_date_mismatch_row = cur.fetchone()
        property_date_mismatch_count = (
            int(property_date_mismatch_row[0]) if property_date_mismatch_row else 0
        )

    return {
        "posted_stay_rows": int(posted_stay_rows),
        "posted_reservations": int(posted_reservations),
        "posted_otb_room_nights": int(posted_otb_room_nights),
        "provisional_row_count": int(provisional_row_count),
        "posted_room_revenue": float(posted_room_revenue),
        "active_room_nights": int(active_room_nights),
        "july_2025_posted_total_revenue": july_total_revenue,
        "cancelled_reservation_count": cancelled_reservations,
        "property_date_mismatch_count": property_date_mismatch_count,
    }


def fetch_reservation_ids_hash(conn) -> tuple[int, str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            select distinct reservation_id
            from public.reservations_hackathon
            order by reservation_id
            """
        )
        ids = [row[0] for row in cur.fetchall()]
    payload = "\n".join(ids).encode("utf-8")
    return len(ids), hashlib.sha256(payload).hexdigest()


def validate_manifest(
    conn,
    manifest_path: str,
) -> dict[str, Any]:
    with open(manifest_path, encoding="utf-8") as handle:
        manifest = json.load(handle)

    db_count, db_hash = fetch_reservation_ids_hash(conn)
    manifest_count = int(manifest.get("reservation_ids_count", -1))
    manifest_hash = manifest.get("reservation_ids_sha256", "")

    errors: list[str] = []
    if manifest_count != db_count:
        errors.append(
            f"reservation_ids_count mismatch: manifest={manifest_count} db={db_count}"
        )
    if manifest_hash and manifest_hash != db_hash:
        errors.append("reservation_ids_sha256 does not match database")

    return {
        "manifest_path": manifest_path,
        "manifest_anchor_date": manifest.get("anchor_date"),
        "manifest_pages_scraped": manifest.get("pages_scraped"),
        "db_reservation_ids_count": db_count,
        "db_reservation_ids_sha256": db_hash,
        "manifest_valid": len(errors) == 0,
        "manifest_errors": errors,
    }


def build_fingerprint(
    database_url: str,
    command: str,
    manifest_path: str | None = None,
) -> dict[str, Any]:
    manifest_anchor_date: date | None = None
    if manifest_path:
        with open(manifest_path, encoding="utf-8") as handle:
            manifest_payload = json.load(handle)
        manifest_anchor_date = date.fromisoformat(manifest_payload["anchor_date"])

    anchor_date = manifest_anchor_date or datetime.now(timezone.utc).date()

    with connect(database_url) as conn:
        row_counts = fetch_row_counts(conn)
        pair_hash = fetch_pair_hash(conn)
        aggregates = fetch_aggregates(conn, anchor_date=anchor_date)
        manifest = fetch_latest_manifest(conn)
        manifest_check: dict[str, Any] | None = None
        if manifest_path:
            manifest_check = validate_manifest(conn, manifest_path)

    result: dict[str, Any] = {
        "version": 2,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "command": command,
        "database_url_redacted": redact_database_url(database_url),
        "row_counts": row_counts,
        "reservation_stay_status_sha256": pair_hash,
        "dataset_revision": manifest["dataset_revision"],
        "load_manifest_row_hash": manifest["row_hash"],
        "load_manifest_scraped_at": manifest["scraped_at"],
        "otb_anchor_date": anchor_date.isoformat(),
        "aggregates": aggregates,
        "verify_page_url": "https://otel-hackathon-data-site.vercel.app/verify",
        "notes": (
            "Compare row_counts and aggregates against the data site /verify page. "
            "dataset_revision must match the latest load_manifest row and the site."
        ),
    }
    if manifest_check is not None:
        result["scrape_manifest_check"] = manifest_check
    return result


def redact_database_url(database_url: str) -> str:
    if "@" not in database_url:
        return database_url
    prefix, suffix = database_url.split("@", 1)
    if "://" in prefix:
        scheme, _rest = prefix.split("://", 1)
        return f"{scheme}://***:***@{suffix}"
    return f"***@{suffix}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL),
        help="Postgres connection string (default: docker-compose local DB)",
    )
    parser.add_argument(
        "--manifest",
        help="Validate etl/SCRAPE_MANIFEST.json against loaded DB",
    )
    parser.add_argument(
        "--output",
        help="Write etl/LOAD_PROOF.json (prints JSON to stdout if omitted)",
    )
    args = parser.parse_args()

    command = " ".join(sys.argv)
    fingerprint = build_fingerprint(
        args.database_url,
        command,
        manifest_path=args.manifest,
    )

    payload = json.dumps(fingerprint, indent=2)
    if args.output:
        output_path = args.output
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.write("\n")
        print(f"Wrote {output_path}")
    else:
        print(payload)


if __name__ == "__main__":
    main()
