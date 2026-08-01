import pytest
from pathlib import Path
from prompts.registry import (
    assert_no_field_names, manifest, load, anchor, 
    manifest_sha, prompt_set_sha, check_anchors
)

def test_prompt_set_sha_strict():
    with pytest.raises(FileNotFoundError) as exc:
        prompt_set_sha(strict=True)
    assert "Missing" in str(exc.value)
    assert "prompts/passes/p1.txt" in str(exc.value)

def test_assert_no_field_names():
    with pytest.raises(ValueError) as exc:
        assert_no_field_names("This has num_rosc_episodes_ed_v2 in it", "test")
    assert "leaks REDCap field names" in str(exc.value)
    
    # Should not raise
    assert_no_field_names("This is a safe prompt with no field names", "test")
    
def test_check_anchors_gaps():
    # Verify zero gaps across all 39 required anchor cards
    from prompts.registry import check_anchors
    all_gaps = check_anchors(fail_on_gap=True)
    assert all_gaps == {}, f"check_anchors reported gaps across 39 anchor cards: {all_gaps}"

def test_check_anchors_flat_list_fails(tmp_path, monkeypatch):
    card = """
defining_instants: {}
audio_device: []
speech: {}
visual: []
required_attributes:
  - t_start_s
  - t_end_s
disambiguation: []
hard_rules: []
abstain_if: []
"""
    fake_anchors = tmp_path / "anchors"
    fake_anchors.mkdir()
    (fake_anchors / "compression_interruption.yaml").write_text(card)
    
    monkeypatch.setattr("prompts.registry.manifest", lambda: {"anchors_dir": str(fake_anchors)})
    gaps = check_anchors(types=["compression_interruption"], fail_on_gap=False)
    assert "compression_interruption" in gaps
    assert "reasons" in gaps["compression_interruption"]
    assert "absent from required_attributes mapping" in gaps["compression_interruption"]["reasons"]

def test_constitution_round_trip():
    original = Path("tests/fixtures/constitution_v2.0_source.md").read_text()
    constitution = Path("prompts/system/constitution.v2.0.md").read_text()
    
    cov = Path("prompts/fragments/coverage_rules.md").read_text()
    time_cal = Path("prompts/fragments/timestamp_calibration.md").read_text()
    fail = Path("prompts/fragments/failure_modes.md").read_text()
    
    reconstructed = constitution.replace("{{fragment:coverage_rules}}", cov)
    reconstructed = reconstructed.replace("{{fragment:timestamp_calibration}}", time_cal)
    reconstructed = reconstructed.replace("{{fragment:failure_modes}}", fail)
    
    assert reconstructed == original
    
    assert_no_field_names(constitution, "constitution")
    assert_no_field_names(cov, "coverage_rules")
    assert_no_field_names(time_cal, "timestamp_calibration")
    assert_no_field_names(fail, "failure_modes")
