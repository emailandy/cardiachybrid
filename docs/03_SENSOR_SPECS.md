# Resuscitation Quality Improvement Pipeline — Deterministic Multimodal Sensor Specifications (`S1–S7`)

This specification defines the algorithmic architecture, output schemas, downstream variable dependencies, calibration procedures, failure modes, degraded fallbacks, and clinical validation targets for the seven deterministic multimodal sensors (`S1–S7`).

> [!IMPORTANT]
> **Phase 1 Implementation Scope**: All physical streaming sensor hardware ingestion pipelines (`S1–S7`) are **NOT BUILT** in Phase 1 ([D00](tasks/D00.md)). Sensor S3 acoustic signal processing parameters were evaluated offline against clinical simulation audio in our empirical probe (`F-009`).

---

## 1. Sensor S1: Chest-ROI Optical Flow / Compression Motion

### 1.1 Algorithmic Architecture
Sensor S1 tracks chest compression motion using dense Lucas-Kanade optical flow computed over a dynamically bounded chest region-of-interest (`ROI`). The vertical velocity signal $v_y(t)$ is bandpass-filtered (`1.5–2.5 Hz`, corresponding to `90–150 cpm`) to detect active cardiopulmonary resuscitation (`CPR`) intervals and pauses.

```python
# Algorithmic Specification: Optical Flow CPR Motion Detection (S1)
def detect_cpr_motion(vy_signal: list[float], fps: float = 30.0) -> list[dict]:
    """Detects CPR compression intervals from vertical optical flow velocity."""
    import numpy as np
    from scipy.signal import butter, filtfilt
    
    b, a = butter(4, [1.5 / (fps/2), 2.5 / (fps/2)], btype='band')
    filtered = filtfilt(b, a, vy_signal)
    energy = np.convolve(filtered**2, np.ones(int(fps*2))/int(fps*2), mode='same')
    
    threshold = 0.05 * np.max(energy)
    active = energy > threshold
    return _extract_intervals(active, fps)
```

### 1.2 Output Schema
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "id": { "type": "string" },
    "type": { "type": "string", "const": "compression_motion" },
    "t_start_s": { "type": "number" },
    "t_end_s": { "type": "number" },
    "cadence_cpm": { "type": "number" },
    "confidence": { "type": "number", "minimum": 0.0, "maximum": 1.0 }
  },
  "required": ["id", "type", "t_start_s", "t_end_s", "cadence_cpm", "confidence"]
}
```

### 1.3 Variables Fed & Downstream Dependencies
* `cpr_initiated_ed`, `num_cci_v2`
* `t_start_s` and `t_end_s` of `compression_interruption` intervals (`F-006`, `F-010`)
* Derived Quality Metric: Chest Compression Fraction (`CCF`, `D10`)

### 1.4 Calibration, Failure Modes, Degraded Behavior & Validation
* **Calibration**: Requires spatial pixel-to-cm chest calibration and frame rate `fps >= 15`.
* **Failure Modes**: Provider crowding over the chest, rapid camera panning, blankets obscuring ROI.
* **Degraded Behavior**: When S1 optical flow fails or is occluded, temporal boundary adjudication defers to audio cadence (`S2`) or LLM block querying (`F-006`, `F-010`).
* **Validation Target**: Temporal boundary accuracy `<= 0.5s` against dual-annotated human optical flow ground truth.
* **Built Status**: **NOT BUILT** in Phase 1 ([D00](tasks/D00.md)).

---

## 2. Sensor S2: Compression-Audio Cadence Periodicity

### 2.1 Algorithmic Architecture
Sensor S2 computes a Short-Time Fourier Transform (`STFT`, window=2.0s, hop=0.2s) on the 16 kHz mono audio track, monitoring spectral peak energy in the `1.6–2.2 Hz` band (`100–132 cpm`) to detect CPR acoustic clicks or metronome cadences.

```python
# Algorithmic Specification: Audio Cadence Periodicity Detection (S2)
def detect_audio_cadence(audio_16k: list[float], sr: int = 16000) -> list[dict]:
    """Detects CPR acoustic cadence periodicity from 16 kHz mono audio."""
    import numpy as np
    from scipy.signal import stft
    
    f, t, Zxx = stft(audio_16k, fs=sr, nperseg=sr*2, noverlap=int(sr*1.8))
    band_idx = np.where((f >= 1.6) & (f <= 2.2))[0]
    cadence_energy = np.mean(np.abs(Zxx[band_idx, :]), axis=0)
    return _peaks_to_intervals(cadence_energy, t)
