---
name: otb-summary-triage
description: Use get_otb_summary to frame month-level OTB, separate stay rows from reservations, and explain what changed commercially.
---

# OTB Summary Triage

Use `get_otb_summary` first when the GM asks a broad monthly question such as "How is July pacing?" or "What's on the books for August?" Start by stating the stay month, room nights, total revenue, and reservation count, and explicitly keep the grain straight: stay rows are not reservations, and room nights are `sum(number_of_spaces)`.

If `room_revenue / total_revenue < 0.90`, call out that non-room spend is material and the answer should not read like a rooms-only story. If `room_nights / reservation_count > 2.5`, mention that length of stay or multi-room demand is supporting the month. If the GM asks for "OTB" without qualification, keep cancelled and provisional rows out and say that default policy plainly.

Never switch to `property_date` for monthly OTB. Stay-month analysis belongs on `stay_date`. If the question sounds historical rather than current, stop and route to `get_as_of_otb` instead of faking a point-in-time answer from current OTB.

