"""
tests/test_model_params.py

Unit tests verifying that decoding parameters (temperature, thinking, seed)
are properly resolved from prompts/VERSIONS.yaml and propagated to VertexClient.generate().
Zero network calls (mocked).
"""

import argparse
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from prompts.registry import get_model_binding, manifest
from pipeline.vertex_client import VertexClient
from google.genai import types


def test_get_model_binding_resolves_all_declared_passes():
    m = manifest()
    declared_passes = m.get("model_binding", {})
    assert len(declared_passes) >= 6

    for pass_name, expected_binding in declared_passes.items():
        binding = get_model_binding(pass_name)
        assert binding["model"] == expected_binding["model"]
        assert binding["temperature"] == expected_binding["temperature"]
        assert binding.get("thinking") == expected_binding.get("thinking")
        assert binding.get("ensemble_k") == expected_binding.get("ensemble_k")


def test_pass_3_adjudication_specifically_resolves_to_zero_temperature():
    """
    P3 adjudication pass merges, splits, re-times, and reclassifies events.
    It MUST be specified as greedy decoding (temperature: 0.0).
    """
    binding = get_model_binding("pass_3")
    assert binding["temperature"] == 0.0, f"P3 temperature MUST be 0.0, got {binding['temperature']}"
    assert binding["thinking"] == "high"


def test_missing_pass_raises_key_error_loudly():
    """Missing pass name in VERSIONS.yaml must raise KeyError and not default silently."""
    with pytest.raises(KeyError, match="not found in VERSIONS.yaml model_binding"):
        get_model_binding("nonexistent_pass_xyz")


def test_vertex_client_generate_receives_declared_parameters_and_seed():
    """
    Verifies that VertexClient.generate properly populates GenerateContentConfig
    with temperature, thinking_config, and seed.
    """
    mock_genai_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = '{"case_id": "TEST-1", "events": [], "intervals": [], "coverage": []}'
    mock_response.candidates = [MagicMock(finish_reason="STOP")]
    mock_response.usage_metadata.prompt_token_count = 100
    mock_response.usage_metadata.candidates_token_count = 50
    mock_genai_client.models.generate_content.return_value = mock_response

    vc = VertexClient(project="nodepeel", location="global")
    vc.client = mock_genai_client

    # Test P1 binding parameters
    b_p1 = get_model_binding("pass_1")
    vc.generate(
        model=b_p1["model"],
        contents=["test_content"],
        temperature=b_p1["temperature"],
        thinking_str=b_p1.get("thinking"),
        seed=42,
        pass_name="pass_1",
    )

    call_args = mock_genai_client.models.generate_content.call_args
    assert call_args is not None
    config = call_args.kwargs.get("config")
    assert config is not None
    assert config.temperature == b_p1["temperature"]
    assert config.seed == 42
    assert config.thinking_config is not None
    assert config.thinking_config.thinking_level == "LOW"

    # Test P3 binding parameters (greedy 0.0, thinking HIGH)
    b_p3 = get_model_binding("pass_3")
    vc.generate(
        model=b_p3["model"],
        contents=["test_content_p3"],
        temperature=b_p3["temperature"],
        thinking_str=b_p3.get("thinking"),
        seed=42,
        pass_name="pass_3",
    )

    call_args_p3 = mock_genai_client.models.generate_content.call_args
    config_p3 = call_args_p3.kwargs.get("config")
    assert config_p3.temperature == 0.0
    assert config_p3.seed == 42
    assert config_p3.thinking_config.thinking_level == "HIGH"


def test_run_live_plumbing_propagates_parameters_to_all_passes(tmp_path):
    """
    Simulates run_live with a mocked VertexClient to assert that all 5 passes
    (P1, P3, P4a, P4b, P5) pass their declared temperatures and seed to call_model_cached.
    """
    from scripts.run_case import run_live

    out_file = tmp_path / "case.json"
    args = argparse.Namespace(
        case_id="TEST-CASE",
        t0="2023-11-07T07:55:57",
        t0_source="burned_in_timecode",
        run_id="test_run",
        video="gs://videval/cardiac/simvideo2.mp4",
        use_cache=False,
        media_resolution="low",
        with_sensors=False,
        with_p2=False,
        seed=42,
        k=1,
        p1_model=None,
        p3_model=None,
        p4a_model=None,
        p4b_model=None,
        p5_model=None,
        no_bq=True,
        out=str(out_file),
    )

    recorded_calls = []

    def mock_call_model(vc, model, contents, pass_name, **kwargs):
        recorded_calls.append({
            "pass_name": pass_name,
            "model": model,
            "temperature": kwargs.get("temperature"),
            "thinking_str": kwargs.get("thinking_str"),
            "seed": kwargs.get("seed"),
        })
        if pass_name.startswith("p1_"):
            return '{"case_id": "TEST-CASE", "events": [], "intervals": [], "coverage": []}'
        elif pass_name == "p3_adjudicate":
            return '{"adjudication_notes": "ok", "modifications": []}'
        elif pass_name.startswith("p4"):
            return '{"team_score": 5}'
        else:
            return "Section note narrative"

    with patch("scripts.run_case.call_model_cached", side_effect=mock_call_model), \
         patch("scripts.run_case.VertexClient"):
        run_live(args, duration_s=1363.78)

    # 4 P1 windows, 1 P3, 1 P4a, 1 P4b, 7 P5 sections = 14 total calls
    assert len(recorded_calls) == 14

    # Verify P1 calls (windows 0..3)
    p1_calls = [c for c in recorded_calls if c["pass_name"].startswith("p1_win_")]
    assert len(p1_calls) == 4
    for c in p1_calls:
        assert c["temperature"] == get_model_binding("pass_1")["temperature"]
        assert c["thinking_str"] == get_model_binding("pass_1").get("thinking")
        assert c["seed"] == 42

    # Verify P3 call
    p3_call = next(c for c in recorded_calls if c["pass_name"] == "p3_adjudicate")
    assert p3_call["temperature"] == 0.0
    assert p3_call["thinking_str"] == "high"
    assert p3_call["seed"] == 42

    # Verify P4a & P4b calls
    p4a_call = next(c for c in recorded_calls if c["pass_name"] == "p4a_team")
    assert p4a_call["temperature"] == get_model_binding("pass_4a")["temperature"]
    assert p4a_call["seed"] == 42

    p4b_call = next(c for c in recorded_calls if c["pass_name"] == "p4b_team")
    assert p4b_call["temperature"] == get_model_binding("pass_4b")["temperature"]
    assert p4b_call["seed"] == 42

    # Verify P5 calls
    p5_calls = [c for c in recorded_calls if c["pass_name"].startswith("p5_")]
    assert len(p5_calls) == 7
    for c in p5_calls:
        assert c["temperature"] == get_model_binding("pass_5")["temperature"]
        assert c["seed"] == 42
