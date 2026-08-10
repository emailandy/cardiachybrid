"""
tests/test_s3_pinning.py — Real-Detector Pinning Gate for S3 Acoustic Adjudication.

Calls the REAL S3DefibDetector.adjudicate() against REAL tests/video/vidsim2.mp4 (no mocks)
to verify acoustic adjudication on S02-certified true positives and negative controls.
"""

from pathlib import Path
import pytest
from sensors.s3_defib import S3DefibDetector
from pipeline.s3_gate import DEFAULT_WINDOW_S


@pytest.mark.integration
def test_s3_real_detector_pinning_gate() -> None:
    """
    Integration pinning gate:
    Pins the F-030 / M1 documented state — S3 confirms zero shocks under the uncalibrated
    default profile on a training-configuration device that never charged.
    If this ever fails, S3 has been calibrated or presented with a real charge tone, and
    Q-019 should be revisited.
    
    1. confirmed == False at 861.0 and 884.5 (S02-certified negative controls)
    2. 879.0 does not crash (legitimately abstains per F-022)
    3. Positives at 167.94, 385.07, 621.34, 742.21 return confirmed=False
    """
    video_path = Path(__file__).resolve().parent.parent / "tests" / "video" / "vidsim2.mp4"
    if not video_path.exists():
        pytest.skip("tests/video/vidsim2.mp4 not found")

    detector = S3DefibDetector("default")

    # Step 1: Negative controls must reject
    for neg_t in [861.0, 884.5]:
        v_neg = detector.adjudicate(video_path, candidate_t=neg_t, window_s=DEFAULT_WINDOW_S)
        assert not v_neg.confirmed, f"Negative control at {neg_t}s was unexpectedly confirmed!"

    # Step 2: Gold #5 (879.0s) must not crash
    v_879 = detector.adjudicate(video_path, candidate_t=879.0, window_s=DEFAULT_WINDOW_S)
    assert v_879 is not None

    # Step 3: Check S02-certified positives under default window
    positives = [167.94, 385.07, 621.34, 742.21]
    results = {}
    for pos_t in positives:
        v_pos = detector.adjudicate(video_path, candidate_t=pos_t, window_s=DEFAULT_WINDOW_S)
        results[pos_t] = v_pos.confirmed

    # Document real detector outcomes under uncalibrated default profile (F-030)
    # 4/4 return confirmed=False because automated detector under default profile requires per-device calibration (Q-019)
    assert results[167.94] is False
    assert results[385.07] is False
    assert results[621.34] is False
    assert results[742.21] is False
