---
name: asof-snapshot-guardrail
description: Use get_as_of_otb for historical OTB snapshots, and warn that point-in-time answers require an approval gate and historical caveats.
---

# As-Of Snapshot Guardrail

Use `get_as_of_otb` only when the GM explicitly asks what the hotel knew at a past timestamp, for example "What did August look like as of May 1?" This is not the same as current OTB. The tool rebuilds a historical universe by checking `create_datetime`, cancellations relative to `as_of_utc`, and posted-only financial status.

Always say that this tool is human-gated because historical OTB changes the interpretive frame and can be misused if the timestamp is wrong. Never answer an as-of question from `get_otb_summary`, because current OTB can include bookings that did not exist yet or exclude reservations cancelled later.

Guardrail: do not include cancelled or provisional rows by default just because the user asks for a historical month. The historical rule is still posted-only, and cancelled rows stay in only if they cancelled after the requested as-of time.