```

### 2.2 Output Schema
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "id": { "type": "string" },
    "type": { "type": "string", "const": "compression_audio" },
    "t_start_s": { "type": "number" },
    "t_end_s": { "type": "number" },
    "frequency_hz": { "type": "number" },
    "confidence": { "type": "number", "minimum": 0.0, "maximum": 1.0 }
  },
  "required": ["id", "type", "t_start_s", "t_end_s", "frequency_hz", "confidence"]
}
```

### 2.3 Variables Fed & Downstream Dependencies
* Corroborates S1 CPR compression intervals; provides primary cadence when visual ROI is occluded.

### 2.4 Calibration, Failure Modes, Degraded Behavior & Validation
* **Calibration**: Ambient room noise floor subtraction.
* **Failure Modes**: Loud vocalizations, mechanical chest compression device (`MCCD`) motor whine, alarms.
* **Degraded Behavior**: Emits `confidence=0.0` when SNR `< 3.0 dB`, deferring to S1 or LLM.
* **Validation Target**: Cadence accuracy `+/- 5 cpm` against reference metronome.
* **Built Status**: **NOT BUILT** in Phase 1 ([D00](tasks/D00.md)).

---

## 3. Sensor S3: Defibrillator Acoustic Charge/Discharge Detection (`F-009`)

### 3.1 Algorithmic Architecture & Measured Parameters
Sensor S3 processes the 16 kHz mono audio track (`simvideo2.mp4`) to detect defibrillator charge tones and shock discharges (`scripts/probe_acoustic_shocks.py`).

```python
# Algorithmic Specification: Acoustic Defibrillation Detection (S3, F-009)
def detect_defib_shocks(audio_16k: list[float], sr: int = 16000) -> list[dict]:
    """Detects rising charge tones and acoustic discharge transients."""
    # Track rising narrowband tone: 400-1000 Hz, slope >= 40 Hz/s, Pearson r >= 0.70
    tones = _track_rising_tones(audio_16k, sr, freq_min=400, freq_max=1000, min_slope=40)
    events = []
    for tone in tones:
        # Search bounded window after tone termination for discharge spike
        rms_ratio = _compute_peak_rms_ratio(audio_16k, tone['t_end'], window_s=2.0)
        is_shock = rms_ratio > 5.0
        events.append({
            "type": "defibrillation_shock" if is_shock else "defib_charge_aborted",
            "t_start_s": tone['t_end'],
            "peak_rms_ratio": rms_ratio,
            "tone_slope_hz_s": tone['slope'],
            "confidence": min(1.0, rms_ratio / 10.0) if is_shock else 0.95
        })
    return events
```

* **Empirical Measured Parameters (`F-009`)**: In our clinical simulation probe (`simvideo2.mp4`, 16 kHz mono), the detector measured a transient peak-to-median RMS ratio of **`5.7`** (`> 5.0` threshold) with a sharp acoustic discharge spike at **`742.21s`** following an unambiguous rising charge tone progression (**`515 Hz -> 796 Hz`**) during **`738.0–741.0s`**.
* **Primary vs. Corroborating Signal (`F-009`)**: The original S3 specification treated the discharge click as the primary signal and the charge tone as corroboration. Empirical measurement on `simvideo2.mp4` inverts this: a 3-second rising narrowband tone survives 16 kHz mono compression and room noise, whereas a sub-100ms transient barely survives. S3 tracks the rising tone as primary, then searches a bounded window after tone termination for the transient. A charge tone with no following transient is classified as `defib_charge_aborted`—providing the Constitution's negative control for free.

