#!/usr/bin/env python3
"""
scripts/probe_acoustic_shocks.py — Acoustic adjudication across 6 candidate shock windows
on simvideo2.mp4. Measures transient RMS peak-to-median ratio and rising 500-800 Hz charge tone.
"""

import os
import subprocess
from pathlib import Path
import numpy as np
import soundfile as sf
from scipy import signal

WINDOWS = [
    (160.0, 180.0, "Consensus Shock 1 (draws: 164.0 / 165.0 / 171.5 / 173.0)"),
    (380.0, 395.0, "Consensus Shock 2 (draws: 386.5 / 387.0)"),
    (612.0, 630.0, "Consensus Shock 3 (draws: 620.0 / 620.5 / 621.0)"),
    (735.0, 750.0, "Disputed Shock A  (draws: R2 741.0 — ref 742.21)"),
    (850.0, 870.0, "Disputed Shock B  (draws: R2 861.0)"),
    (875.0, 895.0, "Disputed Shock C  (draws: R4 884.5)"),
]


def analyze_window(idx: int, t_start: float, t_end: float, label: str) -> None:
    wav_path = f"/tmp/probe_win_{idx}.wav"
    cmd = [
        "ffmpeg", "-y", "-ss", str(t_start), "-t", str(t_end - t_start),
        "-i", "/tmp/sim.mp4", "-vn", "-ac", "1", "-ar", "16000",
        "-loglevel", "error", wav_path
    ]
    subprocess.run(cmd, check=True)

    y, sr = sf.read(wav_path)
    if y.ndim > 1:
        y = y.mean(axis=1)

    # 1. RMS Transient Envelope (50ms window)
    w = int(0.05 * sr)
    env = np.sqrt(np.convolve(y**2, np.ones(w) / w, mode="same"))
    t_axis = np.arange(len(env)) / sr + t_start

    med_rms = float(np.median(env))
    max_rms = float(np.max(env))
    ratio = max_rms / med_rms if med_rms > 0 else 0.0

    # Find candidate peaks above 4.0x median
    peak_idx = np.argmax(env)
    t_peak = float(t_axis[peak_idx])

    # Let's check top 3 local peaks that are spaced > 1.0s apart in the window
    sorted_indices = np.argsort(env)[::-1]
    candidate_peaks = []
    for idx_val in sorted_indices:
        t_cand = float(t_axis[idx_val])
        if not any(abs(t_cand - p) < 1.0 for p in candidate_peaks):
            candidate_peaks.append(t_cand)
        if len(candidate_peaks) >= 3:
            break
    candidate_peaks.sort()

    print(f"\n=== Window {idx+1}: [{t_start}s - {t_end}s] {label} ===")
    print(f"  Max RMS: {max_rms:.4f} | Median RMS: {med_rms:.4f} | RMS Peak/Median Ratio: {ratio:.1f}x")
    print(f"  Top Candidate Transient Peaks: {[round(p, 2) for p in candidate_peaks]}")

    # 2. Charge tone inspection for each candidate peak (check 3s window before peak)
    for p_t in candidate_peaks:
        # Check spectrogram from p_t - 3.5s to p_t - 0.2s
        sub_start = max(0, int((p_t - t_start - 3.5) * sr))
        sub_end = max(0, int((p_t - t_start - 0.2) * sr))
        if sub_end <= sub_start + int(0.5 * sr):
            continue
        y_sub = y[sub_start:sub_end]
        f, t_sp, Sxx = signal.spectrogram(y_sub, sr, nperseg=1024, noverlap=512)

        # Focus on 500-850 Hz band
        band_mask = (f >= 500) & (f <= 850)
        f_band = f[band_mask]
        S_band = Sxx[band_mask, :]

        # Find dominant frequency at each time step in the band
        dom_freqs = []
        for col in range(S_band.shape[1]):
            col_power = S_band[:, col]
            if np.max(col_power) > 3.0 * np.median(Sxx[:, col]):
                dom_f = float(f_band[np.argmax(col_power)])
                dom_freqs.append(round(dom_f))
        
        # Check if monotonically rising (or rising trend > 80 Hz increase)
        if len(dom_freqs) >= 4:
            start_f = np.mean(dom_freqs[:3])
            end_f = np.mean(dom_freqs[-3:])
            freq_diff = end_f - start_f
            is_rising = freq_diff > 80.0
        else:
            freq_diff = 0.0
            is_rising = False

        print(f"    Peak @ {p_t:.2f}s -> Charge Tone Check (500-850 Hz):")
        print(f"      Freq sequence: {dom_freqs[:12]} ... (n={len(dom_freqs)})")
        print(f"      Freq shift: {freq_diff:+.1f} Hz | Rising tone present: {is_rising}")


def main() -> None:
    print("Running acoustic adjudication across 6 candidate shock windows...")
    for idx, (ts, te, label) in enumerate(WINDOWS):
        analyze_window(idx, ts, te, label)


if __name__ == "__main__":
    main()
