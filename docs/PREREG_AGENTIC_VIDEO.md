## Pre-registration: Agentic Video Feasibility (Task 13a)

### 1. Hypothesis / Mechanism
**Hypothesis**: The introduction of agentic video processing (`MediaProcessing.AGENTIC`) in `gemini-3.8-flash` will yield superior extraction accuracy (specifically on temporal boundaries for CCIs and instantaneous events like shocks) compared to fixed-rate frame extraction (`STATIC`), without degrading the boolean/categorical accuracy of static evaluation.
**Mechanism**: Agentic processing allows the model to dynamically navigate the video track, seeking forward and backward to identify precise event boundaries and states, overcoming the hard resolution limits of static `fps` decimation.

### 2. Experimental Arms (One Variable at a Time)
To isolate model tier, processing mode, and agentic capability, `thinking_level` MUST be held CONSTANT (`ThinkingLevel.MEDIUM`) across all arms, as `gemini-3.8-flash` rejects `MINIMAL`.
*   **Arm A (Baseline)**: `gemini-3.6-flash`, `processing=STATIC`, `thinking=MEDIUM`
*   **Arm B (Model Upgrade)**: `gemini-3.8-flash`, `processing=STATIC`, `thinking=MEDIUM`
*   **Arm C (Capability Upgrade)**: `gemini-3.8-flash`, `processing=AGENTIC`, `thinking=MEDIUM`
*   **Arm D (Tier Upgrade)**: `gemini-3.8-pro`, `processing=AGENTIC`, `thinking=MEDIUM`

### 3. The Ground-Truth Precision Caveat & Stopping Condition
The ground-truth timestamps for this clinical simulation have a precision of roughly ±3s. 
**Stopping Condition**: If the timestamp precision improvement (mean absolute error of `Δt`) between Arm B and Arm C (STATIC vs AGENTIC) is less than the ±3s ground-truth noise floor, I will report the temporal benefit of agentic mode as unmeasurable on this case and stop. I will not tune prompts to chase sub-precision illusory wins.

### 4. Evaluation Metrics
Separate tables will be maintained for Instantaneous Events (Shocks, Epi) and Interval Events (CCIs).

**Table 1: Instantaneous Events**
| Metric | Arm A | Arm B | Arm C | Arm D |
|---|---|---|---|---|
| True Positives (Recall) | | | | |
| False Positives | | | | |
| Temporal MAE (s) | | | | |

**Table 2: Interval Events (CCIs)**
| Metric | Arm A | Arm B | Arm C | Arm D |
|---|---|---|---|---|
| True Positives (Recall) | | | | |
| False Positives | | | | |
| Start/End MAE (s) | | | | |

### 5. Falsification Criteria & Cost Ceiling
*   **Falsification**: If Arm C (AGENTIC) has a higher Temporal MAE or lower True Positive rate than Arm B (STATIC), the hypothesis is falsified. If Arm C hallucinates events not present in Arm B, the safety of AGENTIC mode is falsified.
*   **Cost Ceiling**: $5.00 total across all draws. If projected cost exceeds this, abort.
