from __future__ import annotations

import inspect
import math

from otel_rm.tools.required import (
    get_as_of_otb,
    get_block_vs_transient_mix,
    get_otb_summary,
    get_pickup_delta,
    get_segment_mix,
)


def month_with_provisional_rows(db_conn) -> str:
    with db_conn.cursor() as cur:
        cur.execute(
            """
            select to_char(date_trunc('month', stay_date), 'YYYY-MM') as stay_month
            from public.reservations_hackathon
            where financial_status = 'Provisional'
            group by 1
            order by 1
            limit 1
            """
        )
        row = cur.fetchone()
    assert row is not None
    return row["stay_month"]


def month_with_cancelled_posted_rows(db_conn) -> str:
    with db_conn.cursor() as cur:
        cur.execute(
            """
            select to_char(date_trunc('month', stay_date), 'YYYY-MM') as stay_month
            from public.vw_stay_night_history
            where reservation_status = 'Cancelled'
              and financial_status = 'Posted'
            group by 1
            order by 1
            limit 1
            """
        )
        row = cur.fetchone()
    assert row is not None
    return row["stay_month"]


def month_with_property_date_mismatch(db_conn) -> str:
    with db_conn.cursor() as cur:
        cur.execute(
            """
            with stay_counts as (
              select to_char(date_trunc('month', stay_date), 'YYYY-MM') as month_key, count(*) as row_count
              from public.vw_stay_night_base
              group by 1
            ),
            property_counts as (
              select to_char(date_trunc('month', property_date), 'YYYY-MM') as month_key, count(*) as row_count
              from public.vw_stay_night_base
              group by 1
            )
            select stay_counts.month_key
            from stay_counts
            left join property_counts using (month_key)
            where stay_counts.row_count <> coalesce(property_counts.row_count, 0)
            order by stay_counts.month_key
            limit 1
            """
        )
        row = cur.fetchone()
    assert row is not None
    return row["month_key"]


def test_grain_inequality_july_otb():
    result = get_otb_summary("2025-07", exclude_cancelled=True)
    assert result["reservation_count"] < result["row_count"]
    assert result["room_nights"] >= result["reservation_count"]
    assert result["room_revenue"] <= result["total_revenue"]


def test_cancellation_filter_changes_counts(db_conn):
    stay_month = month_with_cancelled_posted_rows(db_conn)
    excluded = get_otb_summary(stay_month, exclude_cancelled=True)
    included = get_otb_summary(stay_month, exclude_cancelled=False)
    assert excluded["row_count"] < included["row_count"]
    assert excluded["reservation_count"] <= included["reservation_count"]


def test_segment_shares_sum_to_one():
    result = get_segment_mix("2025-07")
    assert math.isclose(
        sum(segment["share_of_room_nights"] for segment in result["segments"]),
        1.0,
        abs_tol=1e-6,
    )
    assert math.isclose(
        sum(segment["share_of_revenue"] for segment in result["segments"]),
        1.0,
        abs_tol=1e-6,
    )
    for segment in result["segments"]:
        assert 0.0 <= segment["share_of_room_nights"] <= 1.0
        assert 0.0 <= segment["share_of_revenue"] <= 1.0


def test_macro_group_filter_narrows_universe():
    unfiltered = get_segment_mix("2025-07")
    filtered = get_segment_mix("2025-07", macro_group="Retail")
    assert sum(segment["room_nights"] for segment in filtered["segments"]) <= sum(
        segment["room_nights"] for segment in unfiltered["segments"]
    )
    assert all(segment["macro_group"] == "Retail" for segment in filtered["segments"])


def test_pickup_uses_booking_date_for_window():
    long_window = get_pickup_delta(booking_window_days=365, future_stay_from="2025-07-01")
    short_window = get_pickup_delta(booking_window_days=1, future_stay_from="2025-07-01")
    assert long_window["future_stay_from"] == "2025-07-01"
    assert short_window["new_reservations"] <= long_window["new_reservations"]


