# Open Questions

## CLINICAL — awaiting clinical lead
Q-001 CCI truncation policy when >30 
  - options: TBD 
  - default: 30 longest by duration
  - owner: clinical lead
  - status: OPEN
  - blocks: TBD

Q-002 new_pad_position when repositioned twice 
  - options: TBD
  - default: last
  - owner: clinical lead
  - status: OPEN
  - blocks: TBD

Q-003 mccd_obstacles obesity/cachexia 
  - options: TBD
  - default: hard-suppressed, GOV-07
  - owner: clinical lead
  - status: OPEN
  - blocks: TBD

Q-004 MCCD adjustment window with multiple adjustments 
  - options: TBD
  - default: envelope
  - owner: clinical lead
  - status: OPEN
  - blocks: TBD

Q-005 intub_assist bougie + fiberoptic 
  - options: TBD
  - default: bougie precedence
  - owner: clinical lead
  - status: OPEN
  - blocks: TBD

Q-006 TEAM autonomy threshold 
  - options: TBD
  - default: always human until ICC ≥ 0.75
  - owner: clinical lead
  - status: OPEN
  - blocks: TBD

Q-009 — All 39 anchor cards require clinical review for accuracy before
production use. Structural validation (check_anchors) passes; clinical
validation has not occurred. Blocks: first production run, not development.
Owner: clinical lead.  Status: OPEN.

Q-012 CCF denominator definition
  - options: (a) first compression -> last compression, (b) patient arrival -> termination or ROSC, (c) first compression -> termination, excluding sustained-ROSC periods
  - default: candidate (c) first compression -> termination excluding sustained ROSC (configured in config/metrics.yaml)
  - owner: clinical lead
  - status: OPEN
  - blocks: D10 clinical sign-off

## OPERATIONAL — awaiting human
Q-007 — Is the artifact-foundry-prod pip index an institutional control?
Inherited pip config points at
us-python.pkg.dev/artifact-foundry-prod/ah-3p-staging-python, which lacks
setuptools and pytest.
(a) Deliberate supply-chain control → REVERT the venv override; request
    upstream PyPI passthrough or explicit mirroring from the platform team.
(b) Stale/unrelated config → the venv-scoped override is the permanent fix.
Interim: venv-scoped override to pypi.org, repo-local, no global change.
Owner: human / platform team.  Status: OPEN.  Blocks: nothing (workaround
in place), but must be resolved before any production deployment.

Q-008 Pin exact Gemini model version strings before the first production run.
-latest aliases make historical runs unreproducible.
  - options: specific model strings (e.g. gemini-1.5-pro-001)
  - default: TBD
  - owner: human
  - status: OPEN
  - blocks: production deployment

Q-010 BigQuery Terraform Region Selection.
Multi-region US vs single region (e.g. us-east4 for data-residency compliance).
  - options: (a) Multi-region US (cheaper/simpler), (b) Single region e.g. us-east4
  - default: None (must be explicitly chosen by human; no silent default)
  - owner: human
  - status: RESOLVED (SINGLE REGION, us-east4)
  - blocks: nothing

Q-011 text_embedding storage in fact_utterance.
  - status: DEFERRED (not OPEN)
  - note: "Embedding storage deferred to the retrieval layer. When added, requires separate governance review — derived embeddings of clinical audio are PHI and voice embeddings may be biometric identifiers."


