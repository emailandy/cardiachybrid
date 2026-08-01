"""
Unit test suite for QI metrics layer (D10).
Verifies:
  1. Hand-computed 10-minute case with three known interruptions yields CCF to 3 decimals.
  2. CCF denominator option (c) correctly excludes sustained ROSC periods (Q-012).
  3. Zero shocks yields NULL (None), not 0, for all peri-shock metrics.
  4. Ratio metrics record both numerator and denominator explicitly.
  5. S7 ASR-dependent metrics emit NULL with reason 'requires S7 diarized ASR'.
  6. Two REDCap calc field replacements emit with source='REDCAP_CALC_REPLACEMENT'.
  7. Every row carries declarative metric_definition_version from definitions.yaml.
"""
from __future__ import annotations

import re
from pathlib import Path
import pytest

from fixtures.synthetic_streams import get_maximal_stream, get_degraded_stream, get_sparse_stream
from generated.models import Event, EventStream, Interval
from metrics.compute import (
    MetricRow,
    compute_case_metrics,
    compute_ccf,
    get_metric_definition_version,
)


def _make_10_min_case_stream(with_rosc: bool = False) -> EventStream:
    """Create a 10-minute (600.0s) stream with three known CCIs (10s, 15s, 20s)."""
    events = [
        Event(type="cpr_initiated_ed", timestamp_s=0.0, attributes={}, evidence=[]),
        Event(type="ems_handoff_end", timestamp_s=600.0, attributes={}, evidence=[]),
    ]
    intervals = [
        Interval(
            type="compression_interruption",
            t_start_s=100.0,
            t_end_s=110.0,
            duration_s=10.0,
            attributes={},
        ),
        Interval(
            type="compression_interruption",
            t_start_s=250.0,
            t_end_s=265.0,
            duration_s=15.0,
            attributes={},
        ),
        Interval(
            type="compression_interruption",
            t_start_s=400.0,
            t_end_s=420.0,
            duration_s=20.0,
            attributes={},
        ),
    ]
    if with_rosc:
        # Add 60.0s sustained ROSC interval
        intervals.append(
            Interval(
                type="sustained_rosc",
                t_start_s=300.0,
                t_end_s=360.0,
                duration_s=60.0,
                attributes={},
            )
        )
    return EventStream(
        case_id="case_10min",
        events=events,
        intervals=intervals,
        coverage=[],
        fields=get_maximal_stream().fields,
    )


def test_ccf_hand_computed_10_min_case():
    """Verify hand-computed 10-minute case with three known interruptions to 3 decimals."""
    stream = _make_10_min_case_stream(with_rosc=False)
    version = get_metric_definition_version()
    row = compute_ccf(stream, version)
    # Total time = 600.0, CCI time = 10 + 15 + 20 = 45.0
    # Numerator = 555.0, Denominator = 600.0 -> 555.0 / 600.0 = 0.925
    assert row.value == 0.925
    assert row.numerator == 555.0
    assert row.denominator == 600.0
    assert row.null_reason is None
    assert row.metric_definition_version == version


def test_ccf_option_c_excluding_rosc():
    """Verify candidate (c) excludes sustained ROSC periods from denominator (Q-012)."""
    stream = _make_10_min_case_stream(with_rosc=True)
    version = get_metric_definition_version()
    row = compute_ccf(
        stream,
        version,
        config={"ccf_denominator_mode": "first_compression_to_termination_excluding_rosc"},
    )
    # Denominator = 600.0 - 60.0 = 540.0
    # Numerator = 540.0 - 45.0 = 495.0 -> 495.0 / 540.0 = 0.916666... -> 0.917
    assert row.denominator == 540.0
    assert row.numerator == 495.0
    assert row.value == 0.917
    assert row.null_reason is None


def test_ccf_epochs_10_min_case():
    """Verify CCF array across sequential 2-minute (120s) epochs on 10-minute case."""
    stream = _make_10_min_case_stream(with_rosc=False)
    rows = compute_case_metrics(stream)
    row_map = {r.metric_name: r for r in rows}
    row = row_map["ccf_by_2min_epoch"]
    assert row.value == [0.917, 1.0, 0.875, 0.833, 1.0]
    assert row.numerator == 555.0
    assert row.denominator == 600.0
    assert row.null_reason is None


def test_zero_shocks_yields_null_not_zero():
    """Assert that a case with 0 shocks yields NULL (None), not 0, for peri-shock metrics."""
    stream = _make_10_min_case_stream()
    rows = compute_case_metrics(stream)
    row_map = {r.metric_name: r for r in rows}

    for name in (
        "peri_shock_pause_pre_s",
        "peri_shock_pause_post_s",
        "median_peri_shock_pause_pre_s",
        "median_peri_shock_pause_post_s",
        "pre_charged_shock_rate",
    ):
        r = row_map[name]
        assert r.value is None, f"Metric {name} emitted {r.value!r} instead of None (NULL) for zero shocks"
        assert r.null_reason == "zero shocks in case"


def test_asr_metrics_emit_null_with_reason():
    """Assert S7 ASR-dependent metrics emit NULL with null_reason 'requires S7 diarized ASR'."""
    stream = _make_10_min_case_stream()
    rows = compute_case_metrics(stream)
    row_map = {r.metric_name: r for r in rows}

    for name in ("closed_loop_completion_rate", "n_unacknowledged_directives"):
        r = row_map[name]
        assert r.value is None
        assert r.null_reason == "requires S7 diarized ASR"


def test_redcap_calc_replacements_emit_with_source():
    """Assert the two REDCap calc replacement metrics emit with source 'REDCAP_CALC_REPLACEMENT'."""
    stream = _make_10_min_case_stream()
    rows = compute_case_metrics(stream)
    row_map = {r.metric_name: r for r in rows}

    for name in ("dur_mccd_app_ed_secs_v2", "duration_ventilator_place_v2"):
        r = row_map[name]
        assert r.source == "REDCAP_CALC_REPLACEMENT"


def test_metric_definition_version_hash():
    """Assert metric_definition_version is an 8-char hex string derived from definitions.yaml prose."""
    ver = get_metric_definition_version()
    assert len(ver) == 8
    assert re.match(r"^[0-9a-f]{8}$", ver), f"Version {ver!r} is not an 8-char hex string"

    stream = _make_10_min_case_stream()
    rows = compute_case_metrics(stream)
    for r in rows:
        assert r.metric_definition_version == ver


def test_all_metrics_on_synthetic_streams():
    """Verify compute_case_metrics runs without exception across synthetic fixtures."""
    for stream_func in (get_maximal_stream, get_degraded_stream, get_sparse_stream):
        stream = stream_func()
        rows = compute_case_metrics(stream)
        assert len(rows) >= 15
        for r in rows:
            assert isinstance(r, MetricRow)
            assert r.metric_definition_version