def test_ota_concentration_signal():
    result = get_segment_mix("2025-08")
    ota_segment = next((segment for segment in result["segments"] if segment["market_code"] == "OTA"), None)
    assert ota_segment is not None, "OTA segment missing; ETL or month selection is broken."
    assert 0.0 < ota_segment["share_of_revenue"] < 1.0


def test_provisional_rows_excluded_from_default_otb(db_conn, load_proof):
    stay_month = month_with_provisional_rows(db_conn)
    default_result = get_otb_summary(stay_month)
    with db_conn.cursor() as cur:
        cur.execute(
            """
            select count(*) as row_count
            from public.vw_stay_night_history
            where stay_date >= to_date(%s, 'YYYY-MM')
              and stay_date < (to_date(%s, 'YYYY-MM') + interval '1 month')
              and reservation_status <> 'Cancelled'
            """,
            (stay_month, stay_month),
        )
        raw_row_count = cur.fetchone()["row_count"]
    assert default_result["row_count"] < raw_row_count
    assert load_proof["aggregates"]["provisional_row_count"] > 0


def test_as_of_snapshot_differs_from_current_otb():
    current = get_otb_summary("2025-08")
    historical = get_as_of_otb("2025-08", "2025-05-01T12:00:00Z")
    assert historical["reservation_count"] <= current["reservation_count"]
    assert historical["row_count"] != current["row_count"] or historical["total_revenue"] != current["total_revenue"]


def test_property_date_mismatch_matches_load_proof(db_conn, load_proof):
    stay_month = month_with_property_date_mismatch(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(
            "select count(*) as mismatch_count from public.reservations_hackathon where property_date <> stay_date"
        )
        mismatch_count = cur.fetchone()["mismatch_count"]
        cur.execute(
            """
            select count(*) as stay_date_count
            from public.vw_stay_night_base
            where stay_date >= to_date(%s, 'YYYY-MM')
              and stay_date < (to_date(%s, 'YYYY-MM') + interval '1 month')
            """
            ,
            (stay_month, stay_month),
        )
        stay_date_count = cur.fetchone()["stay_date_count"]
        cur.execute(
            """
            select count(*) as property_date_count
            from public.vw_stay_night_base
            where property_date >= to_date(%s, 'YYYY-MM')
              and property_date < (to_date(%s, 'YYYY-MM') + interval '1 month')
            """
            ,
            (stay_month, stay_month),
        )
        property_date_count = cur.fetchone()["property_date_count"]
    assert mismatch_count == load_proof["aggregates"]["property_date_mismatch_count"]
    assert get_otb_summary(stay_month)["row_count"] == stay_date_count
    assert stay_date_count != property_date_count


def test_block_vs_transient_mix_reconciles_to_otb():
    summary = get_otb_summary("2025-09")
    mix = get_block_vs_transient_mix("2025-09")
    assert mix["block_room_nights"] + mix["transient_room_nights"] == summary["room_nights"]
    assert 0.0 <= mix["block_share_of_room_nights"] <= 1.0
    assert 0.0 <= mix["block_share_of_revenue"] <= 1.0
    assert mix["top3_company_revenue_share"] <= 1.0
    assert len(mix["top_companies"]) <= 3
    assert mix["top_companies"] == sorted(
        mix["top_companies"],
        key=lambda item: item["total_revenue"],
        reverse=True,
    )


def test_tool_surface_is_isolated_and_docstrings_are_grain_aware():
    for fn in [
        get_otb_summary,
        get_segment_mix,
        get_pickup_delta,
        get_as_of_otb,
        get_block_vs_transient_mix,
    ]:
        signature = inspect.signature(fn)
        assert "sql" not in signature.parameters
        assert "query" not in signature.parameters
        assert fn.__doc__ is not None
        assert "grain" in fn.__doc__.lower()
