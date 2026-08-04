"""
Same-model probe-derived reference for simvideo2.mp4.
NOT human ground truth; exists to measure run-to-run drift, not clinical accuracy.

NOTE ON ACOUSTIC ADJUDICATION (SENSOR S3 CALIBRATION SCOPE):
The charge-tone detector (400-1000 Hz, slope >= 40 Hz/s, Pearson r >= 0.70,
duration >= 1.1s) was derived from four positive and two negative examples
(n=4 positives, n=2 negatives) in a single video, from a single unidentified
defibrillator model, on a 16 kHz mono track. The parameters are fitted, not general.
Defibrillator charge tones differ materially by manufacturer — a device whose tone
falls outside 400-1000 Hz or rises more slowly than 40 Hz/s would be missed.
S3 requires a per-device calibration set before production use. See CR-003.
"""

from typing import Any

PROBE_REFERENCE_SIMVIDEO2: dict[str, Any] = {
    "case_id": "simvideo2.mp4",
    "shocks": [
        {"timestamp_s": 167.94, "provenance": "acoustic_confirmed"},
        {"timestamp_s": 385.07, "provenance": "acoustic_confirmed"},
        {"timestamp_s": 621.34, "provenance": "acoustic_confirmed"},
        {"timestamp_s": 742.21, "provenance": "acoustic_confirmed"},
        {"timestamp_s": 861.0, "provenance": "disputed"},
        {"timestamp_s": 884.5, "provenance": "disputed"},
    ],
    "ccis": [
        {"start_s": 142.0, "end_s": 152.0, "duration_s": 10.0, "provenance": "probe_verified"},
        {"start_s": 162.0, "end_s": 175.0, "duration_s": 13.0, "provenance": "corroborated_both_runs"},
        {"start_s": 200.0, "end_s": 232.0, "duration_s": 32.0, "provenance": "probe_verified"},
        {"start_s": 384.0, "end_s": 388.0, "duration_s": 4.0, "provenance": "corroborated_both_runs"},
        {"start_s": 550.0, "end_s": 570.0, "duration_s": 20.0, "provenance": "probe_verified"},
        {"start_s": 613.0, "end_s": 623.0, "duration_s": 10.0, "provenance": "probe_verified"},
        {"start_s": 724.0, "end_s": 744.0, "duration_s": 20.0, "provenance": "run_02, unverified"},
        {"start_s": 844.0, "end_s": 866.0, "duration_s": 22.0, "provenance": "run_02, unverified"},
    ],
    "active_resuscitation_window_s": (0.0, 880.0),
    "rosc": [],
    "death_pronounced": False,
    "dnr_confirmed": False,
}


def main() -> None:
    raise RuntimeError("This fixture module should not be executed directly.")


if __name__ == "__main__":
    main()
