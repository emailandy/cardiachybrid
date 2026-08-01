# PROMPTS & PASSES DESIGN NOTES

## Anchor slicing — what A05 must solve
Full library: 39 cards, ~115 KB, ~29K tokens.
Video at fps:2 over an 8-min window: ~248K tokens.
Per case: ~7 windows × k=3 = 21 P1 calls.
Carrying the full library costs ~600K redundant input tokens per case and
cannot be cached, because the slice differs per window.

THE RISK: a card omitted from a slice makes that event type UNEMITTABLE in
that window. Silent, total recall loss for that type — not degradation.

Therefore selection must be recall-biased:
  - always include: cards for event types the sensor tracks have already
    flagged as present (compression intervals, device-audio hits)
  - always include: high-frequency types regardless of pre-scan
    (compression_interruption, medication_administration, pulse_check,
    rhythm_check) — these occur in nearly every window
  - conditionally include: types with a keyword or sensor trigger in this
    window
  - never omit on token pressure alone. If the budget binds, split the
    window rather than drop a card.
Log the selected set per call so a missed event can be traced to a slicing
decision rather than a model failure.
