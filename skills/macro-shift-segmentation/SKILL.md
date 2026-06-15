---
name: macro-shift-segmentation
description: Use get_segment_mix to interpret effective macro groups correctly when market classifications change over time by stay date.
---

# Macro Shift Segmentation

Use `get_segment_mix` when the GM asks for segment mix by macro group or when a month appears to move between Retail, Leisure Group, Corporate, or MICE. The key rule is that `effective_macro_group` is stay-date aware. A market's static lookup category can differ from the correct classification for a given stay month.

For this dataset, treat `PROM` carefully because its macro-group history changes effective `2025-06-01`. If a month after that date shows `PROM` demand, do not narrate it as Retail without checking the effective macro group returned by the tool. When segment mix shifts because of classification history rather than true booking behavior, explain that distinction so the GM does not mistake taxonomy drift for commercial momentum.

Never bypass the tool and never segment by `property_date` for monthly mix work.

