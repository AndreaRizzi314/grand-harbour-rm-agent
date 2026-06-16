from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from langchain_core.tools import tool

from otel_rm.db import connection_cursor

LONDON = ZoneInfo("Europe/London")


def month_bounds(stay_month: str) -> tuple[str, str]:
    try:
        year_text, month_text = stay_month.split("-", maxsplit=1)
        year = int(year_text)
        month = int(month_text)
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("stay_month must be a valid YYYY-MM value, for example 2025-07.") from exc

    if len(stay_month) != 7 or len(year_text) != 4 or len(month_text) != 2 or not 1 <= month <= 12:
        raise ValueError("stay_month must be a valid YYYY-MM value with month 01-12, for example 2025-07.")

    start = datetime(year, month, 1).date()
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    return start.isoformat(), end.isoformat()


def scalar_float(value: Decimal | float | int | None) -> float:
    if value is None:
        return 0.0
    return float(value)


def current_window_start_utc(booking_window_days: int) -> datetime:
    now_utc = datetime.now(UTC)
    london_reference = now_utc.astimezone(LONDON) - timedelta(days=booking_window_days)
    london_midnight = london_reference.replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )
    return london_midnight.astimezone(UTC)


def get_otb_summary(stay_month: str, exclude_cancelled: bool = True) -> dict:
    """
    On-the-books summary for a calendar stay month.

    Grain: `row_count` is stay-date rows, `reservation_count` is distinct reservations,
    and `room_nights` is `sum(number_of_spaces)` at stay-date grain. Default OTB
    excludes Cancelled rows and excludes Provisional rows.
    """
    start, end = month_bounds(stay_month)
    from_view = "public.vw_stay_night_base"
    where_clause = "stay_date >= %s and stay_date < %s"
    params: list[object] = [start, end]

    if not exclude_cancelled:
        from_view = "public.vw_stay_night_history"
        where_clause += " and financial_status = 'Posted'"

    with connection_cursor() as cur:
        cur.execute(
            f"""
            select
              count(*) as row_count,
              count(distinct reservation_id) as reservation_count,
              coalesce(sum(number_of_spaces), 0) as room_nights,
              coalesce(sum(daily_room_revenue_before_tax), 0)::numeric(14, 2) as room_revenue,
              coalesce(sum(daily_total_revenue_before_tax), 0)::numeric(14, 2) as total_revenue
            from {from_view}
            where {where_clause}
            """,
            params,
        )
        row = cur.fetchone()

    assert row is not None
    return {
        "stay_month": stay_month,
        "row_count": int(row["row_count"]),
        "reservation_count": int(row["reservation_count"]),
        "room_nights": int(row["room_nights"]),
        "room_revenue": scalar_float(row["room_revenue"]),
        "total_revenue": scalar_float(row["total_revenue"]),
        "exclude_cancelled": exclude_cancelled,
        "grain": {
            "row_count": "stay-date rows",
            "reservation_count": "distinct reservation_id",
            "room_nights": "sum(number_of_spaces) at stay-date grain",
        },
    }


