# Decisions
## 001 — Registry gate syntax normalization
The registry gate syntax must be normalized to `<attr> <op> <typed_literal>` before D3, because the supplied registry mixes `== 1` and `is true` for the same condition.

## 002 — Normalized all gates in registry
Normalized all gates in mapping/registry.yaml to `<attr> <op> <typed_literal>` format. Changed 10 gates in total (added quotes around string literals, changed 'is true' to '== true').

## 003 — EXPORT_COLUMNS (1891) vs IMPORTABLE_COLUMNS (1889)
Date: 2026-07-31  Session: D01  Decided by: human
D01's original gate said 1889. The parser produced 1891. Root cause:
exportFieldNames excludes calc/file/descriptive; a CSV data export does not.
Both counts are correct for their purpose.
  EXPORT_COLUMNS     = 1891, everything a data export contains
  IMPORTABLE_COLUMNS = 1889, what exportFieldNames returns and what may be
                       POSTed to the import API
This dictionary has 2 calc fields and zero file/descriptive fields, so the
delta is exactly 2.
Consequence: D13 must compare against IMPORTABLE_COLUMNS. Comparing against
EXPORT_COLUMNS would report 2 phantom columns forever.

## 004 — Broken Gates in Registry Fix
Date: 2026-07-31  Session: D14  Decided by: human
Fixed four broken `conditional_text` gates that referenced attributes without emitting an event scope (e.g., `other_mccd_used_ems_v2`, `specify_other_mccd_ed_v2`, `mccd_obstacle_other`, and `other_mccd_adjust_v2`). The gates were fixed by explicitly declaring `event_type` and (if needed) `where` scope. A validator will be added to ensure this pattern doesn't recur.

## 005 — Unquoted yes/no booleans in YAML
Date: 2026-07-31  Session: D14  Decided by: agent
PyYAML silently evaluates unquoted 'yes' and 'no' in registry vocabularies as python booleans `True` and `False`. To accurately pass these exact keys down to the prompt contract, we implemented logic that reverses boolean serialization (`True -> "yes"`, `False -> "no"`) in `emit_contract.py` and `emit_python.py`. This ensures no `TypeError` occurs during set-operations and proper symbolic matching is maintained in `tests/test_coverage.py`.

## 006 — Interval Type Leak in Event Types
Date: 2026-07-31  Session: A01  Decided by: human
`interval_type` values (cci, rosc, vent_delay) must not leak into the derived `event_types` used for `redcap_feeding`. Separate `event_types_from_rules` and `event_types_from_hints` derivation lists are introduced, and we assert that interval types never overlap with event types.
