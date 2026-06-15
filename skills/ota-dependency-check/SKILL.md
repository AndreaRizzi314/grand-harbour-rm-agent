---
name: ota-dependency-check
description: Use get_segment_mix to judge OTA and retail dependency, especially when share_of_revenue suggests channel concentration risk.
---

# OTA Dependency Check

Use `get_segment_mix` for dependency questions such as "Are we too reliant on OTA?" or "What is driving retail revenue?" Focus on `share_of_revenue`, then check whether room-night share tells the same story. The denominator is the filtered stay-month population returned by the tool; do not mix denominators across separate queries.

Judgment rules:

- If OTA `share_of_revenue > 0.35`, say dependence is elevated and recommend a direct-demand action, such as tightening OTA promotions, protecting direct parity, or shifting remarketing budget toward brand channels.
- If OTA revenue share exceeds OTA room-night share by more than 5 percentage points, explain that OTA is not just large, it is monetizing above-average spend, which makes abrupt closure riskier.
- If Retail macro-group demand is dominant but split across multiple non-OTA segments, say the risk is manageable and avoid overstating a pure OTA problem.

Guardrail: a missing OTA row in a month is a data-quality alarm, not a business conclusion. Treat that as a broken ETL or wrong filter until proven otherwise.

