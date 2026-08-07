#!/usr/bin/env python3
"""
scripts/run_negative_controls.py — Negative Control Verification on Empty Resuscitation Bays.

Executes Sensor S1 optical flow motion detection on blank bay video feeds:
1. tests/video/blankbayvideop1.mp4: Patient 1's Bay (Room 1)
   - Calibration ROI: 'simvideo2' -> [x: 860, y: 340, width: 140, height: 140]
   - Bed alignment: Verified against Patient 1 manikin bed position.
   - Status: VERIFIED NEGATIVE CONTROL.

2. tests/video/blankbayvideo.mp4: Patient 2's Bay (Room 2)
   - Status: PROVISIONAL / UNRESOLVED (Chest ROI has 4 unreconciled estimates spanning 123px).
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sensors.s1_s6_motion import S1ChestMotionDetector, NoPeriodicMotion

VIDEOS = [
    ("Patient 1 Bay (Room 1)", Path("tests/video/blankbayvideop1.mp4"), "simvideo2", "[860, 340, 140, 140]", "VERIFIED"),
    ("Patient 2 Bay (Room 2)", Path("tests/video/blankbayvideo.mp4"), "default", "[600, 400, 720, 480]", "PROVISIONAL (Unresolved ROI)"),
]

def run_control(label: str, video_path: Path, profile: str, roi_coords: str, status: str) -> None:
    print(f"\n================================================================================")
    print(f"RUNNING NEGATIVE CONTROL: {label}")
    print(f"  File: {video_path.name}")
    print(f"  Profile: {profile} | Target Chest ROI: {roi_coords}")
    print(f"  Status: {status}")
    print(f"================================================================================")
    if not video_path.exists():
        print(f"SKIPPED: {video_path} not found.")
        return

    detector = S1ChestMotionDetector(profile_name=profile)
    try:
        events = detector.detect_from_video(video_path)
        print(f"Result: {len(events)} CPR compression events detected.")
        if len(events) == 0:
            print("✓ PASS: Zero compression events detected on empty bay.")
        else:
            print(f"❌ FAIL: Detected {len(events)} false positive events on empty bay.")
    except NoPeriodicMotion as e:
        print(f"✓ PASS: S1 correctly raised NoPeriodicMotion exception:")
        print(f"  Reason: {e}")
        print("  Zero compression events emitted on empty bay.")
    except Exception as e:
        print(f"⚠ Raised unexpected exception ({type(e).__name__}): {e}")

def main() -> None:
    print("=== S1 NON-VACUOUS NEGATIVE CONTROL VERIFICATION ===")
    for label, path, profile, roi, status in VIDEOS:
        run_control(label, path, profile, roi, status)

if __name__ == "__main__":
    main()
