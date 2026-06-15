---
name: block-concentration-review
description: Use get_block_vs_transient_mix to evaluate block dependency, top-company concentration, and whether group business is crowding out healthier mix.
---

# Block Concentration Review

Use `get_block_vs_transient_mix` whenever the GM asks about group business, block exposure, or company concentration. Start with the block room-night and revenue shares, then move immediately to whether the top companies are carrying an unhealthy amount of the month.

Judgment rules:

- If `block_share_of_revenue > 0.55`, say the month is block-led and recommend checking shoulder-night controls, displacement, and whether premium transient demand still has enough inventory to book.
- If `top3_company_revenue_share > 0.45`, flag concentration and recommend reviewing wash, cut-off dates, and secondary account diversification before taking more low-quality block demand.
- If block room-night share is high but block revenue share is materially lower, explain that the hotel may be filling with lower-rated group business and should review rate integrity before adding more blocks.

Use null `company_name` as `Transient`, exactly like the tool does. Do not query raw reservations or invent company rollups outside the tool result.

