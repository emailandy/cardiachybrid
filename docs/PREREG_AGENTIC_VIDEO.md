## Pre-registration: Agentic Video Feasibility (Task 13a)

### 1. Hypothesis, Mechanism & Expected Prior
**Hypothesis**: Does agentic video processing (`media_processing="agentic"`) yield superior extraction accuracy (specifically on temporal boundaries for CCIs and instantaneous events like shocks) compared to fixed-rate frame extraction (`STATIC`), without degrading the boolean/categorical accuracy of static evaluation?
**Expected Prior (Predicted Negative)**: Google's documentation states that agentic processing is intended for long-form video to target contextually relevant information, while static processing should be used for short-form video content requiring *frame-level precision*. Since our temporal MAE binding metric demands +/- 3s precision (frame-level), **the stated prior is that agentic arms will LOSE on temporal MAE, but WIN on token efficiency**. A pre-registered predicted-negative result is scientifically valuable. We will not tune prompts to rescue the agentic arms if they lose on precision.

### 2. Experimental Arms (One Variable at a Time)
To isolate mode and model, `thinking_level` MUST be held CONSTANT (`ThinkingLevel.MEDIUM` or `thinking_level="MEDIUM"`) across all arms, as `gemini-3.8-flash` rejects `MINIMAL`.

*   **Arm A**: `gemini-3.6-flash`, `media_processing="static"` (Baseline / Current Pipeline)
*   **Arm B**: `gemini-3.6-flash`, `media_processing="agentic"` (Changes MODE only)
*   **Arm C**: `gemini-3.8-flash`, `media_processing="static"` (Changes MODEL only)
*   **Arm D**: `gemini-3.8-flash`, `media_processing="agentic"` (Changes BOTH model and mode)

### 3. Step List Handling & Turn Constraints
The agentic processing mode via `GenerateContent` emits an opaque `step_list` that encodes video context across turns. 
**Constraint**: Our pipeline executes independent, stateless generation calls for each pass (P1, P2, P3). It is inherently single-turn per video interaction. Therefore, multi-turn `step_list` plumbing is NOT required for this experiment. Agentic arms will be strictly restricted to single-turn video extraction.

### 4. The Ground-Truth Precision Caveat & Stopping Condition
The ground-truth timestamps for this clinical simulation have a precision of roughly ±3s. 
**Stopping Condition**: If the timestamp precision improvement (mean absolute error of `Δt`) on the agentic arms is less than the ±3s ground-truth noise floor, I will report the temporal benefit of agentic mode as unmeasurable on this case and stop.

### 5. Evaluation Metrics
Separate tables will be maintained for Instantaneous Events (Shocks, Epi) and Interval Events (CCIs). Token efficiency is added to measure the claimed benefit of agentic mode.

**Table 1: Instantaneous Events**
| Metric | Arm A | Arm B | Arm C | Arm D |
|---|---|---|---|---|
| True Positives (Recall) | | | | |
| False Positives | | | | |
| Temporal MAE (s) | | | | |
| Input Tokens | | | | |

**Table 2: Interval Events (CCIs)**
| Metric | Arm A | Arm B | Arm C | Arm D |
|---|---|---|---|---|
| True Positives (Recall) | | | | |
| False Positives | | | | |
| Start/End MAE (s) | | | | |
| Input Tokens | | | | |

### 6. Falsification Criteria & Cost Ceiling
*   **Falsification**: If Arm B or D (AGENTIC) has a higher Temporal MAE or lower True Positive rate than their STATIC counterparts, the temporal precision hypothesis is falsified. If they hallucinate events not present in the STATIC arms, the safety of AGENTIC mode is falsified.
*   **Cost Ceiling**: $5.00 total across all draws. If projected cost exceeds this, abort.
