Room nights are `sum(number_of_spaces)` at the stay-date row grain, so one reservation can produce multiple stay rows and multiple room nights. Stay rows are individual `reservation_id × stay_date` rows. Reservations are `count(distinct reservation_id)` in the filtered universe.

Default OTB means future-facing stay analysis with `reservation_status <> 'Cancelled'` and `financial_status = 'Posted'`; provisional rows stay out unless the question explicitly asks for tentative business. All monthly OTB tools filter on `stay_date`, never `property_date`, and the anchor date comes from the same scrape day used for `/verify`.

Pickup windows use `create_datetime` and start at Europe/London local midnight for `now - booking_window_days`, then compare in UTC because the fact timestamps are stored in UTC.

Effective macro group is the stay-date-aware segment label from `market_macro_group_history`; it can differ from the static `market_code_lookup.macro_group` when a market changes classification over time, such as `PROM` shifting from `Retail` to `Leisure Group` effective `2025-06-01`.

Room-type ADR is `sum(daily_room_revenue_before_tax) / sum(number_of_spaces)` by `space_type` over posted, non-cancelled stay-date rows. Cancelled-business views must state whether the month is filtered by `stay_date` (cancelled stays for that month) or `cancellation_datetime` (cancellation activity during that month).

Company concentration ranks posted, non-cancelled stay-date rows by `company_name`, with `Transient` shown as an explicit bucket unless the user asks for account-only concentration. Corporate share defaults to effective macro group `Corporate`; corporate group blocks can be included explicitly with a separate flag.
