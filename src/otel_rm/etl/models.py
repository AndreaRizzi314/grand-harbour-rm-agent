from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
import hashlib


@dataclass(slots=True)
class RoomTypeLookupRow:
    space_type: str
    room_class: str
    display_name: str
    number_of_rooms: int


@dataclass(slots=True)
class RatePlanLookupRow:
    rate_plan_code: str
    plan_family: str
    is_commissionable: bool


@dataclass(slots=True)
class MarketCodeLookupRow:
    market_code: str
    market_name: str
    macro_group: str
    description: str


@dataclass(slots=True)
class MarketMacroGroupHistoryRow:
    market_code: str
    valid_from: date
    valid_to: date | None
    macro_group: str


@dataclass(slots=True)
class ChannelCodeLookupRow:
    channel_code: str
    channel_name: str
    channel_group: str


@dataclass(slots=True)
class StayRow:
    stay_date: date
    property_date: date
    financial_status: str
    daily_room_revenue_before_tax: Decimal
    daily_total_revenue_before_tax: Decimal


@dataclass(slots=True)
class ReservationRecord:
    reservation_id: str
    arrival_date: date
    departure_date: date
    stay_date: date
    property_date: date
    reservation_status: str
    financial_status: str
    create_datetime: datetime
    cancellation_datetime: datetime | None
    guest_country: str | None
    is_block: bool
    is_walk_in: bool
    number_of_spaces: int
    space_type: str
    market_code: str
    channel_code: str
    source_name: str
    rate_plan_code: str
    daily_room_revenue_before_tax: Decimal
    daily_total_revenue_before_tax: Decimal
    nights: int
    adr_room: Decimal
    lead_time: int
    company_name: str | None
    travel_agent_name: str | None


@dataclass(slots=True)
class VerifySnapshot:
    anchor_date: date
    dataset_revision: str
    reservation_stay_status_sha256: str
    total_reservations: int
    total_stay_rows: int
    rate_plan_lookup_rows: int
    market_macro_group_history_rows: int
    cancelled_reservations: int
    provisional_row_count: int
    property_date_mismatch_count: int
    posted_stay_rows: int
    posted_otb_room_nights: int
    posted_room_revenue_before_tax: Decimal
    posted_total_revenue_before_tax: Decimal
    stly_room_nights: int
    stly_total_revenue_before_tax: Decimal


@dataclass(slots=True)
class ScrapedDataset:
    anchor_date: date
    dataset_revision: str
    scraped_at: datetime
    pages_scraped: int
    reservations: list[ReservationRecord]
    room_types: list[RoomTypeLookupRow]
    rate_plans: list[RatePlanLookupRow]
    markets: list[MarketCodeLookupRow]
    macro_history: list[MarketMacroGroupHistoryRow]
    channels: list[ChannelCodeLookupRow]
    verify: VerifySnapshot

    @property
    def reservation_ids(self) -> list[str]:
        return sorted({row.reservation_id for row in self.reservations})

    def reservation_ids_sha256(self) -> str:
        payload = "\n".join(self.reservation_ids).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def reservation_stay_status_sha256(self) -> str:
        lines = [
            f"{row.reservation_id}|{row.stay_date.isoformat()}|{row.financial_status}"
            for row in sorted(
                self.reservations,
                key=lambda row: (
                    row.reservation_id,
                    row.stay_date,
                    row.financial_status,
                ),
            )
        ]
        payload = "\n".join(lines).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def build_scrape_manifest(self) -> dict[str, str | int]:
        return {
            "anchor_date": self.anchor_date.isoformat(),
            "pages_scraped": self.pages_scraped,
            "reservation_ids_count": len(self.reservation_ids),
            "reservation_ids_sha256": self.reservation_ids_sha256(),
            "notes": (
                "Scraped with Playwright from the rendered reservations list and "
                "detail pages. reservation_ids_count must match count(distinct "
                "reservation_id) in the database and total_reservations on /verify."
            ),
        }

