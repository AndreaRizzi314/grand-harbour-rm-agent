from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
import re
from typing import Any

from playwright.sync_api import Browser, Locator, Page, sync_playwright

from otel_rm.etl.models import (
    ChannelCodeLookupRow,
    MarketCodeLookupRow,
    MarketMacroGroupHistoryRow,
    RatePlanLookupRow,
    ReservationRecord,
    RoomTypeLookupRow,
    ScrapedDataset,
    VerifySnapshot,
)

BASE_URL = "https://otel-hackathon-data-site.vercel.app"
RESERVATIONS_URL = f"{BASE_URL}/reservations"
REFERENCE_URL = f"{BASE_URL}/reference"
VERIFY_URL = f"{BASE_URL}/verify"


@dataclass(slots=True)
class ReservationListRow:
    reservation_id: str
    arrival_date: date
    departure_date: date
    nights: int
    reservation_status: str
    market_code: str
    channel_code: str
    space_type: str
    number_of_spaces: int
    adr_room: Decimal
    lead_time: int
    detail_path: str


class HackathonSiteScraper:
    """Scrape the rendered hackathon data site with Playwright."""

    def __init__(self, headless: bool = True):
        self.headless = headless

    def scrape(self) -> ScrapedDataset:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=self.headless)
            try:
                page = browser.new_page(viewport={"width": 1440, "height": 1600})
                verify = self.scrape_verify(page)
                room_types, markets, channels, rate_plans, macro_history = (
                    self.scrape_reference(page)
                )
                pages_scraped, reservation_rows = self.scrape_reservation_index(page)

                reservations = [
                    self.scrape_reservation_detail(browser, row)
                    for row in reservation_rows
                ]
            finally:
                browser.close()

        reservations_flat = [stay_row for reservation in reservations for stay_row in reservation]
        return ScrapedDataset(
            anchor_date=verify.anchor_date,
            dataset_revision=verify.dataset_revision,
            scraped_at=datetime.now(timezone.utc),
            pages_scraped=pages_scraped,
            reservations=reservations_flat,
            room_types=room_types,
            rate_plans=rate_plans,
            markets=markets,
            macro_history=macro_history,
            channels=channels,
            verify=verify,
        )

    def scrape_verify(self, page: Page) -> VerifySnapshot:
        page.goto(VERIFY_URL, wait_until="networkidle", timeout=120000)
        lines = cleaned_lines(page.locator("main").inner_text())
        text = "\n".join(lines)

        anchor_match = re.search(r"as of (\d{4}-\d{2}-\d{2})", text)
        if not anchor_match:
            raise ValueError("Could not parse verify anchor date")

        return VerifySnapshot(
            anchor_date=parse_date(anchor_match.group(1)),
            dataset_revision=extract_value(lines, "dataset_revision"),
            reservation_stay_status_sha256=extract_value(
                lines, "reservation_stay_status_sha256"
            ),
            total_reservations=int(extract_value(lines, "total_reservations")),
            total_stay_rows=int(extract_value(lines, "total_stay_rows")),
            rate_plan_lookup_rows=int(extract_value(lines, "rate_plan_lookup_rows")),
            market_macro_group_history_rows=int(
                extract_value(lines, "market_macro_group_history_rows")
            ),
            cancelled_reservations=int(extract_value(lines, "cancelled_reservations")),
            provisional_row_count=int(extract_value(lines, "provisional_row_count")),
            property_date_mismatch_count=int(
                extract_value(lines, "property_date_mismatch_count")
            ),
            posted_stay_rows=int(extract_value(lines, "posted_stay_rows")),
            posted_otb_room_nights=int(extract_value(lines, "posted_otb_room_nights")),
            posted_room_revenue_before_tax=parse_decimal(
                extract_value(lines, "posted_room_revenue_before_tax")
            ),
            posted_total_revenue_before_tax=parse_decimal(
                extract_value(lines, "posted_total_revenue_before_tax")
            ),
            stly_room_nights=int(extract_value(lines, "stly_room_nights")),
            stly_total_revenue_before_tax=parse_decimal(
                extract_value(lines, "stly_total_revenue_before_tax")
            ),
        )

    def scrape_reference(
        self,
        page: Page,
    ) -> tuple[
        list[RoomTypeLookupRow],
        list[MarketCodeLookupRow],
        list[ChannelCodeLookupRow],
        list[RatePlanLookupRow],
        list[MarketMacroGroupHistoryRow],
    ]:
        page.goto(REFERENCE_URL, wait_until="networkidle", timeout=120000)

        def click_tab(label: str) -> None:
            page.get_by_role("tab", name=label).click()
            page.wait_for_timeout(150)

        click_tab("Room types")
        room_type_rows = table_rows(page.locator("table").first)
        room_types = [
            RoomTypeLookupRow(
                space_type=row[0],
                room_class=row[1],
                display_name=row[2],
                number_of_rooms=int(row[3]),
            )
            for row in room_type_rows
        ]

        click_tab("Markets")
        market_rows = table_rows(page.locator("table").first)
        markets = [
            MarketCodeLookupRow(
                market_code=row[0],
                market_name=row[1],
                macro_group=row[2],
                description=row[3],
            )
            for row in market_rows
        ]

        click_tab("Channels")
        channel_rows = table_rows(page.locator("table").first)
        channels = [
            ChannelCodeLookupRow(
                channel_code=row[0],
                channel_name=row[1],
                channel_group=row[2],
            )
            for row in channel_rows
        ]

        click_tab("Rate plans")
        rate_plan_rows = table_rows(page.locator("table").first)
        rate_plans = [
            RatePlanLookupRow(
                rate_plan_code=row[0],
                plan_family=row[1],
                is_commissionable=row[2].lower() == "true",
            )
            for row in rate_plan_rows
        ]

        click_tab("Macro history")
        macro_history_rows = table_rows(page.locator("table").first)
        macro_history = [
            MarketMacroGroupHistoryRow(
                market_code=row[0],
                valid_from=parse_date(row[1]),
                valid_to=None if row[2] == "—" else parse_date(row[2]),
                macro_group=row[3],
            )
            for row in macro_history_rows
        ]

        return room_types, markets, channels, rate_plans, macro_history

    def scrape_reservation_index(
        self, page: Page
    ) -> tuple[int, list[ReservationListRow]]:
        page.goto(RESERVATIONS_URL, wait_until="networkidle", timeout=120000)
        rows: list[ReservationListRow] = []
        pages_scraped = 0

        while True:
            wait_for_table_rows(page)
            pages_scraped += 1
            rows.extend(self.parse_reservation_list_page(page))

            next_button = page.get_by_test_id("next-page")
            if next_button.is_disabled():
                break
            next_button.click(force=True)
            wait_for_table_rows(page)

        return pages_scraped, rows

    def parse_reservation_list_page(self, page: Page) -> list[ReservationListRow]:
        parsed: list[ReservationListRow] = []
        table = page.locator("tbody tr")
        for index in range(table.count()):
            row = table.nth(index)
            cells = [clean_text(cell) for cell in row.locator("td").all()]
            href = row.locator("a").first.get_attribute("href")
            if href is None or len(cells) < 11:
                raise ValueError("Reservation list row is missing expected cells")
            parsed.append(
                ReservationListRow(
                    reservation_id=cells[0],
                    arrival_date=parse_date(cells[1]),
                    departure_date=parse_date(cells[2]),
                    nights=int(cells[3]),
                    reservation_status=cells[4],
                    market_code=cells[5],
                    channel_code=cells[6],
                    space_type=cells[7],
                    number_of_spaces=int(cells[8]),
                    adr_room=parse_decimal(cells[9]),
                    lead_time=int(cells[10]),
                    detail_path=href,
                )
            )
        return parsed

    def scrape_reservation_detail(
        self, browser: Browser, summary: ReservationListRow
    ) -> list[ReservationRecord]:
        page = browser.new_page(viewport={"width": 1440, "height": 1400})
        try:
            page.goto(f"{BASE_URL}{summary.detail_path}", wait_until="networkidle", timeout=120000)
            lines = cleaned_lines(page.locator("main").inner_text())
            field_lines = between_markers(lines, "RESERVATION FIELDS", "STAY ROWS")
            fields = pairs_to_mapping(field_lines)
            stay_rows = table_rows(page.locator("table").first)
        finally:
            page.close()

        create_datetime = parse_datetime(fields["create_datetime"])
        cancellation_datetime = (
            None
            if fields["cancellation_datetime"] == "—"
            else parse_datetime(fields["cancellation_datetime"])
        )
        guest_country = none_if_dash(fields["guest_country"])
        company_name = none_if_dash(fields["company_name"])
        travel_agent_name = none_if_dash(fields["travel_agent_name"])
        canonical_rate_plan_code = map_rate_plan_code(
            raw_code=fields["rate_plan_code"],
            market_code=fields["market_code"],
            is_walk_in=parse_bool(fields["is_walk_in"]),
        )

        records: list[ReservationRecord] = []
        for stay_row in stay_rows:
            records.append(
                ReservationRecord(
                    reservation_id=summary.reservation_id,
                    arrival_date=parse_date(fields["arrival_date"]),
                    departure_date=parse_date(fields["departure_date"]),
                    stay_date=parse_date(stay_row[0]),
                    property_date=parse_date(stay_row[1]),
                    reservation_status=fields["reservation_status"],
                    financial_status=stay_row[2],
                    create_datetime=create_datetime,
                    cancellation_datetime=cancellation_datetime,
                    guest_country=guest_country,
                    is_block=parse_bool(fields["is_block"]),
                    is_walk_in=parse_bool(fields["is_walk_in"]),
                    number_of_spaces=int(fields["number_of_spaces"]),
                    space_type=fields["space_type"],
                    market_code=fields["market_code"],
                    channel_code=fields["channel_code"],
                    source_name=fields["source_name"],
                    rate_plan_code=canonical_rate_plan_code,
                    daily_room_revenue_before_tax=parse_decimal(stay_row[3]),
                    daily_total_revenue_before_tax=parse_decimal(stay_row[4]),
                    nights=int(fields["nights"]),
                    adr_room=parse_decimal(fields["adr_room"]),
                    lead_time=int(fields["lead_time"]),
                    company_name=company_name,
                    travel_agent_name=travel_agent_name,
                )
            )
        return records


