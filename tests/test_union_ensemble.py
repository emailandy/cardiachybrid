"""
tests/test_union_ensemble.py

Unit test suite verifying:
1. k draws produce k× calls per window in run_case.py (mocked, zero network).
2. Union preserves an event appearing in only 1 of k draws (zero drops before P3).
3. Cluster metadata: n_draws, t_spread_s, t_median_s correct on synthetic inputs;
   t_spread_s is 'n/a' when n_draws == 1.
4. k resolves from VERSIONS.yaml (model_binding), not hardcoded literals.
"""

from __future__ import annotations

import argparse
from unittest.mock import MagicMock, patch
import pytest

from generated.models import Event, EventStream, Interval, CaseFields, Evidence
from ingest.ensemble import (
    CROSS_DRAW_CLUSTER_TOLERANCE_S,
    union_and_cluster_draw_streams,
)
from prompts.registry import get_model_binding


def test_cross_draw_cluster_tolerance_is_declared_constant():
    """Verify cluster tolerance is declared and derived from Decision 017/018."""
    assert CROSS_DRAW_CLUSTER_TOLERANCE_S == 3.0


def test_k_resolves_from_versions_yaml():
    """Verify Pass 1 ensemble_k resolves from prompts/VERSIONS.yaml."""
    b_p1 = get_model_binding("pass_1")
    assert "ensemble_k" in b_p1
    assert b_p1["ensemble_k"] == 3


def test_union_preserves_single_draw_event():
    """
    Union guarantee: An event present in only 1 of 3 draws must be preserved
    with n_draws=1, t_spread_s='n/a', and t_median_s=t.
    """
    # Draw 0 has shock at 165.0s
    ev1 = Event(
        type="defibrillation_shock",
        timestamp_s=165.0,
        t_start_s=165.0,
        t_precision_s=2.0,
        evidence=[Evidence(modality="visual", t=165.0, desc="Defibrillator shock delivered")],
    )
    stream0 = EventStream(case_id="TEST-CASE", events=[ev1], intervals=[], coverage=[], fields=CaseFields())

    # Draw 1 & 2 have no shocks
    stream1 = EventStream(case_id="TEST-CASE", events=[], intervals=[], coverage=[], fields=CaseFields())
    stream2 = EventStream(case_id="TEST-CASE", events=[], intervals=[], coverage=[], fields=CaseFields())

    clustered = union_and_cluster_draw_streams([stream0, stream1, stream2])

    assert len(clustered.events) == 1
    res_ev = clustered.events[0]
    assert res_ev.type == "defibrillation_shock"
    assert res_ev.timestamp_s == 165.0
    assert res_ev.attributes["n_draws"] == 1
    assert res_ev.attributes["t_spread_s"] == "n/a"
    assert res_ev.attributes["t_median_s"] == 165.0
    assert res_ev.attributes["draw_timestamps"] == [165.0]


def test_cluster_metadata_multi_draw_agreement():
    """
    Multi-draw clustering: Events across draws within tolerance cluster together
    and compute n_draws, t_median_s, and numeric t_spread_s.
    """
    ev_d0 = Event(type="defibrillation_shock", timestamp_s=164.0, t_start_s=164.0, t_precision_s=2.0)
    ev_d1 = Event(type="defibrillation_shock", timestamp_s=165.0, t_start_s=165.0, t_precision_s=2.0)
    ev_d2 = Event(type="defibrillation_shock", timestamp_s=166.0, t_start_s=166.0, t_precision_s=2.0)

    stream0 = EventStream(case_id="TEST-CASE", events=[ev_d0], intervals=[], coverage=[], fields=CaseFields())
    stream1 = EventStream(case_id="TEST-CASE", events=[ev_d1], intervals=[], coverage=[], fields=CaseFields())
    stream2 = EventStream(case_id="TEST-CASE", events=[ev_d2], intervals=[], coverage=[], fields=CaseFields())

    clustered = union_and_cluster_draw_streams([stream0, stream1, stream2])

    assert len(clustered.events) == 1
    res_ev = clustered.events[0]
    assert res_ev.type == "defibrillation_shock"
    assert res_ev.attributes["n_draws"] == 3
    assert res_ev.attributes["t_median_s"] == 165.0
    assert res_ev.attributes["t_spread_s"] == 2.0  # 166.0 - 164.0
    assert res_ev.attributes["draw_timestamps"] == [164.0, 165.0, 166.0]