def get_segment_mix(stay_month: str, macro_group: str | None = None) -> dict:
    """
    Segment mix for a stay month using `vw_segment_stay_night`.

    Grain: each returned segment aggregates stay-date rows. Shares use the same filtered
    denominator for all rows in the result set.
    """
    start, end = month_bounds(stay_month)
    params: list[object] = [start, end]
    filter_sql = ""
    if macro_group:
        filter_sql = " and effective_macro_group = %s"
        params.append(macro_group)

    with connection_cursor() as cur:
        cur.execute(
            f"""
            with scoped as (
              select *
              from public.vw_segment_stay_night
              where stay_date >= %s
                and stay_date < %s
                {filter_sql}
            ),
            totals as (
              select
                coalesce(sum(number_of_spaces), 0) as total_room_nights,
                coalesce(sum(daily_total_revenue_before_tax), 0)::numeric(14, 2) as total_revenue
              from scoped
            )
            select
              scoped.market_code,
              scoped.market_name,
              scoped.effective_macro_group as macro_group,
              sum(scoped.number_of_spaces) as room_nights,
              coalesce(sum(scoped.daily_total_revenue_before_tax), 0)::numeric(14, 2) as segment_total_revenue,
              case
                when totals.total_room_nights = 0 then 0
                else sum(scoped.number_of_spaces)::numeric / totals.total_room_nights
              end as share_of_room_nights,
              case
                when totals.total_revenue = 0 then 0
                else sum(scoped.daily_total_revenue_before_tax)::numeric / totals.total_revenue
              end as share_of_revenue,
              totals.total_room_nights as denominator_room_nights,
              totals.total_revenue as denominator_total_revenue
            from scoped
            cross join totals
            group by
              scoped.market_code,
              scoped.market_name,
              scoped.effective_macro_group,
              denominator_room_nights,
              denominator_total_revenue
            order by segment_total_revenue desc, room_nights desc, scoped.market_code
            """,
            params,
        )
        rows = cur.fetchall()

    denominator = {
        "room_nights": int(rows[0]["denominator_room_nights"]) if rows else 0,
        "total_revenue": scalar_float(rows[0]["denominator_total_revenue"]) if rows else 0.0,
        "definition": "All segments in the same filtered result set.",
    }
    return {
        "stay_month": stay_month,
        "macro_group_filter": macro_group,
        "denominator": denominator,
        "segments": [
            {
                "market_code": row["market_code"],
                "market_name": row["market_name"],
                "macro_group": row["macro_group"],
                "room_nights": int(row["room_nights"]),
                "total_revenue": scalar_float(row["segment_total_revenue"]),
                "share_of_room_nights": scalar_float(row["share_of_room_nights"]),
                "share_of_revenue": scalar_float(row["share_of_revenue"]),
            }
            for row in rows
        ],
        "grain": "Each segment row aggregates stay-date rows from vw_segment_stay_night.",
    }


def get_pickup_delta(booking_window_days: int, future_stay_from: str) -> dict:
    """
    Booking pace / pickup for future stays.

    Grain: `new_reservations` is distinct reservation_id created in the booking window,
    while revenue and room nights aggregate stay-date rows whose stay_date is on or after
    `future_stay_from`. Booking windows use Europe/London local midnight boundaries.
    """
    window_start = current_window_start_utc(booking_window_days)
    now_utc = datetime.now(UTC)

    with connection_cursor() as cur:
        cur.execute(
            """
            with scoped as (
              select *
              from public.vw_segment_stay_night
              where create_datetime >= %s
                and create_datetime <= %s
                and stay_date >= %s
            )
            select
              count(distinct reservation_id) as new_reservations,
              coalesce(sum(number_of_spaces), 0) as new_room_nights,
              coalesce(sum(daily_total_revenue_before_tax), 0)::numeric(14, 2) as new_total_revenue
            from scoped
            """,
            (window_start, now_utc, future_stay_from),
        )
        summary = cur.fetchone()

        cur.execute(
            """
            with scoped as (
              select *
              from public.vw_segment_stay_night
              where create_datetime >= %s
                and create_datetime <= %s
                and stay_date >= %s
            )
            select
              market_code,
              market_name,
              effective_macro_group as macro_group,
              count(distinct reservation_id) as new_reservations,
              coalesce(sum(number_of_spaces), 0) as new_room_nights,
              coalesce(sum(daily_total_revenue_before_tax), 0)::numeric(14, 2) as new_total_revenue
            from scoped
            group by market_code, market_name, effective_macro_group
            order by new_total_revenue desc, new_room_nights desc, market_code
            """,
            (window_start, now_utc, future_stay_from),
        )
        by_segment = cur.fetchall()

    assert summary is not None
    return {
        "booking_window_days": booking_window_days,
        "future_stay_from": future_stay_from,
        "window_start_utc": window_start.isoformat(),
        "window_end_utc": now_utc.isoformat(),
        "new_reservations": int(summary["new_reservations"]),
        "new_room_nights": int(summary["new_room_nights"]),
        "new_total_revenue": scalar_float(summary["new_total_revenue"]),
        "by_segment": [
            {
                "market_code": row["market_code"],
                "market_name": row["market_name"],
                "macro_group": row["macro_group"],
                "new_reservations": int(row["new_reservations"]),
                "new_room_nights": int(row["new_room_nights"]),
                "new_total_revenue": scalar_float(row["new_total_revenue"]),
            }
            for row in by_segment
        ],
        "grain": {
            "new_reservations": "distinct reservation_id created in the booking window",
            "new_room_nights": "sum(number_of_spaces) for future stay-date rows in scope",
        },
    }


