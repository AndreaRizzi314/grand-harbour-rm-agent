---
name: pickup-pace-diagnosis
description: Use get_pickup_delta to judge recent booking pace for future stays and recommend action when pickup is too weak or too concentrated.
---

# Pickup Pace Diagnosis

Use `get_pickup_delta` when the GM asks what changed recently, what booked in the last 7 or 30 days, or whether future demand is building. Always remind yourself that pickup windows use `create_datetime`, not `stay_date`; the stay filter only limits which future nights receive the booked demand.

Judgment rules:

- If `new_total_revenue` over the last 7 days is less than 10% of the month's current OTB revenue, describe pickup as soft and recommend protecting rate only if the segment mix is healthy; otherwise review need periods and conversion tactics.
- If one segment contributes more than 40% of `new_total_revenue`, call out concentration risk and recommend balancing that demand with direct or corporate activity rather than simply chasing more of the same.
- If `new_reservations` is low but `new_room_nights` is still strong, explain that the pace is being carried by longer-stay or multi-room bookings rather than broad-based transient demand.

Do not answer pickup questions with current OTB alone. Pace is about when the business booked.

