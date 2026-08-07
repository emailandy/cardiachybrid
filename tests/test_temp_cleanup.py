"""
tests/test_temp_cleanup.py — Verification of PHI Containment and Transient Artifact Lifecycle (F-036 / Decision 033).

Asserts:
1. Clean Run Guarantee: Transient audio extracts are deleted immediately after context exit.
2. Exception Guarantee: Transient audio extracts are deleted even when exceptions occur.
3. Startup Sweep Guarantee: Stale artifacts left by previous crashes/kills are purged on initialization.
"""

from __future__ import annotations

from pathlib import Path
import pytest

from sensors.temp_artifacts import (
    get_repo_temp_dir,
    init_repo_temp_dir,
    transient_audio_extract,
)


def test_clean_run_guarantee() -> None:
    """Verifies that transient audio extraction cleans up completely on normal exit."""
    video_path = Path("tests/video/vidsim2.mp4")
    if not video_path.exists():
        pytest.skip(f"Test video not found: {video_path}")

    temp_dir = get_repo_temp_dir()

    with transient_audio_extract(video_path) as temp_wav:
        assert temp_wav.exists()
        assert temp_wav.stat().st_size > 0
        assert temp_wav.parent == temp_dir

    # After exit, file must be unlinked and directory empty
    assert not temp_wav.exists()
    assert len(list(temp_dir.glob("*"))) == 0


def test_exception_cleanup_guarantee() -> None:
    """Verifies that transient audio extracts are cleaned up when an exception occurs inside context."""
    video_path = Path("tests/video/vidsim2.mp4")
    if not video_path.exists():
        pytest.skip(f"Test video not found: {video_path}")

    temp_dir = get_repo_temp_dir()
    recorded_path: Path | None = None

    with pytest.raises(RuntimeError, match="Simulated mid-pipeline failure"):
        with transient_audio_extract(video_path) as temp_wav:
            recorded_path = temp_wav
            assert temp_wav.exists()
            raise RuntimeError("Simulated mid-pipeline failure")

    assert recorded_path is not None
    assert not recorded_path.exists()
    assert len(list(temp_dir.glob("*"))) == 0


def test_startup_sweep_guarantee() -> None:
    """Verifies that startup sweep purges pre-existing stale artifacts left by prior crashes."""
    temp_dir = init_repo_temp_dir(sweep=True)
    stale_file = temp_dir / "stale_crashed_run.wav"
    stale_file.write_text("dummy stale un-deleted PHI audio content")
    assert stale_file.exists()

    # Re-running init_repo_temp_dir with sweep=True must purge the stale artifact
    init_repo_temp_dir(sweep=True)
    assert not stale_file.exists()
    assert len(list(temp_dir.glob("*"))) == 0