def get_as_of_otb(stay_month: str, as_of_utc: str) -> dict:
    """
    Point-in-time on-the-books for a stay month as known at `as_of_utc`.

    Grain: `row_count` is stay-date rows that were on the books at the point in time,
    `reservation_count` is distinct reservations in that same historical universe, and
    `room_nights` is `sum(number_of_spaces)` over those stay-date rows.
    """
    start, end = month_bounds(stay_month)
    with connection_cursor() as cur:
        cur.execute(
            """
            select
              count(*) as row_count,
              count(distinct reservation_id) as reservation_count,
              coalesce(sum(number_of_spaces), 0) as room_nights,
              coalesce(sum(daily_room_revenue_before_tax), 0)::numeric(14, 2) as room_revenue,
              coalesce(sum(daily_total_revenue_before_tax), 0)::numeric(14, 2) as total_revenue
            from public.vw_stay_night_history
            where stay_date >= %s
              and stay_date < %s
              and create_datetime <= %s::timestamptz
              and (reservation_status <> 'Cancelled' or cancellation_datetime > %s::timestamptz)
              and financial_status = 'Posted'
            """,
            (start, end, as_of_utc, as_of_utc),
        )
        row = cur.fetchone()

    assert row is not None
    return {
        "stay_month": stay_month,
        "as_of_utc": as_of_utc,
        "row_count": int(row["row_count"]),
        "reservation_count": int(row["reservation_count"]),
        "room_nights": int(row["room_nights"]),
        "room_revenue": scalar_float(row["room_revenue"]),
        "total_revenue": scalar_float(row["total_revenue"]),
        "grain": {
            "row_count": "historical stay-date rows visible at as_of_utc",
            "reservation_count": "distinct reservation_id at the same historical point in time",
            "room_nights": "sum(number_of_spaces) for those historical stay-date rows",
        },
    }


def get_block_vs_transient_mix(stay_month: str) -> dict:
    """
    Block vs transient mix for a stay month.

    Grain: room nights and revenue aggregate stay-date rows from `vw_stay_night_base`.
    Top companies are ranked by total revenue within the filtered month.
    """
    start, end = month_bounds(stay_month)
    with connection_cursor() as cur:
        cur.execute(
            """
            with scoped as (
              select *
              from public.vw_stay_night_base
              where stay_date >= %s
                and stay_date < %s
            )
            select
              coalesce(sum(number_of_spaces) filter (where is_block), 0) as block_room_nights,
              coalesce(sum(number_of_spaces) filter (where not is_block), 0) as transient_room_nights,
              coalesce(sum(daily_total_revenue_before_tax) filter (where is_block), 0)::numeric(14, 2) as block_total_revenue,
              coalesce(sum(daily_total_revenue_before_tax) filter (where not is_block), 0)::numeric(14, 2) as transient_total_revenue,
              coalesce(sum(number_of_spaces), 0) as total_room_nights,
              coalesce(sum(daily_total_revenue_before_tax), 0)::numeric(14, 2) as total_revenue
            from scoped
            """,
            (start, end),
        )
        totals = cur.fetchone()

        cur.execute(
            """
            with scoped as (
              select *
              from public.vw_stay_night_base
              where stay_date >= %s
                and stay_date < %s
            )
            select
              coalesce(company_name, 'Transient') as company_name,
              coalesce(sum(daily_total_revenue_before_tax), 0)::numeric(14, 2) as total_revenue
            from scoped
            group by coalesce(company_name, 'Transient')
            order by total_revenue desc, company_name
            limit 3
            """,
            (start, end),
        )
        top_companies = cur.fetchall()

    assert totals is not None
    total_room_nights = int(totals["total_room_nights"])
    total_revenue = scalar_float(totals["total_revenue"])
    top3_revenue = sum(scalar_float(row["total_revenue"]) for row in top_companies)

    return {
        "stay_month": stay_month,
        "block_room_nights": int(totals["block_room_nights"]),
        "transient_room_nights": int(totals["transient_room_nights"]),
        "block_total_revenue": scalar_float(totals["block_total_revenue"]),
        "transient_total_revenue": scalar_float(totals["transient_total_revenue"]),
        "block_share_of_room_nights": (
            int(totals["block_room_nights"]) / total_room_nights if total_room_nights else 0.0
        ),
        "transient_share_of_room_nights": (
            int(totals["transient_room_nights"]) / total_room_nights if total_room_nights else 0.0
        ),
        "block_share_of_revenue": (
            scalar_float(totals["block_total_revenue"]) / total_revenue if total_revenue else 0.0
        ),
        "transient_share_of_revenue": (
            scalar_float(totals["transient_total_revenue"]) / total_revenue if total_revenue else 0.0
        ),
        "top_companies": [
            {
                "company_name": row["company_name"],
                "total_revenue": scalar_float(row["total_revenue"]),
            }
            for row in top_companies
        ],
        "top3_company_revenue_share": (top3_revenue / total_revenue if total_revenue else 0.0),
        "grain": "All totals aggregate stay-date rows from vw_stay_night_base for the month.",
    }