> [!WARNING]
> **The `n=4` Calibration-Scope Caveat (`F-009`, `CR-003`)**: The charge-tone detector parameters (`400–1000 Hz`, slope `>= 40 Hz/s`, Pearson `r >= 0.70`, duration `>= 1.1s`) were derived from four positive and two negative examples (**`n=4 positives, n=2 negatives`**) in a single video, from a single unidentified defibrillator model, on a 16 kHz mono track. The parameters are **fitted, not general** (`F-009`, `CR-003`). Defibrillator charge tones differ materially by manufacturer—a device whose tone falls outside 400–1000 Hz or rises more slowly than 40 Hz/s would be missed. Sensor S3 requires a per-device calibration set before production use (`CR-003`). Sensitivity and specificity are not estimable from six examples; the correct claim is *"unambiguous on this footage,"* not *"validated"* (`F-009`).

### 3.2 Output Schema
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "id": { "type": "string" },
    "type": { "type": "string", "enum": ["defibrillation_shock", "defib_charge_aborted"] },
    "t_start_s": { "type": "number" },
    "t_end_s": { "type": "number" },
    "peak_rms_ratio": { "type": "number" },
    "tone_slope_hz_s": { "type": "number" },
    "confidence": { "type": "number", "minimum": 0.0, "maximum": 1.0 }
  },
  "required": ["id", "type", "t_start_s", "t_end_s", "peak_rms_ratio", "tone_slope_hz_s", "confidence"]
}
```

### 3.3 Variables Fed & Downstream Dependencies
* `defib_shock_time_1..30`, `num_times_defib_ed_v2`
* Derived Quality Metric: Peri-shock pause duration (`D10`)
* Adjudicates candidate defibrillation shocks proposed by LLM Union-of-k draws (`F-008`).

### 3.4 Calibration, Failure Modes, Degraded Behavior & Validation
* **Calibration**: Requires per-manufacturer defibrillator charge tone frequency profile (`CR-003`).
* **Windowed Adjudicator Contract (`F-013`, `F-014`)**: Sensor S3 operates as a windowed adjudicator (`adjudicate(audio_or_video_path, candidate_t, window_s=30.0) -> DefibVerdict`) over candidate regions proposed by LLM/P1 passes ("union for recall, acoustic adjudication for precision"), to be wired in `S09`. Standalone full-track detection without window gating yields ~100% false positives (`F-014`) due to speech formants and equipment alarms in the 400-1000 Hz band.
* **Failure Modes**: Siren noise masking tones; non-standard defibrillator manufacturer tones.
* **Degraded Behavior**: When acoustic SNR `< 5.0`, defers shock adjudication to LLM Union-of-k draws (`F-008`).
* **Validation Target**: `0` false positives on calibration set; timing accuracy `<= 0.2s`.
* **Built Status**: Offline probe and windowed adjudicator validated (`F-009`, `F-013`); streaming pipeline **NOT BUILT** in Phase 1 ([D00](tasks/D00.md)).

---

## 4. Sensor S4: Monitor Waveform & Display OCR Telemetry Ingestion

### 4.1 Algorithmic Architecture
Sensor S4 performs optical character recognition (`OCR`) and waveform edge extraction on the physiological monitor display ROI, logging time-series vital signs and arterial line blood pressure readings.

```python
# Algorithmic Specification: Monitor OCR Ingestion (S4)
def ingest_monitor_ocr(frame_roi: list[list[int]], timestamp_s: float) -> dict:
    """Extracts numeric vital signs from monitor display ROI."""
    # OCR pipeline extracting SBP, DBP, HR, SpO2, ETCO2
    return {
        "type": "monitor_ocr",
        "t_start_s": timestamp_s,
        "t_end_s": timestamp_s + 1.0,
        "sbp_mmHg": 120.0,
        "dbp_mmHg": 80.0,
        "confidence": 0.95
    }
```

### 4.2 Output Schema
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "type": { "type": "string", "const": "monitor_ocr" },
    "t_start_s": { "type": "number" },
    "t_end_s": { "type": "number" },
    "sbp_mmHg": { "type": "number" },
    "dbp_mmHg": { "type": "number" },
    "heart_rate_bpm": { "type": "number" },
    "confidence": { "type": "number", "minimum": 0.0, "maximum": 1.0 }
  },
  "required": ["type", "t_start_s", "t_end_s", "confidence"]
}
```

