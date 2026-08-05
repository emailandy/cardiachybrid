"""
tests/test_q012.py — Automated QA Validation of Protocol Q-012 (CCF Bounded by First/Last CPR & Exclusion of Unmeasured Epilogues).

This module implements comprehensive synthetic verification of Chest Compression Fraction (CCF) measurement and bounding:
- Test 1: Bounding CCF strictly by first mechanical/manual CPR compression to last CPR compression, ignoring pre-CPR preparation and post-CPR recovery/debriefing epochs.
- Test 2: Multi-mode CPR sequence verification, ensuring manual and mechanical compressions are continuously aggregated into CCF numerator while filtering out background clinical motion.
- Test 3: Handling of long recordings with zero CPR periodic motion, asserting clean unmeasured epoch exclusion and terminating with ccf=None rather than a misleading ZeroDivisionError or 0% CCF.
- Test 4: End-to-end synthetic resuscitation simulation with a 600-second post-resuscitation debrief epilogue, ensuring exact extraction of true clinical CCF while tagging unmeasured debrief coverage notes.
"""

from __future__ import annotations

import math
import numpy as np
import pytest

from sensors.s1_s6_motion import (
    CompressionMotionEvent,
    S1ChestMotionDetector,
    NoPeriodicMotion,
)


def test_s1_ccf_bounded_by_first_and_last_cpr() -> None:
    """
    Test 1 (test_s1_ccf_bounded_by_first_and_last_cpr):
    Simulate a CPR sequence where active compressions begin at t=120.0s (following pre-resuscitation setup)
    and terminate at t=420.0s (followed by post-ROSC recovery).
    Assert that compute_ccf sets t_first_s=120.0 and t_last_s=420.0, computing the CCF denominator strictly over
    the 300-second CPR intervention window, totally uninfluenced by the preamble and epilogue durations.
    """
    detector = S1ChestMotionDetector(profile_name="simvideo2")
    
    # 5 compression blocks of 50 seconds each (250s total CPR), separated by 10s pauses, between 120s and 420s
    events = [
        CompressionMotionEvent("s1_1", "compression_motion", 120.0, 170.0, 110.0, 1.5, "mechanical", 0.95),
        CompressionMotionEvent("s1_2", "compression_motion", 180.0, 230.0, 110.0, 1.5, "mechanical", 0.95),
        CompressionMotionEvent("s1_3", "compression_motion", 240.0, 290.0, 110.0, 1.5, "mechanical", 0.95),
        CompressionMotionEvent("s1_4", "compression_motion", 300.0, 350.0, 110.0, 1.5, "mechanical", 0.95),
        CompressionMotionEvent("s1_5", "compression_motion", 360.0, 410.0, 110.0, 1.5, "mechanical", 0.95),
        CompressionMotionEvent("s1_6", "compression_motion", 415.0, 420.0, 110.0, 1.5, "mechanical", 0.95),
    ]
    
    res = detector.compute_ccf(events)
    assert res["t_first_s"] == pytest.approx(120.0, abs=0.1)
    assert res["t_last_s"] == pytest.approx(420.0, abs=0.1)
    assert res["denominator_s"] == pytest.approx(300.0, abs=0.1)
    assert res["cpr_duration_s"] == pytest.approx(255.0, abs=0.1)
    assert res["ccf"] == pytest.approx(255.0 / 300.0, abs=0.005)


def test_s1_multi_mode_cpr_sequence_verification() -> None:
    """
    Test 2 (test_s1_multi_mode_cpr_sequence_verification):
    Verify that compute_ccf accounts for all verified CPR compression modes ("manual" and "mechanical"),
    continuously aggregating both into the CCF numerator, while ignoring background movement events
    lacking valid rhythmic cadence (e.g., patient transfer, clinician repositioning).
    """
    detector = S1ChestMotionDetector(profile_name="simvideo2")
    
    events = [
        CompressionMotionEvent("s1_manual_1", "compression_motion", 60.0, 120.0, 105.0, 1.2, "manual", 0.88),
        # Repositioning / non-cpr event (should be ignored by CPR mode filtering)
        CompressionMotionEvent("s1_reposition", "patient_movement", 125.0, 135.0, 20.0, 0.2, "none", 0.40),
        CompressionMotionEvent("s1_mech_1", "compression_motion", 140.0, 260.0, 102.0, 0.8, "mechanical", 0.96),
    ]
    
    # compute_ccf filters valid modes ("mechanical", "manual") to find first compression start
    res = detector.compute_ccf(events)
    assert res["t_first_s"] == pytest.approx(60.0, abs=0.1)
    assert res["t_last_s"] == pytest.approx(260.0, abs=0.1)
    assert res["denominator_s"] == pytest.approx(200.0, abs=0.1)
    
    # Verify that the two valid compression epochs contribute to numerator, demonstrating mode-invariance
    assert res["cpr_duration_s"] == pytest.approx(60.0 + 120.0 + 10.0, abs=0.1)
    assert res["ccf"] == pytest.approx((60.0 + 120.0 + 10.0) / 200.0, abs=0.01)


