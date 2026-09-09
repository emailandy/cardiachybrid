## Pre-registration: Agentic Video Feasibility Screening Gate (Task 13a)

### Prerequisites & Invocation Mechanism (SDK Bypass)
*   **SDK Upgrade Cancelled**: We will NOT upgrade `google-genai`. Instead, execution will bypass the SDK's `types.Part` Pydantic validation via direct REST calls.
*   **Constants**:
    *   `location="global"` (matches existing pipeline default in `pipeline/vertex_client.py:45`).
    *   `api_version="v1beta1"` (required for agentic).
    *   `transport="REST"` (to bypass `google-genai 2.16.0` validation).
    *   `thinking_level`: **NONE**. Sending `thinkingLevel="MEDIUM"` (as documented in Google's samples) returns HTTP 400 (`Unknown name "thinkingLevel"`). This is a recorded documentation defect; `thinking_level` is omitted from all arms.
    *   `responseSchema` = ON for all arms (mandatory).

### 1. Hypothesis, Mechanism & Expected Prior
**Hypothesis**: Per F-008/F-010, the pipeline already assigns candidate generation to the LLM and temporal precision to deterministic sensors, so the only channel where agentic mode could materially matter is RECALL at the P1 harvest / union-of-k stage. This experiment tests whether agentic processing (`mediaProcessing="AGENTIC"`) widens the candidate net compared to fixed-rate frame extraction (`STATIC`), rather than whether it improves timing.
**Expected Prior**: 
*   **Token Efficiency**: Agentic token cost is LOAD-DEPENDENT. A paired measurement on `simvideo2.mp4` (1363s) showed that for a trivial prompt, agentic used 425x FEWER tokens than static (292 vs 124,146). However, for an exhaustive extraction prompt, agentic entered a high-token tool-use loop consuming ~2.2x MORE tokens than static (~276,328 vs ~124,126). Static pays a flat full-ingest toll; agentic is cheaper for simple questions but more expensive for exhaustive exploration. *(Retraction: The previous prediction that agentic would strictly lose on token efficiency was based on an invalid unpaired comparison and is hereby retracted. This highlights the value of pre-registering priors.)*
*   **Temporal Precision**: Google routes static mode for *frame-level precision*. The prior remains that agentic will LOSE on temporal MAE. We will not tune prompts to rescue agentic if it loses on precision.

### 2. Prior Exposure Disclosure
Before this design was finalized, a single unstructured, non-schema probe on `simvideo2.mp4` under agentic mode was conducted. It returned a partial reasoning fragment referencing "pads not charging" and a candidate window near "10:00-10:30", but no final shock list was produced and no ground-truth comparison was made. This experiment design was fixed before any ground-truth comparison occurred.

### 3. Experimental Arms (Holding Model Constant)
To rigorously isolate processing mode, the model is held constant at `gemini-3.8-flash`. `simvideo2.mp4` (non-PHI manikin footage) will be used.
*   **Arm S**: `gemini-3.8-flash`, `mediaProcessing="STATIC"`, `responseSchema` ON, `k=5` draws.
*   **Arm A**: `gemini-3.8-flash`, `mediaProcessing="AGENTIC"`, `responseSchema` ON, `k=5` draws.

*(Note: The previously proposed 4-arm matrix comparing 3.6 vs 3.8 has been moved to Future Work to avoid confounding mode with model upgrades).*

### 4. Parsing Contract & `step_list` Handling
Agentic responses emit opaque internal reasoning parts alongside the requested output.
**Contract**: The response parser must iterate over all parts. Parts lacking a `text` key (thought/step parts) **MUST be filtered out**. Remaining text parts will be concatenated and parsed via `json.loads`. Failure to filter will cause internal reasoning to be silently absorbed as data.

### 5. Target & The Ground-Truth Precision Caveat (Screening Gate)
**Target**: The 5 human-adjudicated shocks. These will be read dynamically from `fixtures/ground_truth_simvideo2.json`, not hardcoded.
**Ground-Truth Precision (Recall-Only Scoping)**: The ground-truth timestamps have a precision of roughly ±3s. Recall is scored at ±3.0s tolerance. Any temporal precision difference below this threshold is unmeasurable annotation noise. Therefore, this experiment scopes claims to **RECALL ONLY**. Temporal MAE will be reported **DESCRIPTIVELY ONLY** and will not be used in the win condition.

### 6. Evaluation Metrics
Evaluations will be per-arm, per-draw to capture stochastic spread (`k=5`).

**Table: Instantaneous Events (Shocks)**
| Metric | Arm S (`k=1..5` spread & mean) | Arm A (`k=1..5` spread & mean) |
|---|---|---|
| True Positives (Recall @ ±3.0s) | | |
| False Positives & False Negatives | | |
| Temporal MAE (s) (Descriptive Only) | | |
| totalTokenCount | | |
| toolUsePromptTokenCount | | |
| Latency & Cost | | |

### 7. Screening Gate Criteria & Asymmetric Interpretation
This is a SCREENING GATE, not an accuracy evaluation. Given `n=1` case and `k=5` draws, no outcome can establish production accuracy (refer to Q-017 for the 25-case accuracy standard). The maximum valid claim is a mode preference on a single manikin video.

**Asymmetric Interpretation Rule**:
*   **Decisive Negative (Falsification)**: If agentic is CLEARLY WORSE or EQUAL to static in True Positive rate. Stop. Do not revisit agentic until GA. *Rationale*: `simvideo2` is the easy case (burned-in timecode, controlled lighting, mechanical CPR, no PHI occlusion). Failure on clean manikin footage generalizes downward to messy real ED footage with high confidence.
*   **Indeterminate**: Any result that meets neither the Win condition nor the Falsification condition. This will be reported as "no measurable difference" with no recommendation for adoption, and testing will stop. No prompt tuning or re-running will be conducted to break ties.
*   **Win / Adopt**: Arm A's median True Positive (TP) count across `k=5` draws strictly exceeds Arm S's median TP count by >= 1 shock, AND Arm A's minimum TP count across all 5 draws is >= Arm S's median TP count (ensuring the gain is not an artifact of a single outlier draw). Temporal MAE is descriptive only and excluded from this condition. Cherry-picking a "best-of-5" single draw is strictly forbidden. **If agentic is CLEARLY BETTER, this does NOT license adoption. The ONLY claim permitted is "warrants evaluation on the Q-017 gold set."**

**Cost Ceiling**: ~$0.60 total (~276k agentic + ~124k static per exhaustive call, 5 draws each ~= 2M tokens). Cost is not a deciding factor either way.

### 8. Future Work
*   Two-arm static comparison isolating model tier: `gemini-3.6-flash` (STATIC) vs `gemini-3.8-flash` (STATIC).