### 4.3 Variables Fed & Downstream Dependencies
* `aline_sbp_cci_*`, `aline_dbp_cci_*`, `rhythm_rosc_*`, `first_ed_rhythm_v2`.

### 4.4 Calibration, Failure Modes, Degraded Behavior & Validation
* **Calibration**: Monitor screen bounding box coordinates; contrast normalization.
* **Failure Modes**: Provider standing in front of monitor; screen glare; low video bitrate.
* **Degraded Behavior**: Emits `state="utd"`, `modality="monitor_ocr"`, and `abstain_reason="Monitor display occluded"`.
* **Validation Target**: Numeric OCR accuracy `>= 98%` on unobstructed frames.
* **Built Status**: **NOT BUILT** in Phase 1 ([D00](tasks/D00.md)).

---

## 5. Sensor S5: Clock Anchor Synchronization

### 5.1 Algorithmic Architecture
Sensor S5 cross-correlates audio/video timestamps against monitor internal clock impulses and EMS dispatch tone markers to compute drift offset $\Delta t_{sync}$.

```python
# Algorithmic Specification: Temporal Clock Synchronization (S5)
def compute_clock_offset(video_markers: list[float], clock_markers: list[float]) -> float:
    """Computes zero-time synchronization offset delta_t in seconds."""
    import numpy as np
    return float(np.median(np.array(clock_markers) - np.array(video_markers)))
```

### 5.2 Output Schema
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "type": { "type": "string", "const": "clock_sync" },
    "offset_s": { "type": "number" },
    "drift_ppm": { "type": "number" },
    "confidence": { "type": "number", "minimum": 0.0, "maximum": 1.0 }
  },
  "required": ["type", "offset_s", "confidence"]
}
```

### 5.3 Variables Fed & Downstream Dependencies
* Normalizes all timestamps across `fact_event`, `fact_interval`, and `fact_sensor_interval` to a single unified case zero-time.

### 5.4 Calibration, Failure Modes, Degraded Behavior & Validation
* **Calibration**: Initial room wall clock or defibrillator time-set reference.
* **Failure Modes**: Asynchronous device clocks; frame drops in video capture.
* **Degraded Behavior**: Assumes nominal `fps=30` linear clock without drift correction (`confidence=0.80`).
* **Validation Target**: Inter-stream temporal synchronization `<= 0.5s` (`±0.5s` sub-second precision floor; empirical OCR reads carry millisecond timestamps such as `07:56:06.630`).
* **Clinical Precision & Drift Notes**: In `simvideo2.mp4`, Sample 1 (`t=10s`) projects T0 at `.630`, while samples 2 and 3 (`t=300s, 600s`) project at `.072` and `.081` (agreeing to within 9ms). The ~450ms difference at `t=10s` is a decode-position rounding artifact rather than true clock drift. If S5 reports drift near the `2.0s` threshold on another case, inspect the first sample first.
* **Built Status**: **BUILT** in Phase 2 ([S01](tasks/S01.md)).

---

## 6. Sensor S6: Channel Coverage & Visual Occlusion Detection (`F-012`)

### 6.1 Algorithmic Architecture
Sensor S6 classifies visual obstructions on camera feeds and ROI bounding boxes (detecting provider crowding, camera blockages, or disconnected audio).

```python
# Algorithmic Specification: Channel Coverage Detection (S6, F-012)
def detect_visual_occlusion(frame_roi: list[list[int]], timestamp_s: float) -> dict:
    """Detects visual occlusion or provider crowding over ROI."""
    # Returns occlusion annotation if ROI visibility < 20%
    return {
        "type": "coverage_note",
        "channel": "visual_chest",
        "t_start_s": timestamp_s,
        "t_end_s": timestamp_s + 5.0,
        "degradation_type": "provider_crowding",
        "confidence": 0.95
    }
