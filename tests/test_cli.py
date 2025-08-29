"""Test CLI functionality."""

from __future__ import annotations

import subprocess
import sys

import pytest

from vercel_cli.run import main


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
