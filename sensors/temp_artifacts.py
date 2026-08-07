"""
sensors/temp_artifacts.py — Repository-Local Transient Artifact Manager.

Enforces Decision 033 / F-036:
1. Never writes intermediate media/audio extractions to shared directories (/tmp).
2. Uses repo-local .resus_qc_tmp/ directory with strict user-only (0700) permissions.
3. Guarantees cleanup via try...finally and signal handling (SIGTERM).
4. Executes startup sweep to purge pre-existing stale artifacts from crashed runs.
5. Fails loudly with path, exit code, and stderr on ffmpeg or creation failures.
"""

from __future__ import annotations

from contextlib import contextmanager
import logging
import os
from pathlib import Path
import shutil
import signal
import subprocess
from typing import Generator
import uuid

_ACTIVE_TEMP_FILES: set[Path] = set()
_SIGTERM_REGISTERED = False


def _sigterm_handler(signum: int, frame: object) -> None:
    for p in list(_ACTIVE_TEMP_FILES):
        try:
            p.unlink(missing_ok=True)
        except Exception:
            pass
    # Exit with standard signal code
    os._exit(128 + signum)


def get_repo_temp_dir() -> Path:
    """Returns absolute path to the repository-local temporary directory."""
    return Path(__file__).resolve().parent.parent / ".resus_qc_tmp"


def init_repo_temp_dir(sweep: bool = True) -> Path:
    """
    Initializes the repository-local temporary directory with 0700 permissions.
    If sweep=True, removes any existing files from previous crashed runs.
    """
    global _SIGTERM_REGISTERED
    temp_dir = get_repo_temp_dir()
    temp_dir.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(temp_dir, 0o700)
    except Exception as e:
        logging.warning(f"Could not chmod 0700 on {temp_dir}: {e}")

    if sweep:
        for item in temp_dir.iterdir():
            try:
                if item.is_file() or item.is_symlink():
                    item.unlink(missing_ok=True)
                elif item.is_dir():
                    shutil.rmtree(item, ignore_errors=True)
            except Exception as e:
                logging.warning(f"Startup sweep failed to remove stale artifact {item}: {e}")

    if not _SIGTERM_REGISTERED:
        try:
            signal.signal(signal.SIGTERM, _sigterm_handler)
            _SIGTERM_REGISTERED = True
        except (ValueError, AttributeError):
            pass  # Not in main thread or signal unsupported

    return temp_dir


@contextmanager
def transient_audio_extract(
    video_path: str | Path,
    sr: int = 16000,
    mono: bool = True,
    sweep_on_init: bool = True,
) -> Generator[Path, None, None]:
    """
    Extracts an audio track from a video file into a repository-local temporary file
    with guaranteed lifecycle cleanup on normal return, exceptions, and interrupts.
    """
    vpath = Path(video_path).resolve()
    if not vpath.exists():
        raise FileNotFoundError(f"Video file not found: {vpath}")

    temp_dir = init_repo_temp_dir(sweep=sweep_on_init)
    out_file = temp_dir / f"extract_{uuid.uuid4().hex}.wav"
    _ACTIVE_TEMP_FILES.add(out_file)

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(vpath),
        "-vn",
        "-ar",
        str(sr),
        "-loglevel",
        "error",
    ]
    if mono:
        cmd.extend(["-ac", "1"])
    cmd.append(str(out_file))

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(
                f"ffmpeg audio extraction failed (exit {proc.returncode}) for {vpath} -> {out_file}:\n"
                f"{proc.stderr}"
            )
        if not out_file.exists() or out_file.stat().st_size == 0:
            raise RuntimeError(
                f"ffmpeg exited 0 but target audio file was not created or empty: {out_file}"
            )

        yield out_file

    finally:
        _ACTIVE_TEMP_FILES.discard(out_file)
        try:
            out_file.unlink(missing_ok=True)
        except Exception as e:
            logging.error(f"Failed to cleanup transient audio extract {out_file}: {e}")
