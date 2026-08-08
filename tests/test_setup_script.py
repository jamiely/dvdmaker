"""Tests for the Ubuntu/Debian prerequisite setup script."""

import os
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "setup.sh"


def run_script(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT), *arguments],
        capture_output=True,
        text=True,
        check=False,
    )


def test_setup_script_is_executable_and_has_valid_bash_syntax():
    assert os.access(SCRIPT, os.X_OK)
    result = subprocess.run(
        ["bash", "-n", str(SCRIPT)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr


def test_setup_script_help():
    result = run_script("--help")
    assert result.returncode == 0
    assert "--check" in result.stdout
    assert "--dry-run" in result.stdout


def test_setup_script_dry_run_lists_every_package():
    result = run_script("--dry-run")
    assert result.returncode == 0
    assert "apt-get update" in result.stdout
    for package in [
        "python3",
        "python3-pip",
        "python3-venv",
        "make",
        "ffmpeg",
        "dvdauthor",
        "genisoimage",
        "lsdvd",
    ]:
        assert package in result.stdout


def test_setup_script_rejects_unknown_options():
    result = run_script("--unknown")
    assert result.returncode == 2
    assert "Unknown option" in result.stderr
