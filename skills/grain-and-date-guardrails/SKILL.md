---
name: grain-and-date-guardrails
description: Use get_otb_summary and get_segment_mix with strict row-versus-reservation and stay-date-versus-property-date guardrails.
---

# Grain And Date Guardrails

Use `get_otb_summary` or `get_segment_mix` when the GM asks a normal OTB or mix question, but keep three traps front of mind.

First, stay rows are not reservations. A multi-night reservation produces multiple stay rows, and multi-room reservations inflate room nights beyond both rows and reservations. Second, monthly OTB belongs on `stay_date`, not `property_date`; property-date mismatches exist in the dataset and can quietly distort monthly reporting if you pivot on the wrong field. Third, default OTB excludes both cancelled and provisional rows unless the user explicitly asks to broaden the universe.

If any answer risks crossing those wires, say the caveat out loud before giving the conclusion. Guardrails are part of the answer, not optional footnotes.

