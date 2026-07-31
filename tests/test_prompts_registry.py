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
    assert "prompts/system.txt" in str(exc.value)

def test_assert_no_field_names():
    with pytest.raises(ValueError) as exc:
        assert_no_field_names("This has num_rosc_episodes_ed_v2 in it", "test")
    assert "leaks REDCap field names" in str(exc.value)
    
    # Should not raise
    assert_no_field_names("This is a safe prompt with no field names", "test")
    
def test_check_anchors_gaps():
    gaps = check_anchors(fail_on_gap=False)
    # 39 required anchor cards are missing
    assert len(gaps) == 39
    for v in gaps.values():
        assert v == ["<no anchor card>"]