```

### 6.2 Output Schema
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "type": { "type": "string", "const": "coverage_note" },
    "channel": { "type": "string", "enum": ["visual_chest", "monitor_ocr", "audio_room"] },
    "t_start_s": { "type": "number" },
    "t_end_s": { "type": "number" },
    "degradation_type": { "type": "string" },
    "confidence": { "type": "number", "minimum": 0.0, "maximum": 1.0 }
  },
  "required": ["type", "channel", "t_start_s", "t_end_s", "degradation_type", "confidence"]
}
```

### 6.3 Variables Fed & Downstream Dependencies
* Provides explicit channel degradation reasons (`abstain_reason="Channel coverage degraded"`) for unpopulated clinical fields (`F-012`, `F-004`).

### 6.4 Calibration, Failure Modes, Degraded Behavior & Validation
* **Calibration**: Background scene occlusion thresholding.
* **Failure Modes**: Partial translucency (e.g., clear sterile drapes misclassified as occlusion).
* **Degraded Behavior (`F-012`)**: When Sensor S6 is unbuilt, coverage notes lack specific degradation issue types. Under our rigorous cause-based abstention derivation, **47 of 63 unpopulated clinical fields correctly fall back to branch 5 (`"no evidence observed"`)** rather than receiving a speculative or field-name-keyed explanation (`F-012`). As framed in our demonstration: *"Sixty-three fields say 'unable to determine.' Forty-seven of them say only that — no evidence observed. The system knows it didn't see something; it doesn't yet know why, because the coverage sensor isn't built. When it is, each of those rows will name a channel and a timestamp range you can check against the video yourself."*
* **Validation Target**: 100% recall of visual occlusions `>= 5.0s`.
* **Built Status**: **NOT BUILT** in Phase 1 (`F-012`, [D00](tasks/D00.md)).

---

## 7. Sensor S7: Diarized ASR Transcription & Speaker Attribution

### 7.1 Algorithmic Architecture
Sensor S7 performs multichannel automatic speech recognition (`ASR`) with x-vector speaker diarization to attribute spoken utterances to the primary resuscitation team leader.

```python
# Algorithmic Specification: Diarized ASR Transcription (S7)
def transcribe_diarized_utterances(audio_16k: list[float], sr: int = 16000) -> list[dict]:
    """Transcribes spoken utterances and attributes speaker ID."""
    # ASR + speaker diarization pipeline
    return [{
        "utterance_id": "utt_001",
        "speaker_id": "speaker_leader",
        "t_start_s": 12.0,
        "t_end_s": 15.0,
        "transcript": "Stop CPR, rhythm check.",
        "is_directive": True,
        "confidence": 0.91
    }]
```

### 7.2 Output Schema
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "utterance_id": { "type": "string" },
    "speaker_id": { "type": "string" },
    "t_start_s": { "type": "number" },
    "t_end_s": { "type": "number" },
    "transcript": { "type": "string" },
    "is_directive": { "type": "boolean" },
    "confidence": { "type": "number", "minimum": 0.0, "maximum": 1.0 }
  },
  "required": ["utterance_id", "speaker_id", "t_start_s", "t_end_s", "transcript", "confidence"]
}
```

### 7.3 Variables Fed & Downstream Dependencies
* `closed_loop_completion_rate`, `n_unacknowledged_directives`, `fact_utterance`.

### 7.4 Calibration, Failure Modes, Degraded Behavior & Validation
* **Calibration**: Room acoustic impulse response and microphone gain normalization.
* **Failure Modes**: Simultaneous overlapping speech; PPE/mask acoustic attenuation.
* **Degraded Behavior**: Without S7, diarized ASR-dependent metrics emit `NULL` with `null_reason="requires S7 diarized ASR"` (`D10`).
* **Validation Target**: Word error rate (`WER`) `<= 15%`, speaker diarization error rate (`DER`) `<= 10%`.
* **Built Status**: **NOT BUILT** in Phase 1 ([D00](tasks/D00.md)).

---
Last verified: 2026-08-13 against dict_version e7c08437adcef4a5, prompt_set_sha 2b6988545630a115