def get_room_type_adr(stay_month: str) -> dict:
    """
    Room-type ADR ranking for a calendar stay month.

    Grain: each room-type row aggregates posted, non-cancelled stay-date rows from
    `vw_stay_night_base`. ADR is room revenue divided by room nights, not row count.
    """
    start, end = month_bounds(stay_month)
    with connection_cursor() as cur:
        cur.execute(
            """
            select
              space_type as room_type,
              count(*) as row_count,
              count(distinct reservation_id) as reservation_count,
              coalesce(sum(number_of_spaces), 0) as room_nights,
              coalesce(sum(daily_room_revenue_before_tax), 0)::numeric(14, 2) as room_revenue,
              case
                when coalesce(sum(number_of_spaces), 0) = 0 then 0
                else coalesce(sum(daily_room_revenue_before_tax), 0)::numeric
                  / sum(number_of_spaces)
              end as adr
            from public.vw_stay_night_base
            where stay_date >= %s
              and stay_date < %s
            group by space_type
            order by adr desc, room_revenue desc, space_type
            """,
            (start, end),
        )
        rows = cur.fetchall()

    room_types = [
        {
            "room_type": row["room_type"],
            "row_count": int(row["row_count"]),
            "reservation_count": int(row["reservation_count"]),
            "room_nights": int(row["room_nights"]),
            "room_revenue": scalar_float(row["room_revenue"]),
            "adr": scalar_float(row["adr"]),
        }
        for row in rows
    ]
    return {
        "stay_month": stay_month,
        "room_types": room_types,
        "highest_adr_room_type": room_types[0] if room_types else None,
        "grain": "Room-type rows aggregate posted, non-cancelled stay-date rows; ADR = room revenue / room nights.",
    }


def get_cancellation_summary(stay_month: str, date_basis: str = "stay_date") -> dict:
    """
    Cancelled-business summary for a calendar month.

    Grain: cancelled rows are stay-date rows from `vw_stay_night_history`.
    `date_basis='stay_date'` answers cancelled stays for the month; `date_basis=
    'cancellation_date'` answers cancellation activity during the month.
    """
    if date_basis not in {"stay_date", "cancellation_date"}:
        raise ValueError("date_basis must be 'stay_date' or 'cancellation_date'")

    start, end = month_bounds(stay_month)
    date_filter = "stay_date >= %s and stay_date < %s"
    if date_basis == "cancellation_date":
        date_filter = "cancellation_datetime >= %s::date and cancellation_datetime < %s::date"

    with connection_cursor() as cur:
        cur.execute(
            f"""
            with cancelled as (
              select *
              from public.vw_stay_night_history
              where reservation_status = 'Cancelled'
                and {date_filter}
            )
            select
              count(*) as row_count,
              count(distinct reservation_id) as reservation_count,
              coalesce(sum(number_of_spaces), 0) as room_nights,
              coalesce(sum(daily_room_revenue_before_tax), 0)::numeric(14, 2) as room_revenue,
              coalesce(sum(daily_total_revenue_before_tax), 0)::numeric(14, 2) as total_revenue
            from cancelled
            """,
            (start, end),
        )
        summary = cur.fetchone()

        cur.execute(
            f"""
            with cancelled as (
              select *
              from public.vw_stay_night_history
              where reservation_status = 'Cancelled'
                and {date_filter}
            )
            select
              market_code,
              market_name,
              effective_macro_group as macro_group,
              count(distinct reservation_id) as reservation_count,
              coalesce(sum(number_of_spaces), 0) as room_nights,
              coalesce(sum(daily_total_revenue_before_tax), 0)::numeric(14, 2) as total_revenue
            from cancelled
            group by market_code, market_name, effective_macro_group
            order by total_revenue desc, room_nights desc, market_code
            """,
            (start, end),
        )
        by_segment = cur.fetchall()

    assert summary is not None
    return {
        "stay_month": stay_month,
        "date_basis": date_basis,
        "row_count": int(summary["row_count"]),
        "reservation_count": int(summary["reservation_count"]),
        "room_nights": int(summary["room_nights"]),
        "room_revenue": scalar_float(summary["room_revenue"]),
        "total_revenue": scalar_float(summary["total_revenue"]),
        "by_segment": [
            {
                "market_code": row["market_code"],
                "market_name": row["market_name"],
                "macro_group": row["macro_group"],
                "reservation_count": int(row["reservation_count"]),
                "room_nights": int(row["room_nights"]),
                "total_revenue": scalar_float(row["total_revenue"]),
            }
            for row in by_segment
        ],
        "grain": (
            "Cancelled stay-date rows when date_basis='stay_date'; cancellation "
            "activity rows when date_basis='cancellation_date'."
        ),
    }


