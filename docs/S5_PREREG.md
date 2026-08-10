## Pre-registration: S5 Clock Anchor Analysis

### 1. Hypothesis / Mechanism
**Hypothesis**: Distributing the S5 `clock_anchor` to Windows 1–3 will cause the model's emitted timestamps to align closely with the physical timecode burned into the video feed, thereby correcting the systematic negative drift (~2.0s) observed in later windows.
**Mechanism**: The model has visual access to the burned-in timecode in the footage. By providing a grounding `T0` (the wall-clock time at video second `0.0` or `win_start`), the model can convert the visible timecode directly into absolute video seconds rather than estimating time elapsed since the start of the window.

### 2. The Ground-Truth Precision Caveat
The ground-truth timestamps for this case have a precision of roughly ±3s. Since the systematic bias we are attempting to correct is ~2.0s (e.g. shocks at 622s, 742s, 879s are systematically reported as 620s, 740s, 876.5s), this residual bias is smaller than the precision of the ground-truth annotations themselves. Thus, a 2s offset **may not be measurable** against this ground truth. "Improving" it might simply be overfitting to human annotation noise rather than achieving true sub-second accuracy. I will only accept the anchor as a measurable improvement if the offset shifts by a magnitude that unambiguously exceeds the noise floor or if the timestamps systematically "snap" to specific fractional values indicating a direct derivation from the visible timecode rather than integer rounding.

### 3. Stopping Condition
If the absolute mean shift in `Δt` is less than the ±3s ground-truth precision, I will report the anchor's effect as unmeasurable on this case and stop. I will not attempt to tune model parameters, thresholds, or formatting to force a "win" out of sub-precision noise.
