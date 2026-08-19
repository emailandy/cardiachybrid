# prompts/ — RUNTIME PROMPTS (application source code, not documentation)

## This directory is intentionally empty until A01.

Every file here is bound to `generated/extraction_contract.json` (produced by
D14). Anchor cards must cover exactly the attributes the contract declares;
`VERSIONS.yaml` pins a contract version; pass templates inject contract slices.

Writing prompts before the contract exists means inventing attribute names the
reducer will not recognize — which produces silent nulls that look like honest
abstentions. That failure mode is the reason this directory is gated.

## Source content is staged in `_inbox/`
  _inbox/20_constitution.md      → A02 → system/constitution.v2.0.md
  _inbox/21_passes.md            → A04, A06 → passes/
  _inbox/22_contract_examples.md → A03 reference shape

## Build order
  D14 → A01 (manifest + registry) → A02 (constitution) → A03 (anchors)
      → A04 (P1/P2) → A05 (builder) → A06 (P3–P5)

## Do not add a file here outside an A0x task.
CODEOWNERS requires clinical-lead review on this path. A prompt change alters
clinical data extraction exactly the way a reducer change does.