#!/usr/bin/env python3
"""
scripts/verify_charge_tones.py — Verifies charge-tone presence across all 6 candidate shock windows
using a widened (200-4000 Hz) band filter and explicit mathematical decision rules.
"""

import numpy as np
import soundfile as sf
from scipy import signal, stats

WINDOWS = [
    (160.0, 180.0, "Consensus Shock 1 (draws: 164.0 / 165.0 / 171.5 / 173.0)", 167.94),
    (380.0, 395.0, "Consensus Shock 2 (draws: 386.5 / 387.0)", 385.07),
    (612.0, 630.0, "Consensus Shock 3 (draws: 620.0 / 620.5 / 621.0)", 621.34),
    (735.0, 750.0, "Disputed Shock A  (draws: R2 741.0 — ref 742.21)", 742.21),
    (850.0, 870.0, "Disputed Shock B  (draws: R2 861.0)", 851.01),
    (875.0, 895.0, "Disputed Shock C  (draws: R4 884.5)", 880.17),
]


def analyze_charge_tone(idx: int, ts: float, te: float, label: str, t_peak: float) -> None:
    wav_path = f"/tmp/probe_win_{idx}.wav"
    y, sr = sf.read(wav_path)
    if y.ndim > 1:
        y = y.mean(axis=1)

    # 1. RMS transient check around t_peak
    w = int(0.05 * sr)
    env = np.sqrt(np.convolve(y**2, np.ones(w) / w, mode="same"))
    max_rms = float(np.max(env))
    med_rms = float(np.median(env))
    ratio = max_rms / med_rms if med_rms > 0 else 0.0

    # 2. Spectrogram 200-4000 Hz over the 3.0s window before t_peak
    sub_start = max(0, int((t_peak - ts - 3.2) * sr))
    sub_end = max(0, int((t_peak - ts - 0.2) * sr))
    y_sub = y[sub_start:sub_end]
    f, t_sp, Sxx = signal.spectrogram(y_sub, sr, nperseg=1024, noverlap=512)

    mask = (f > 200) & (f < 4000)
    f_b, S_b = f[mask], Sxx[mask, :]

    dom_f = [int(f_b[np.argmax(S_b[:, col])]) for col in range(S_b.shape[1])]

    # 3. Decision Rule Arithmetic:
    # Look for any contiguous window of at least n_min frames where f is in 400..1000 Hz
    # and linear regression slope df/dt >= 40 Hz/s with r >= 0.70.
    n_frames = len(dom_f)
    t_axis_sub = np.linspace(0, 3.0, n_frames)

    best_slope = 0.0
    best_r = 0.0
    best_range = (0, 0)
    is_present = False

    window_size = min(35, n_frames)  # ~1.1 seconds window
    for i in range(0, n_frames - window_size + 1):
        seg_f = np.array(dom_f[i : i + window_size])
        seg_t = t_axis_sub[i : i + window_size]
        # Check if in plausible charge tone frequency band (400 to 1000 Hz)
        if np.mean((seg_f >= 400) & (seg_f <= 1000)) >= 0.7:
            res = stats.linregress(seg_t, seg_f)
            if res.slope > best_slope and res.rvalue > best_r:
                best_slope = float(res.slope)
                best_r = float(res.rvalue)
                best_range = (int(np.min(seg_f)), int(np.max(seg_f)))
                if best_slope >= 40.0 and best_r >= 0.70:
                    is_present = True

    print(f"\n=== Window {idx+1}: {label} (transient @ {t_peak}s, RMS ratio: {ratio:.1f}x) ===")
    print(f"  Full dominant-frequency array (200-4000 Hz, n={len(dom_f)} frames):")
    print("  ", dom_f)
    print(
        f"  Best rising segment: slope = {best_slope:+.1f} Hz/s | r = {best_r:.2f} | range = {best_range[0]}..{best_range[1]} Hz"
    )
    print(f"  Decision Rule (slope >= 40 Hz/s and r >= 0.70): CHARGE TONE {'PRESENT' if is_present else 'ABSENT'}")


def main() -> None:
    print("=== CHARGE-TONE MATHEMATICAL VERIFICATION (200-4000 Hz band) ===")
    print("Decision rule: Linear regression slope >= 40 Hz/s with Pearson r >= 0.70 in 400..1000 Hz band.")
    for idx, (ts, te, label, t_peak) in enumerate(WINDOWS):
        analyze_charge_tone(idx, ts, te, label, t_peak)


if __name__ == "__main__":
    main()
