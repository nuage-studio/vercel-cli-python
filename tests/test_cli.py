"""Test CLI functionality."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from vercel_cli.run import main, run_vercel


def test_vercel_cli_subprocess() -> None:
    """Test vercel CLI using subprocess to ensure the binary is functional."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "vercel_cli.run", "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,  # 30 second timeout
        )

        # The command should succeed
        assert result.returncode == 0, (
            f"Command failed with return code {result.returncode}"
        )

        # "Vercel CLI 46.1.0" goes to stderr, version number goes to stdout
        stderr_output = result.stderr.strip()
        stdout_output = result.stdout.strip()
        assert "Vercel CLI" in stderr_output, (
            f"Expected 'Vercel CLI' in stderr, got: {stderr_output}"
        )
        assert any(char.isdigit() for char in stdout_output), (
            f"Expected version number in stdout, got: {stdout_output}"
        )

    except subprocess.TimeoutExpired:
        pytest.fail("vercel --version command timed out")
    except FileNotFoundError:
        pytest.skip("vercel CLI not available in PATH")


def test_vercel_cli_main_function() -> None:
    """Test vercel CLI using the main function directly (pure Python)."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(sys, "argv", [sys.argv[0], "--version"])
        result = main()
        assert result == 0, f"Main function returned {result}, expected 0"


def test_run_vercel_programmatic_version() -> None:
    """Test run_vercel function with explicit arguments."""
    result = run_vercel(["--version"])
    assert result == 0, f"run_vercel returned {result}, expected 0"


def test_run_vercel_programmatic_with_cwd() -> None:
    """Test run_vercel function with custom working directory."""
    # Use current directory for testing
    current_dir = Path.cwd()
    result = run_vercel(["--version"], cwd=current_dir)
    assert result == 0, f"run_vercel with cwd returned {result}, expected 0"


def test_run_vercel_programmatic_with_env() -> None:
    """Test run_vercel function with custom environment variables."""
    env = {"TEST_VAR": "test_value"}
    result = run_vercel(["--version"], env=env)
    assert result == 0, f"run_vercel with env returned {result}, expected 0"


def test_run_vercel_programmatic_invalid_command() -> None:
    """Test run_vercel function with invalid command arguments."""
    result = run_vercel(["--invalid-flag-that-does-not-exist"])
    # Should return non-zero exit code for invalid command
    assert result != 0, (
        f"run_vercel with invalid args should return non-zero, got {result}"
    )


def test_run_vercel_programmatic_empty_args() -> None:
    """Test run_vercel function with empty arguments list."""
    result = run_vercel([])
    # Empty args should show help or version info, but should not crash
    assert isinstance(result, int), "run_vercel should return an integer exit code"