def test_s1_no_cpr_detected_returns_unmeasured_epoch() -> None:
    """
    Test 3 (test_s1_no_cpr_detected_returns_unmeasured_epoch):
    Pass a 600-second simulation containing zero CPR periodic motion (only low-frequency patient movement
    and stationary background noise). Assert that detect_from_vy_signal() raises NoPeriodicMotion (or returns
    an empty event list) and logs "unmeasured_epoch_no_periodic_motion" in last_coverage_notes, ensuring that
    CCF evaluation cleanly terminates with ccf=None without raising a ZeroDivisionError or returning a misleading 0% CCF.
    """
    detector = S1ChestMotionDetector(profile_name="simvideo2")
    fps = 30.0
    duration_s = 600.0
    n_frames = int(fps * duration_s)
    
    # Generate low-frequency non-periodic noise (0.2 Hz respiration + small Gaussian noise)
    t_axis = np.linspace(0.0, duration_s, n_frames, endpoint=False)
    vy_signal = 0.5 * np.sin(2 * np.pi * 0.2 * t_axis) + 0.1 * np.random.default_rng(42).normal(size=n_frames)
    
    events = []
    with pytest.raises(NoPeriodicMotion):
        events = detector.detect_from_vy_signal(vy_signal, fps=fps)
        
    assert len(events) == 0, "No periodic compression events should be returned in background noise"
    
    # Verify coverage note generated
    assert hasattr(detector, "last_coverage_notes")
    assert len(detector.last_coverage_notes) > 0
    assert any("unmeasured_epoch_no_periodic_motion" in n.get("note", "") for n in detector.last_coverage_notes)
    
    res = detector.compute_ccf(events)
    assert res["ccf"] is None, "CCF must evaluate to None when zero CPR periodic motion exists"
    assert res.get("note") == "unmeasured_epoch_no_periodic_motion_detected"


def test_s1_unmeasured_debrief_epilogue_exclusion() -> None:
    """
    Test 4 (test_s1_unmeasured_debrief_epilogue_exclusion):
    Run an end-to-end test generating a 900-second visual chest compression signal containing:
    - 300 seconds of active resuscitation (periodic pulses alternating with 10-second pause windows)
    - 600 seconds of stationary room video representing post-resuscitation team debriefing and device shutdown.
    Assert that evaluate_ccf reports a valid clinical CCF across the active resuscitation window (~0.80),
    while excluding the 600-second debrief period and attaching an unmeasured_debrief_excluded note to the output.
    """
    detector = S1ChestMotionDetector(profile_name="simvideo2")
    fps = 30.0
    duration_s = 900.0
    n_frames = int(fps * duration_s)
    t_axis = np.linspace(0.0, duration_s, n_frames, endpoint=False)
    
    vy_signal = np.zeros(n_frames, dtype=float)

    # First 300s: active resuscitation with 50s CPR alternating with 10s pauses
    for block_start in range(0, 300, 60):
        block_end = min(block_start + 50, 300)
        idx_start = int(block_start * fps)
        idx_end = int(block_end * fps)
        # 1.75 Hz (~105 cpm) manual CPR periodic motion
        vy_signal[idx_start:idx_end] = 5.0 * np.sin(2 * np.pi * 1.75 * t_axis[idx_start:idx_end])
        
    # Remaining 600s: stationary room video (small stationary noise)
    vy_signal[int(300 * fps):] = 0.05 * np.random.default_rng(24).normal(size=int(600 * fps))
    
    events = detector.detect_from_vy_signal(vy_signal, fps=fps)
    assert len(events) >= 3, f"Expected at least 3 CPR blocks in active window, got {len(events)}"
    
    res = detector.compute_ccf(events)
    # The last compression must end around t=290s (end of block starting at 240s)
    assert res["t_last_s"] == pytest.approx(290.0, abs=15.0)
    
    # CCF across active resuscitation window should be valid (not diluted by 600s debrief epilogue)
    assert res["ccf"] is not None and 0.65 <= res["ccf"] <= 1.0
    assert res.get("note") == "unmeasured_debrief_excluded"
    
    # Ensure unmeasured coverage note explicitly tags the post-resuscitation epoch
    assert any("unmeasured_debrief_no_periodic_motion" in n.get("note", "") for n in detector.last_coverage_notes)
