from __future__ import annotations

import argparse
import logging
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from vercel_cli import vendor_cli

if TYPE_CHECKING:
    from pathlib import Path


def test_vendor_cli_check_sets_outputs_and_logs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger=vendor_cli.__name__)
    monkeypatch.setattr(
        vendor_cli, "read_vendored_version", MagicMock(return_value="1.0.0")
    )
    monkeypatch.setattr(
        vendor_cli, "resolve_latest_version", MagicMock(return_value="1.2.3")
    )

    called: dict[str, str] = {}

    def fake_update(version: str) -> None:
        called["update"] = version

    monkeypatch.setattr(vendor_cli, "update_vendor", fake_update)

    out_file = tmp_path / "gha.out"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out_file))

    rc = vendor_cli.cmd_check(argparse.Namespace(vendor=True, github_outputs=True))
    assert rc == 0
    assert "1.2.3" in caplog.text
    content = out_file.read_text()
    assert "updated=true" in content
    assert "new_version=1.2.3" in content
    assert called.get("update") == "1.2.3"


def test_vendor_cli_update_latest(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger=vendor_cli.__name__)
    monkeypatch.setattr(vendor_cli, "resolve_latest_version", lambda: "2.0.0")

    updated: dict[str, str] = {}

    def fake_update(version: str) -> None:
        updated["v"] = version

    monkeypatch.setattr(vendor_cli, "update_vendor", fake_update)

    out_file = tmp_path / "gha.out"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out_file))

    rc = vendor_cli.cmd_update(
        argparse.Namespace(version="latest", github_outputs=True)
    )
    assert rc == 0
    assert updated.get("v") == "2.0.0"
    assert "2.0.0" in caplog.text
    content = out_file.read_text()
    assert "updated=true" in content
    assert "new_version=2.0.0" in content


def test_vendor_cli_main_invokes_subcommands(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level("INFO", logger=vendor_cli.__name__)
    monkeypatch.setattr(
        vendor_cli, "resolve_latest_version", MagicMock(return_value="3.3.3")
    )

    monkeypatch.setattr(vendor_cli, "update_vendor", MagicMock())
    with pytest.raises(SystemExit) as ei:
        vendor_cli.main(["update", "latest"])
    assert ei.value.code == 0
    assert "3.3.3" in caplog.text

    monkeypatch.setattr(
        vendor_cli, "read_vendored_version", MagicMock(return_value="1.0.0")
    )
    monkeypatch.setattr(
        vendor_cli, "resolve_latest_version", MagicMock(return_value="1.0.0")
    )
    with pytest.raises(SystemExit) as ei2:
        vendor_cli.main(["check"])
    assert ei2.value.code == 0