def test_cluster_metadata_two_draw_partial_agreement():
    """Two of three draws observe event: n_draws=2, numeric t_spread_s."""
    ev_d0 = Event(type="defibrillation_shock", timestamp_s=620.0, t_start_s=620.0)
    ev_d1 = Event(type="defibrillation_shock", timestamp_s=620.5, t_start_s=620.5)

    stream0 = EventStream(case_id="TEST-CASE", events=[ev_d0], intervals=[], coverage=[], fields=CaseFields())
    stream1 = EventStream(case_id="TEST-CASE", events=[ev_d1], intervals=[], coverage=[], fields=CaseFields())
    stream2 = EventStream(case_id="TEST-CASE", events=[], intervals=[], coverage=[], fields=CaseFields())

    clustered = union_and_cluster_draw_streams([stream0, stream1, stream2])

    assert len(clustered.events) == 1
    res_ev = clustered.events[0]
    assert res_ev.attributes["n_draws"] == 2
    assert res_ev.attributes["t_spread_s"] == 0.5
    assert res_ev.attributes["t_median_s"] == 620.25


def test_distinct_events_do_not_overcluster():
    """Events separated by more than tolerance remain separate candidates."""
    ev1 = Event(type="defibrillation_shock", timestamp_s=165.0, t_start_s=165.0)
    ev2 = Event(type="defibrillation_shock", timestamp_s=388.0, t_start_s=388.0)

    stream0 = EventStream(case_id="TEST-CASE", events=[ev1, ev2], intervals=[], coverage=[], fields=CaseFields())
    clustered = union_and_cluster_draw_streams([stream0])

    assert len(clustered.events) == 2
    assert clustered.events[0].attributes["n_draws"] == 1
    assert clustered.events[1].attributes["n_draws"] == 1


@patch("scripts.run_case.call_model_cached")
@patch("scripts.run_case.VertexClient")
def test_k_draws_produce_k_times_p1_calls(mock_vc_cls, mock_call_cached, tmp_path):
    """Verifies that k=3 produces exactly 4 windows × 3 draws = 12 P1 API calls."""
    from scripts.run_case import run_live

    mock_vc = MagicMock()
    mock_vc_cls.return_value = mock_vc

    # Mock return JSON for all passes
    p1_json = '{"case_id": "TEST", "events": [{"type": "defibrillation_shock", "timestamp_s": 165.0, "t_start_s": 165.0}], "intervals": [], "coverage": []}'
    p3_json = '{"case_id": "TEST", "events": [{"type": "defibrillation_shock", "timestamp_s": 165.0, "t_start_s": 165.0}], "intervals": [], "coverage": []}'
    p4a_json = '{"team_ratings": {}}'
    p4b_json = '{"team12_v2": 3}'
    p5_json = '{"section_name": "ED Airway", "clinical_anomalies_detected": false, "notes_markdown": "None"}'

    def side_effect(*args, **kwargs):
        pname = kwargs.get("pass_name", "")
        if "p1_win" in pname:
            return p1_json
        elif pname == "pass_3":
            return p3_json
        elif pname == "pass_4a":
            return p4a_json
        elif pname == "pass_4b":
            return p4b_json
        elif "pass_5" in pname:
            return p5_json
        return "{}"

    mock_call_cached.side_effect = side_effect

    args = argparse.Namespace(
        case_id="TEST-CASE",
        video="gs://videval/cardiac/simvideo2.mp4",
        k=3,
        with_sensors=False,
        with_p2=False,
        use_cache=False,
        media_resolution="low",
        no_bq=True,
        t0="2023-11-07T07:55:57",
        t0_source="burned_in_timecode",
        seed=42,
        run_id="test_run_k3",
        p1_model=None,
        p3_model=None,
        p4a_model=None,
        p4b_model=None,
        p5_model=None,
        out=str(tmp_path / "case.json"),
    )

    with patch("scripts.run_case.reduce_stream") as mock_reduce:
        mock_reduce.return_value = ([], [], [])
        run_live(args, duration_s=1363.78)

    p1_calls = [c for c in mock_call_cached.call_args_list if "p1_win" in c.kwargs.get("pass_name", "")]
    # 4 windows × k=3 = 12 calls
    assert len(p1_calls) == 12
    # Verify pass names include draw index
    pass_names = [c.kwargs.get("pass_name") for c in p1_calls]
    assert "p1_win_0_draw_0" in pass_names
    assert "p1_win_0_draw_1" in pass_names
    assert "p1_win_0_draw_2" in pass_names
    assert "p1_win_3_draw_2" in pass_names
