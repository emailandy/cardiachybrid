## Pre-registration: Agentic Video Feasibility (Task 13a)

### Prerequisites & Invocation Mechanism (SDK Bypass)
*   **SDK Upgrade Cancelled**: We will NOT upgrade `google-genai`. Instead, execution will bypass the SDK's `types.Part` Pydantic validation via direct REST calls.
*   **Constants**:
    *   `location="global"` (matches existing pipeline default in `pipeline/vertex_client.py:45`).
    *   `api_version="v1beta1"` (required for agentic).
    *   `transport="REST"` (to bypass `google-genai 2.16.0` validation).
    *   `thinking_level`: **NONE**. Sending `thinkingLevel="MEDIUM"` (as documented in Google's samples) returns HTTP 400 (`Unknown name "thinkingLevel"`). This is a recorded documentation defect; `thinking_level` is omitted from all arms.
    *   `responseSchema` = ON for all arms (mandatory).

### 1. Hypothesis, Mechanism & Expected Prior
**Hypothesis**: Does agentic video processing (`mediaProcessing="AGENTIC"`) yield superior extraction recall and accuracy on instantaneous events (shocks) compared to fixed-rate frame extraction (`STATIC`), specifically on long-form video?
**Expected Prior (Predicted Negative)**: A preliminary long-form probe demonstrated that agentic mode consumes massively MORE tokens (~270k) than static mode (~1.3k) on 22-minute video by entering a high-token tool-use loop. Furthermore, Google routes static mode for *frame-level precision*. Therefore, the stated prior is that **agentic arms will LOSE on both temporal MAE and token efficiency**, though it may improve event recall via targeted navigation. We will not tune prompts to rescue agentic if it loses on precision. A predicted-negative is a valid result.

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

### 5. Target & The Ground-Truth Precision Caveat
**Target**: The 5 human-adjudicated shocks. These will be read dynamically from `fixtures/ground_truth_simvideo2.json`, not hardcoded.
**Ground-Truth Precision**: The ground-truth timestamps have a precision of roughly ±3s. 
**Stopping Condition**: If the timestamp precision difference (mean absolute error of `Δt`) between Arm A and Arm S is less than the ±3s ground-truth noise floor, I will report "no measurable benefit" for agentic mode's temporal precision and stop.

### 6. Evaluation Metrics
Evaluations will be per-arm, per-draw to capture stochastic spread (`k=5`).

**Table: Instantaneous Events (Shocks)**
| Metric | Arm S (`k=1..5` spread & mean) | Arm A (`k=1..5` spread & mean) |
|---|---|---|
| True Positives (Recall @ ±3.0s) | | |
| False Positives & False Negatives | | |
| Temporal MAE (s) | | |
| totalTokenCount | | |
| toolUsePromptTokenCount | | |
| Latency & Cost | | |

### 7. Win, Falsification & Indeterminate Criteria
*   **Win / Adopt**: Arm A's median True Positive (TP) count across `k=5` draws strictly exceeds Arm S's median TP count by >= 1 shock, AND Arm A's minimum TP count across all 5 draws is >= Arm S's median TP count (ensuring the gain is not an artifact of a single outlier draw), AND Arm A's Temporal MAE stays within the ±3.0s ground-truth noise floor of Arm S. Cherry-picking a "best-of-5" single draw is strictly forbidden.
*   **Indeterminate**: Any result that meets neither the Win condition nor the Falsification condition. This will be reported as "no measurable difference" with no recommendation for adoption, and testing will stop. No prompt tuning or re-running will be conducted to break ties.
*   **Falsification**: If Arm A (AGENTIC) has a higher Temporal MAE (beyond the ±3s floor) or lower True Positive rate than Arm S (STATIC), the precision/recall hypothesis is falsified.
*   **Maximum Claim Ceiling**: Given n=1 case and k=5 draws, no outcome of this experiment can establish accuracy for production use; the maximum claim available is a mode preference on a single manikin case (see Q-017).
*   **Cost Ceiling**: $5.00 total across all draws. If projected cost exceeds this, abort.

### 8. Future Work
*   Two-arm static comparison isolating model tier: `gemini-3.6-flash` (STATIC) vs `gemini-3.8-flash` (STATIC).
