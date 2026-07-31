# Decisions
001 - The registry gate syntax must be normalized to `<attr> <op> <typed_literal>` before D3, because the supplied registry mixes `== 1` and `is true` for the same condition.
002 - Normalized all gates in mapping/registry.yaml to `<attr> <op> <typed_literal>` format. Changed 10 gates in total (added quotes around string literals, changed 'is true' to '== true').