def table_rows(table: Locator) -> list[list[str]]:
    body_rows = table.locator("tbody tr")
    rows: list[list[str]] = []
    for index in range(body_rows.count()):
        row = body_rows.nth(index)
        rows.append([clean_text(cell) for cell in row.locator("td").all()])
    return rows


def wait_for_table_rows(page: Page) -> None:
    page.wait_for_selector("tbody tr", timeout=120000)
    page.wait_for_function(
        """
        () => {
          const row = document.querySelector('tbody tr');
          if (!row) return false;
          const cells = row.querySelectorAll('td');
          return cells.length > 1 && !row.innerText.includes('Loading');
        }
        """,
        timeout=120000,
    )


def cleaned_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def between_markers(lines: list[str], start: str, end_prefix: str) -> list[str]:
    try:
        start_index = lines.index(start) + 1
    except ValueError as exc:
        raise ValueError(f"Missing section marker: {start}") from exc

    collected: list[str] = []
    for line in lines[start_index:]:
        if line.startswith(end_prefix):
            break
        collected.append(line)
    return collected


def pairs_to_mapping(lines: Iterable[str]) -> dict[str, str]:
    items = list(lines)
    if len(items) % 2 != 0:
        raise ValueError("Expected an even number of label/value lines")
    return {items[index]: items[index + 1] for index in range(0, len(items), 2)}


