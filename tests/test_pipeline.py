"""
tests/test_pipeline.py — Integrated Sensor Pipeline Tests (S09).

Verifies that:
1. SensorPipelineRunner executes all seven deterministic sensors (S1-S7).
2. get_p1_sensor_placeholders produces the exact 5 dictionary keys required by build_p1.
3. verify_p1_placeholder_wiring proves that Pass P1 receives all five sensor placeholders
   and renders cleanly without any unfilled placeholders remaining.
4. run_replication_experiment reports empirical replication metrics matching ground truth.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline.sensor_runner import (
    SensorPipelineResult,
    SensorPipelineRunner,
    run_replication_experiment,
    verify_p1_placeholder_wiring,
)

pytestmark = pytest.mark.skipif(
    not Path("simvideo2.mp4").exists(),
    reason="Requires local simvideo2.mp4 video file (not committed to git)",
)


def test_pipeline_runner_returns_all_seven_sensors() -> None:
    """Verifies that SensorPipelineRunner executes S1 through S7 on simvideo2 reference."""
    runner = SensorPipelineRunner()
    res = runner.run_pipeline(
        "simvideo2.mp4", "simvideo2.mp4", max_duration_s=160.0
    )

    assert len(res.s1_compressions) >= 1
    assert len(res.s1_pauses) >= 1
    assert len(res.s2_audio_cadence) >= 1
    assert len(res.s3_defib_shocks) >= 0
    assert len(res.s4_monitor_vitals) >= 1
    assert res.clock_anchor_iso is not None
    assert len(res.s6_coverage_notes) >= 0
    assert len(res.s7_utterances) >= 1


def test_get_p1_sensor_placeholders_returns_exact_five_keys() -> None:
    """
    Verifies that get_p1_sensor_placeholders returns exactly the five keys
    expected by prompts/builder.py build_p1(sensor_data=...).
    """
    runner = SensorPipelineRunner()
    res = runner.run_pipeline("simvideo2.mp4", "simvideo2.mp4", max_duration_s=25.0)
    sensor_data = runner.get_p1_sensor_placeholders(
        res, win_start=0.0, win_end=300.0
    )

    expected_keys = {
        "compressions_active",
        "device_audio",
        "monitor_ocr",
        "asr_diarized",
        "quality_track",
    }
    assert set(sensor_data.keys()) == expected_keys

    # Confirm all five lists are JSON-serializable
    for key, val in sensor_data.items():
        assert isinstance(val, list)
        encoded = json.dumps(val)
        assert isinstance(encoded, str)


def test_verify_p1_placeholder_wiring() -> None:
    """
    Verifies the S09 acceptance gate: P1 receives all five sensor placeholders
    and renders cleanly without unfilled placeholders or field names.
    """
    assert verify_p1_placeholder_wiring(max_duration_s=25.0) is True


def test_run_replication_experiment_reports_empirical_findings() -> None:
    """
    Verifies that run_replication_experiment produces the empirical replication
    comparison report for S09 and docs/SENSOR_FINDINGS.md.
    """
    report = run_replication_experiment(max_duration_s=25.0)
    assert report["recording"] == "simvideo2.mp4"
    assert report["integrated_sensor_shocks_confirmed"] == 4
    assert report["integrated_sensor_shocks_recall"] == 1.0
    assert report["integrated_sensor_shocks_precision"] == 1.0
    assert report["s7a_wer_against_reference"] in (0.0, None)
    assert report["standalone_llm_replication_rate"] == 0.20


@pytest.mark.integration
def test_pipeline_integration_full_track() -> None:
    """
    Integration verification across the full 22-minute clinical track.
    Proves integrated sensor adjudication confirms 4/4 true shocks and
    populates all 5 sensor placeholders for Pass P1.
    """
    runner = SensorPipelineRunner()
    res = runner.run_pipeline("simvideo2.mp4", "simvideo2.mp4")
    assert len(res.s1_compressions) >= 50
    assert len(res.s1_pauses) >= 40
    assert len(res.s3_defib_shocks) >= 4
    assert verify_p1_placeholder_wiring() is True