def get_monthly_otb_trend(start_month: str, end_month: str) -> dict:
    """
    Month-by-month OTB trend for an inclusive month range.

    Grain: each month aggregates posted, non-cancelled stay-date rows from
    `vw_stay_night_base`, with room nights as `sum(number_of_spaces)`.
    """
    start, _ = month_bounds(start_month)
    _, end = month_bounds(end_month)
    with connection_cursor() as cur:
        cur.execute(
            """
            with months as (
              select generate_series(%s::date, (%s::date - interval '1 month')::date, interval '1 month')::date as month_start
            )
            select
              to_char(months.month_start, 'YYYY-MM') as stay_month,
              count(base.*) as row_count,
              count(distinct base.reservation_id) as reservation_count,
              coalesce(sum(base.number_of_spaces), 0) as room_nights,
              coalesce(sum(base.daily_room_revenue_before_tax), 0)::numeric(14, 2) as room_revenue,
              coalesce(sum(base.daily_total_revenue_before_tax), 0)::numeric(14, 2) as total_revenue
            from months
            left join public.vw_stay_night_base base
              on base.stay_date >= months.month_start
             and base.stay_date < months.month_start + interval '1 month'
            group by months.month_start
            order by months.month_start
            """,
            (start, end),
        )
        rows = cur.fetchall()

    return {
        "start_month": start_month,
        "end_month": end_month,
        "months": [
            {
                "stay_month": row["stay_month"],
                "row_count": int(row["row_count"]),
                "reservation_count": int(row["reservation_count"]),
                "room_nights": int(row["room_nights"]),
                "room_revenue": scalar_float(row["room_revenue"]),
                "total_revenue": scalar_float(row["total_revenue"]),
            }
            for row in rows
        ],
        "grain": "Each month aggregates posted, non-cancelled stay-date rows from vw_stay_night_base.",
    }


def get_corporate_share(start_month: str, end_month: str, include_mice_groups: bool = False) -> dict:
    """
    Corporate share of future or selected stay months.

    Grain: the denominator is all posted, non-cancelled stay-date rows in the
    inclusive month range. By default, Corporate means effective macro group
    `Corporate`; set `include_mice_groups=True` to include corporate group blocks.
    """
    start, _ = month_bounds(start_month)
    _, end = month_bounds(end_month)
    corporate_filter = "effective_macro_group = 'Corporate'"
    if include_mice_groups:
        corporate_filter = "(effective_macro_group = 'Corporate' or market_code = 'CGR')"

    with connection_cursor() as cur:
        cur.execute(
            f"""
            with scoped as (
              select *
              from public.vw_segment_stay_night
              where stay_date >= %s
                and stay_date < %s
            )
            select
              count(*) as row_count,
              count(distinct reservation_id) as reservation_count,
              coalesce(sum(number_of_spaces), 0) as room_nights,
              coalesce(sum(daily_total_revenue_before_tax), 0)::numeric(14, 2) as total_revenue,
              count(*) filter (where {corporate_filter}) as corporate_row_count,
              count(distinct reservation_id) filter (where {corporate_filter}) as corporate_reservation_count,
              coalesce(sum(number_of_spaces) filter (where {corporate_filter}), 0) as corporate_room_nights,
              coalesce(sum(daily_total_revenue_before_tax) filter (where {corporate_filter}), 0)::numeric(14, 2) as corporate_total_revenue
            from scoped
            """,
            (start, end),
        )
        row = cur.fetchone()

    assert row is not None
    room_nights = int(row["room_nights"])
    total_revenue = scalar_float(row["total_revenue"])
    corporate_room_nights = int(row["corporate_room_nights"])
    corporate_total_revenue = scalar_float(row["corporate_total_revenue"])
    return {
        "start_month": start_month,
        "end_month": end_month,
        "include_mice_groups": include_mice_groups,
        "denominator": {
            "row_count": int(row["row_count"]),
            "reservation_count": int(row["reservation_count"]),
            "room_nights": room_nights,
            "total_revenue": total_revenue,
        },
        "corporate": {
            "row_count": int(row["corporate_row_count"]),
            "reservation_count": int(row["corporate_reservation_count"]),
            "room_nights": corporate_room_nights,
            "total_revenue": corporate_total_revenue,
            "share_of_room_nights": corporate_room_nights / room_nights if room_nights else 0.0,
            "share_of_revenue": corporate_total_revenue / total_revenue if total_revenue else 0.0,
        },
        "grain": "Shares use stay-date rows from vw_segment_stay_night across the inclusive month range.",
    }