def extract_value(lines: list[str], label: str) -> str:
    for index, line in enumerate(lines):
        if line == label:
            return lines[index + 1]
    raise ValueError(f"Missing value for {label}")


def parse_date(value: str) -> date:
    return date.fromisoformat(value)


def parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def parse_decimal(value: str) -> Decimal:
    return Decimal(value.replace(",", ""))


def parse_bool(value: str) -> bool:
    return value.lower() == "true"


def none_if_dash(value: str) -> str | None:
    return None if value == "—" else value


def map_rate_plan_code(raw_code: str, market_code: str, is_walk_in: bool) -> str:
    if is_walk_in:
        return "WALKIN"

    if raw_code in {
        "BOOKBAR",
        "CORP10BB",
        "DLY1",
        "FITBB",
        "GROUPBB",
        "ZEPHYR-CORP-25",
    }:
        return raw_code

    if raw_code in {"BOOKBARB", "EXPBARB", "EXPBARH", "EXPP"}:
        return "BOOKBAR"
    if raw_code == "BOOKPROM":
        return "PROMO1"
    if raw_code in {"DLYBB"}:
        return "DLY1"
    if raw_code in {"OCHEARLY", "OCHPERKRO"}:
        return "PROMO1"
    if raw_code in {"BARCBB", "GOORO"}:
        return "CORP10BB"

    raise ValueError(
        f"Unsupported commercial rate code {raw_code!r} for market {market_code!r}"
    )


def clean_text(locator: Locator) -> str:
    return " ".join(locator.inner_text().split())
