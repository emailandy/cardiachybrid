# BUILD_ORDER.md — canonical sequence

Phase 0  Gold set (human, parallel)         — no agent tasks
Phase 1  D0 D1 D2 D3 D4 D14                 — schema spine
Phase 2  Anchor cards ×24                   — mostly clinical lead
Phase 3  Constitution v2, P1 P2 P3, builder — app layer
Phase 4  D5 D6 D12                          — reducer   ← D12 IS THE MILESTONE
Phase 5  D7 D8                              — warehouse
Phase 6  D9 D10 P4 P5 D11                   — loop closure
Phase 7  D13 + eval harness                 — hardening
Sensor Layer: S00 S01 S02 S03 S07           — evidence-driven reprioritization of S07 (S2 fusion) directly after S03

## Hard dependencies — violating these wastes days
- D14 MUST precede any prompt work. It defines the attribute contract the
  prompts consume. Prompts written first will invent attribute names the
  registry doesn't recognize.
- Phase 3 MUST precede D5. The reducer interprets real event streams; writing
  it against imagined ones produces code for cases that never occur.
- D12 is the coverage checkpoint. If the project stops anywhere, stop after D12.

## Gates — do not advance until green
after D1   parser prints exactly `909 1889`
after D3   manifest: 911 vars / 1891 cols / unmapped []
after D14  every registry `emit:` key present in contract exactly once
after D12  synthetic maximal emits all 1,891 export columns
after D7   v_audit_missing_fields returns zero rows
