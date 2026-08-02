import pytest
from pathlib import Path
from prompts.registry import (
    assert_no_field_names, manifest, load, anchor, 
    manifest_sha, prompt_set_sha, check_anchors
)

def test_prompt_set_sha_strict():
    sha = prompt_set_sha(strict=True)
    assert isinstance(sha, str) and len(sha) == 16

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

def test_passes_round_trip():
    source = Path("tests/fixtures/passes_v2.0_source.md").read_text()
    p1 = Path("prompts/passes/p1_harvest.v2.0.md").read_text()
    p2 = Path("prompts/passes/p2_verify.v2.0.md").read_text()
    p3 = Path("prompts/passes/p3_adjudicate.v2.0.md").read_text()
    p4a = Path("prompts/passes/p4a_team_items.v2.0.md").read_text()
    p4b = Path("prompts/passes/p4b_team_global.v2.0.md").read_text()
    p5 = Path("prompts/passes/p5_notes.v2.0.md").read_text()

    p1_part = source.split("=== P1 ===\n")[1].split("=== P2 ===\n")[0]
    p2_part = source.split("=== P2 ===\n")[1].split("=== P3 ===\n")[0]
    p3_part = source.split("=== P3 ===\n")[1].split("=== P4A ===\n")[0]
    p4a_part = source.split("=== P4A ===\n")[1].split("=== P4B ===\n")[0]
    p4b_part = source.split("=== P4B ===\n")[1].split("=== P5 ===\n")[0]
    p5_part = source.split("=== P5 ===\n")[1]

    assert p1 == p1_part, "P1 harvest template does not match byte-identical source section"
    assert p2 == p2_part, "P2 verify template does not match byte-identical source section"
    assert p3 == p3_part, "P3 adjudicate template does not match byte-identical source section"
    assert p4a == p4a_part, "P4A team items template does not match byte-identical source section"
    assert p4b == p4b_part, "P4B team global template does not match byte-identical source section"
    assert p5 == p5_part, "P5 notes template does not match byte-identical source section"

    for p, name in [
        (p1, "p1_harvest"),
        (p2, "p2_verify"),
        (p3, "p3_adjudicate"),
        (p4a, "p4a_team_items"),
        (p4b, "p4b_team_global"),
        (p5, "p5_notes"),
    ]:
        assert_no_field_names(p, name)

def test_placeholder_validation():
    from prompts.registry import validate_template_placeholders
    p1 = Path("prompts/passes/p1_harvest.v2.0.md").read_text()
    p2 = Path("prompts/passes/p2_verify.v2.0.md").read_text()
    p3 = Path("prompts/passes/p3_adjudicate.v2.0.md").read_text()
    p4a = Path("prompts/passes/p4a_team_items.v2.0.md").read_text()
    p4b = Path("prompts/passes/p4b_team_global.v2.0.md").read_text()
    p5 = Path("prompts/passes/p5_notes.v2.0.md").read_text()

    # Active templates should pass validation cleanly
    for p, name in [
        (p1, "p1_harvest"),
        (p2, "p2_verify"),
        (p3, "p3_adjudicate"),
        (p4a, "p4a_team_items"),
        (p4b, "p4b_team_global"),
        (p5, "p5_notes"),
    ]:
        validate_template_placeholders(p, name)

    # Undeclared placeholder should raise ValueError
    with pytest.raises(ValueError, match="uses undeclared placeholders"):
        validate_template_placeholders(p1 + " {undeclared_fake_param} ", "p1_harvest")

    # Unused declared placeholder should raise ValueError
    with pytest.raises(ValueError, match="declares unused placeholders"):
        validate_template_placeholders(" {chunk_index} ", "p1_harvest")
