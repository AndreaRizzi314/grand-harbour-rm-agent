from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from psycopg import Connection

from otel_rm.db import get_connection
from otel_rm.etl.models import ScrapedDataset


ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PATH = ROOT / "schema.sql"
VIEWS_PATH = ROOT / "sql" / "VIEWS.sql"


def apply_sql_file(conn: Connection, path: Path) -> None:
    with path.open(encoding="utf-8") as handle:
        conn.execute(handle.read())


def prepare_database(conn: Connection) -> None:
    apply_sql_file(conn, SCHEMA_PATH)
    apply_sql_file(conn, VIEWS_PATH)


def load_dataset(dataset: ScrapedDataset) -> None:
    with get_connection() as conn:
        prepare_database(conn)
        truncate_for_reload(conn)
        insert_lookups(conn, dataset)
        insert_reservations(conn, dataset)
        conn.execute(
            """
            insert into public.load_manifest (
              dataset_revision,
              scraped_at,
              source_url,
              row_hash
            )
            values (%s, %s, %s, %s)
            """,
            (
                dataset.dataset_revision,
                dataset.scraped_at,
                "https://otel-hackathon-data-site.vercel.app",
                dataset.reservation_stay_status_sha256(),
            ),
        )
        apply_sql_file(conn, VIEWS_PATH)
        conn.commit()


def truncate_for_reload(conn: Connection) -> None:
    conn.execute(
        """
        truncate table
          public.reservations_hackathon,
          public.load_manifest,
          public.market_macro_group_history,
          public.rate_plan_lookup,
          public.channel_code_lookup,
          public.market_code_lookup,
          public.room_type_lookup
        restart identity cascade
        """
    )


def insert_lookups(conn: Connection, dataset: ScrapedDataset) -> None:
    with conn.cursor() as cur:
        cur.executemany(
            """
            insert into public.room_type_lookup (
              space_type,
              room_class,
              display_name,
              number_of_rooms
            )
            values (%(space_type)s, %(room_class)s, %(display_name)s, %(number_of_rooms)s)
            """,
            [asdict(row) for row in dataset.room_types],
        )
        cur.executemany(
            """
            insert into public.market_code_lookup (
              market_code,
              market_name,
              macro_group,
              description
            )
            values (%(market_code)s, %(market_name)s, %(macro_group)s, %(description)s)
            """,
            [asdict(row) for row in dataset.markets],
        )
        cur.executemany(
            """
            insert into public.channel_code_lookup (
              channel_code,
              channel_name,
              channel_group
            )
            values (%(channel_code)s, %(channel_name)s, %(channel_group)s)
            """,
            [asdict(row) for row in dataset.channels],
        )
        cur.executemany(
            """
            insert into public.rate_plan_lookup (
              rate_plan_code,
              plan_family,
              is_commissionable
            )
            values (%(rate_plan_code)s, %(plan_family)s, %(is_commissionable)s)
            """,
            [asdict(row) for row in dataset.rate_plans],
        )
        cur.executemany(
            """
            insert into public.market_macro_group_history (
              market_code,
              valid_from,
              valid_to,
              macro_group
            )
            values (%(market_code)s, %(valid_from)s, %(valid_to)s, %(macro_group)s)
            """,
            [asdict(row) for row in dataset.macro_history],
        )


def insert_reservations(conn: Connection, dataset: ScrapedDataset) -> None:
    with conn.cursor() as cur:
        cur.executemany(
            """
            insert into public.reservations_hackathon (
              reservation_id,
              arrival_date,
              departure_date,
              stay_date,
              property_date,
              reservation_status,
              financial_status,
              create_datetime,
              cancellation_datetime,
              guest_country,
              is_block,
              is_walk_in,
              number_of_spaces,
              space_type,
              market_code,
              channel_code,
              source_name,
              rate_plan_code,
              daily_room_revenue_before_tax,
              daily_total_revenue_before_tax,
              nights,
              adr_room,
              lead_time,
              company_name,
              travel_agent_name
            )
            values (
              %(reservation_id)s,
              %(arrival_date)s,
              %(departure_date)s,
              %(stay_date)s,
              %(property_date)s,
              %(reservation_status)s,
              %(financial_status)s,
              %(create_datetime)s,
              %(cancellation_datetime)s,
              %(guest_country)s,
              %(is_block)s,
              %(is_walk_in)s,
              %(number_of_spaces)s,
              %(space_type)s,
              %(market_code)s,
              %(channel_code)s,
              %(source_name)s,
              %(rate_plan_code)s,
              %(daily_room_revenue_before_tax)s,
              %(daily_total_revenue_before_tax)s,
              %(nights)s,
              %(adr_room)s,
              %(lead_time)s,
              %(company_name)s,
              %(travel_agent_name)s
            )
            """,
            [asdict(row) for row in dataset.reservations],
        )