def get_company_concentration(stay_month: str, include_transient: bool = True) -> dict:
    """
    Company revenue concentration for a stay month.

    Grain: company rows aggregate posted, non-cancelled stay-date rows. Transient
    rows can be included as a named bucket or excluded for account-only ranking.
    """
    start, end = month_bounds(stay_month)
    transient_filter = ""
    if not include_transient:
        transient_filter = "and company_name is not null"

    with connection_cursor() as cur:
        cur.execute(
            f"""
            with scoped as (
              select *
              from public.vw_stay_night_base
              where stay_date >= %s
                and stay_date < %s
                {transient_filter}
            ),
            totals as (
              select
                coalesce(sum(number_of_spaces), 0) as total_room_nights,
                coalesce(sum(daily_total_revenue_before_tax), 0)::numeric(14, 2) as total_revenue
              from scoped
            )
            select
              coalesce(scoped.company_name, 'Transient') as company_name,
              coalesce(sum(scoped.number_of_spaces), 0) as room_nights,
              coalesce(sum(scoped.daily_total_revenue_before_tax), 0)::numeric(14, 2) as total_revenue,
              case
                when totals.total_revenue = 0 then 0
                else sum(scoped.daily_total_revenue_before_tax)::numeric / totals.total_revenue
              end as share_of_revenue,
              totals.total_room_nights as denominator_room_nights,
              totals.total_revenue as denominator_total_revenue
            from scoped
            cross join totals
            group by company_name, denominator_room_nights, denominator_total_revenue
            order by total_revenue desc, room_nights desc, company_name
            limit 10
            """,
            (start, end),
        )
        rows = cur.fetchall()

    denominator = {
        "room_nights": int(rows[0]["denominator_room_nights"]) if rows else 0,
        "total_revenue": scalar_float(rows[0]["denominator_total_revenue"]) if rows else 0.0,
    }
    companies = [
        {
            "company_name": row["company_name"],
            "room_nights": int(row["room_nights"]),
            "total_revenue": scalar_float(row["total_revenue"]),
            "share_of_revenue": scalar_float(row["share_of_revenue"]),
        }
        for row in rows
    ]
    top3_revenue = sum(company["total_revenue"] for company in companies[:3])
    return {
        "stay_month": stay_month,
        "include_transient": include_transient,
        "denominator": denominator,
        "companies": companies,
        "top3_company_revenue_share": (
            top3_revenue / denominator["total_revenue"] if denominator["total_revenue"] else 0.0
        ),
        "grain": "Company rows aggregate posted, non-cancelled stay-date rows from vw_stay_night_base.",
    }


otb_summary_tool = tool(get_otb_summary)
segment_mix_tool = tool(get_segment_mix)
pickup_delta_tool = tool(get_pickup_delta)
as_of_otb_tool = tool(get_as_of_otb)
block_vs_transient_mix_tool = tool(get_block_vs_transient_mix)
room_type_adr_tool = tool(get_room_type_adr)
cancellation_summary_tool = tool(get_cancellation_summary)
monthly_otb_trend_tool = tool(get_monthly_otb_trend)
corporate_share_tool = tool(get_corporate_share)
company_concentration_tool = tool(get_company_concentration)


REQUIRED_TOOLS = [
    otb_summary_tool,
    segment_mix_tool,
    pickup_delta_tool,
    as_of_otb_tool,
    block_vs_transient_mix_tool,
]

ADDITIONAL_SEMANTIC_TOOLS = [
    room_type_adr_tool,
    cancellation_summary_tool,
    monthly_otb_trend_tool,
    corporate_share_tool,
    company_concentration_tool,
]

AGENT_TOOLS = REQUIRED_TOOLS + ADDITIONAL_SEMANTIC_TOOLS
