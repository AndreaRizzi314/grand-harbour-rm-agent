# ATTESTATION.md (Phase 0)

Copy this file to your solution repository as `ATTESTATION.md` and fill it in
before starting Phase 1. Keep answers concise - a few sentences per prompt.

---

## Candidate

- Name: Andrea Rizzi 
- Repository URL: https://github.com/AndreaRizzi314/grand-harbour-rm-agent
- Date: 15/06/2026

---

## Comprehension prompts

### 1. Fact-table grain

In one sentence, what is the grain of `reservations_hackathon`?

> Your answer: The grain is one row per `reservation_id x stay_date`

### 2. Revenue columns

Name the two revenue columns and when to use each.

> Your answer: The two revenue columns are `daily_room_revenue_before_tax` for room only analysis such as ADR and room revenue, and `daily_total_revenue_before_tax` for total spend analysis that includes non-room components like packages or breakfast spendings.

### 3. Row vs reservation

Give one example question where counting rows would be wrong.

> Your answer: "How many reservations do we have for July?" would be wrong if I counted rows, because one multi-night reservation creates multiple stay-date rows.

### 4. Schema fields

Is there an `otel_challenge_token` column in the official schema? If so, what is it used for?

> Your answer: No, there is no `otel_challenge_token` column in the official schema.

### 5. Default OTB filters

Which `reservation_status` and `financial_status` values are excluded from default OTB?

> Your answer: Default OTB excludes `reservation_status = 'Cancelled'` and `financial_status = 'Provisional'` unless the question explicitly asks for tentative or cancelled business.

### 6. Stay date vs property date

When can `property_date` differ from `stay_date`, and which field drives monthly OTB?

> Your answer: `property_date` can differ from `stay_date` on night-boundary or audit rows, but monthly OTB should still be driven by stay_date, because OTB is about the night being stayed, not the hotel's accounting business date.

### 7. Point-in-time OTB

How does `as_of_utc` change which cancelled rows are included in `get_as_of_otb`?

> Your answer: `as_of_utc` changes the universe in two ways. A row only exists if `create_datetime <= as_of_utc`, and a cancelled row is still counted only if it had not yet been cancelled at that moment, meaning `cancellation_datetime > as_of_utc` or null. So `get_as_of_otb` reconstructs what was actually on the books then, not what is visible now.

### 8. Block vs transient

How does `is_block` affect a "group vs transient mix" question?

> Your answer: `is_block = true` identifies block or group business, while `is_block = false` is treated as transient business.

### 9. List pagination

How many reservations does the data site show per list page?

> Your answer: The data site shows 100 reservations per list page.

### 10. Pagination completeness

How will you prove you did not miss the last list page during ETL?

> Your answer: I would prove completeness in three ways. First scrape until the final page control is exhausted, persist all scraped reservation IDs into `etl/SCRAPE_MANIFEST.json`, and reconcile both `reservation_ids_count` and `reservation_ids_sha256` against the loaded database and /verify. That makes a silent missed last page very hard to hide, because the count and hash would fail even if the ETL still looked successful.

### 11. Tool grain

For `get_otb_summary`, what is the difference between `row_count` and `reservation_count`?

> Your answer: `row_count` is the number of filtered stay-date rows in the month, while `reservation_count` is the number of distinct `reservation_id` values.

### 12. Human-in-the-loop

Why must `get_as_of_otb` be gated behind approval, and what goes wrong if it is not?

> Your answer: `get_as_of_otb` should be gated because it answers a higher risk historical reconstruction question, not a simple current state query. If it is not gated, the agent can easily answer the wrong timestamped question, compare current OTB to historical OTB incorrectly, or run analysis without the user confirming that the chosen as_of_utc is really the decision frame they want.

### 13. Skill vs tool

Name one revenue-manager question that should load a **skill** but call **`get_segment_mix`**, not raw SQL.

> Your answer: "Were we too dependent on OTA in August?" should load an OTA dependency skill and call `get_segment_mix`, not raw SQL.

---

## ETL design (one line)

Describe pagination strategy + idempotency approach + **anchor date** you will
scrape against (must match `/verify` on load day).

> Your answer: Use Playwright to paginate the rendered reservation list 100 rows at a time and open every detail page, then run an idempotent truncate-and-reload ETL with `load_manifest` hashing, scraping against the same-day `/verify` anchor date of 15/06/2026.