## RESOLVED
**T-001 (A01)**: What is the correct value for 'Scope: MODIFY'? (specs.yaml does not determine this).
**T-002 (A01)**: What is the correct value for 'Scope: READ'? (specs.yaml does not determine this).
**T-003 (A01)**: What is the correct value for 'Self-review Q2'? (specs.yaml does not determine this).
**T-004 (A01)**: What is the correct value for 'Self-review Q3'? (specs.yaml does not determine this).
**T-005 (A05)**: What is the correct value for 'Scope: MODIFY'? (specs.yaml does not determine this).
**T-006 (A05)**: What is the correct value for 'Scope: READ'? (specs.yaml does not determine this).
**T-007 (A05)**: What is the correct value for 'Self-review Q2'? (specs.yaml does not determine this).
**T-008 (A05)**: What is the correct value for 'Self-review Q3'? (specs.yaml does not determine this).
**T-009 (A04)**: What is the correct value for 'Scope: MODIFY'? (specs.yaml does not determine this).
**T-010 (A04)**: What is the correct value for 'Scope: READ'? (specs.yaml does not determine this).
**T-011 (A04)**: What is the correct value for 'Self-review Q2'? (specs.yaml does not determine this).
**T-012 (A04)**: What is the correct value for 'Self-review Q3'? (specs.yaml does not determine this).
**T-013 (A03)**: What is the correct value for 'Scope: MODIFY'? (specs.yaml does not determine this).
**T-014 (A03)**: What is the correct value for 'Scope: READ'? (specs.yaml does not determine this).
**T-015 (A03)**: What is the correct value for 'Self-review Q2'? (specs.yaml does not determine this).
**T-016 (A03)**: What is the correct value for 'Self-review Q3'? (specs.yaml does not determine this).
**T-017 (A02)**: What is the correct value for 'Scope: MODIFY'? (specs.yaml does not determine this).
**T-018 (A02)**: What is the correct value for 'Scope: READ'? (specs.yaml does not determine this).
**T-019 (A02)**: What is the correct value for 'Self-review Q2'? (specs.yaml does not determine this).
**T-020 (A02)**: What is the correct value for 'Self-review Q3'? (specs.yaml does not determine this).
**T-021 (A03b)**: What is the correct value for 'Scope: MODIFY'? (specs.yaml does not determine this).
**T-022 (A03b)**: What is the correct value for 'Scope: READ'? (specs.yaml does not determine this).
**T-023 (A03b)**: What is the correct value for 'Self-review Q2'? (specs.yaml does not determine this).
**T-024 (A03b)**: What is the correct value for 'Self-review Q3'? (specs.yaml does not determine this).
**T-025 (A06)**: What is the correct value for 'Scope: MODIFY'? (specs.yaml does not determine this).
**T-026 (A06)**: What is the correct value for 'Scope: READ'? (specs.yaml does not determine this).
**T-027 (A06)**: What is the correct value for 'Self-review Q2'? (specs.yaml does not determine this).
**T-028 (A06)**: What is the correct value for 'Self-review Q3'? (specs.yaml does not determine this).
**T-029 (D07a)**: What is the correct value for 'Self-review Q2'? (specs.yaml does not determine this).
**T-030 (D07a)**: What is the correct value for 'Self-review Q3'? (specs.yaml does not determine this).
**T-031 (D02)**: What is the correct value for 'Self-review Q2'? (specs.yaml does not determine this).
**T-032 (D02)**: What is the correct value for 'Self-review Q3'? (specs.yaml does not determine this).
**T-033 (D12)**: What is the correct value for 'Self-review Q2'? (specs.yaml does not determine this).
**T-034 (D12)**: What is the correct value for 'Self-review Q3'? (specs.yaml does not determine this).
**T-035 (D06)**: What is the correct value for 'Self-review Q2'? (specs.yaml does not determine this).
**T-036 (D06)**: What is the correct value for 'Self-review Q3'? (specs.yaml does not determine this).
**T-037 (D07)**: What is the correct value for 'Self-review Q2'? (specs.yaml does not determine this).
**T-038 (D07)**: What is the correct value for 'Self-review Q3'? (specs.yaml does not determine this).
**T-039 (D03)**: What is the correct value for 'Self-review Q2'? (specs.yaml does not determine this).
**T-040 (D03)**: What is the correct value for 'Self-review Q3'? (specs.yaml does not determine this).
**T-041 (D13)**: What is the correct value for 'Self-review Q2'? (specs.yaml does not determine this).
**T-042 (D13)**: What is the correct value for 'Self-review Q3'? (specs.yaml does not determine this).
**T-043 (D08)**: What is the correct value for 'Self-review Q2'? (specs.yaml does not determine this).
**T-044 (D08)**: What is the correct value for 'Self-review Q3'? (specs.yaml does not determine this).
**T-045 (D09)**: What is the correct value for 'Self-review Q2'? (specs.yaml does not determine this).
**T-046 (D09)**: What is the correct value for 'Self-review Q3'? (specs.yaml does not determine this).
**T-047 (D04)**: What is the correct value for 'Self-review Q2'? (specs.yaml does not determine this).
**T-048 (D04)**: What is the correct value for 'Self-review Q3'? (specs.yaml does not determine this).
**T-049 (D14)**: What is the correct value for 'Self-review Q2'? (specs.yaml does not determine this).
**T-050 (D14)**: What is the correct value for 'Self-review Q3'? (specs.yaml does not determine this).
**T-051 (D10)**: What is the correct value for 'Self-review Q2'? (specs.yaml does not determine this).
**T-052 (D10)**: What is the correct value for 'Self-review Q3'? (specs.yaml does not determine this).
**T-053 (D01)**: What is the correct value for 'Self-review Q2'? (specs.yaml does not determine this).
**T-054 (D01)**: What is the correct value for 'Self-review Q3'? (specs.yaml does not determine this).
**T-055 (D11)**: What is the correct value for 'Self-review Q2'? (specs.yaml does not determine this).
**T-056 (D11)**: What is the correct value for 'Self-review Q3'? (specs.yaml does not determine this).
**T-057 (D05)**: What is the correct value for 'Self-review Q2'? (specs.yaml does not determine this).
**T-058 (D05)**: What is the correct value for 'Self-review Q3'? (specs.yaml does not determine this).
