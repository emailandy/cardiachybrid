# Decisions
001 - The registry gate syntax must be normalized to `<attr> <op> <typed_literal>` before D3, because the supplied registry mixes `== 1` and `is true` for the same condition.
002 - Normalized all gates in mapping/registry.yaml to `<attr> <op> <typed_literal>` format. Changed 10 gates in total (added quotes around string literals, changed 'is true' to '== true').

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
