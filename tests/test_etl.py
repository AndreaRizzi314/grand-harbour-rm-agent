from __future__ import annotations

from pathlib import Path


def test_lookup_row_counts(db_conn):
    expected = {
        "room_type_lookup": 3,
        "rate_plan_lookup": 8,
        "market_code_lookup": 10,
        "market_macro_group_history": 11,
        "channel_code_lookup": 4,
    }
    with db_conn.cursor() as cur:
        for table_name, expected_count in expected.items():
            cur.execute(f"select count(*) as row_count from public.{table_name}")
            row = cur.fetchone()
            assert row is not None
            assert row["row_count"] == expected_count


def test_fact_table_grain_uniqueness(db_conn):
    with db_conn.cursor() as cur:
        cur.execute(
            """
            select count(*) as duplicate_pairs
            from (
              select reservation_id, stay_date, count(*) as row_count
              from public.reservations_hackathon
              group by reservation_id, stay_date
              having count(*) > 1
            ) duplicates
            """
        )
        row = cur.fetchone()
        assert row is not None
        assert row["duplicate_pairs"] == 0


def test_manifest_and_load_proof_reconcile(db_conn, scrape_manifest, load_proof):
    with db_conn.cursor() as cur:
        cur.execute(
            "select count(distinct reservation_id) as reservation_count from public.reservations_hackathon"
        )
        reservation_count = cur.fetchone()["reservation_count"]
        cur.execute("select count(*) as stay_rows from public.reservations_hackathon")
        stay_rows = cur.fetchone()["stay_rows"]
        cur.execute(
            """
            select dataset_revision, row_hash
            from public.load_manifest
            order by load_id desc
            limit 1
            """
        )
        manifest_row = cur.fetchone()

    assert scrape_manifest["reservation_ids_count"] == reservation_count
    assert load_proof["row_counts"]["reservations_hackathon"] == stay_rows
    assert load_proof["reservation_stay_status_sha256"] == load_proof["load_manifest_row_hash"]
    assert manifest_row["dataset_revision"] == load_proof["dataset_revision"]
    assert manifest_row["row_hash"] == load_proof["reservation_stay_status_sha256"]
    assert load_proof["scrape_manifest_check"]["manifest_valid"] is True


def test_multi_night_reservation_expands_to_nights(db_conn):
    with db_conn.cursor() as cur:
        cur.execute(
            """
            select reservation_id, max(nights) as nights, count(*) as stay_rows
            from public.reservations_hackathon
            group by reservation_id
            having max(nights) > 1
            order by max(nights) desc, reservation_id
            limit 1
            """
        )
        row = cur.fetchone()

    assert row is not None
    assert row["stay_rows"] == row["nights"]

