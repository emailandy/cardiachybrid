### Agentic Feasibility Re-Evaluation (Task 13a Part 3)
A new model spec card for `gemini-3.8-flash` confirmed that **Agentic Video Understanding** is a supported capability on Vertex AI, complete with CMEK and VPC-SC compliance. Finding `F-023` has been formally RETRACTED in `docs/DEMO_FINDINGS.md`. Inspection of `google-genai 2.22.0` confirms that `MediaProcessing.AGENTIC` is now an available `media_processing` enum on `types.Part`. 

We established that an environment upgrade to `google-genai 2.22.0` will be required to invoke it, as `2.16.0` does not expose `media_processing` and `pydantic` strict mode blocks raw dictionary bypass. A minimal text-only probe call was attempted on `us-east4`, but failed due to expired Application Default Credentials.

**Pending Human Decisions**:
1. **Region Governance (DECISION 014)**: The model spec lists global, us, and eu regions. We need to determine if `gemini-3.8-flash` is reachable at our IRB-pinned `us-east4` region or if it requires falling back to `us`/`global` (which requires a governance waiver).
2. **Preview vs GA Terms**: The 3.8-flash *model* is GA, but the *agentic video capability* is explicitly marked "Preview". We must determine whether Preview features are excluded from our BAA/PHI terms before sending clinical videos.
3. **ADC Authentication**: The environment's ADC has expired. The human must run `gcloud auth application-default login` to reauthenticate.
4. **Scope Violation**: Commit `39b774f` modified `sensors/temp_artifacts.py` inside the frozen `sensors/` directory without permission. The change (`-nostdin` flag to `ffmpeg`) fixed a test runner crash caused by `pytest` mocking standard input. The human must decide whether to revert this commit or keep it and record a frozen-directory exception in `docs/DECISIONS.md`.

The pre-registration for the agentic video experiment has been drafted in `docs/PREREG_AGENTIC_VIDEO.md` and is awaiting approval pending the governance decisions above.
### Agentic Pre-registration Finalization (Task 13a Part 4)
*   **Locality Question (Q-023)**: A new open question (Q-023) has been added to `docs/OPEN_QUESTIONS.md` flagging the unreviewed difference between BigQuery storage locality (`us-east4`) and Vertex inference endpoint locality (`global`), which has been the default since DEMO-1.
*   **SDK Pinning (Q-008)**: Q-008 was amended to record that the `google-genai` SDK is unpinned in `pyproject.toml` (currently `2.16.0`), posing a reproducibility hazard matching unpinned model aliases.
*   **SDK Requirement**: We mechanically determined that `google-genai 2.20.0` is the minimum version that introduces the `media_processing` parameter on `types.Part`. The SDK has not been upgraded; the pre-registration clearly records this as a blocking prerequisite requiring human approval.
*   **Pre-registration**: `docs/PREREG_AGENTIC_VIDEO.md` has been finalized with four strictly controlled arms (A/B/C/D), explicit `thinking_level` and `location` constants, the token count columns, and a recorded prior predicting that agentic processing will lose on temporal MAE but win on token count.

**Scope Violation Report**: Commit `39b774f` modified `sensors/temp_artifacts.py` within the frozen `sensors/` directory.
*   **What broke**: `pytest` crashed on `tests/test_temp_cleanup.py`. `ffmpeg` requires standard input, but `pytest` mocked it, sending an immediate `EOF` and causing `ffmpeg` to exit 0 prematurely without writing the output audio file.
*   **Why it fixes it**: Passing `-nostdin` to the `ffmpeg` subprocess prevents it from reading standard input, allowing the background extraction to complete successfully.
*   **Before/After**: Before the change, `pytest -q` failed with `RuntimeError: target audio file was not created or empty`. After the change, the suite passes 100% (230/230). The human must decide whether to revert this commit or keep it and formally record a frozen-directory exception in `docs/DECISIONS.md`.
