#!/usr/bin/env python3
"""Check npm for a new vercel version and vendor it if newer.

This script uses nodejs-wheel-binaries-powered npm and the existing
`scripts.update_vendor` helpers to avoid requiring a system Node.js.

If a newer version is vendored, it writes GitHub Actions outputs:
- updated=true
- new_version=<version>
Otherwise, it writes updated=false.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from scripts.update_vendor import VENDOR_DIR, npm_view, update_vendor

logger = logging.getLogger(__name__)


def _read_current_vendor_version() -> str:
    pkg_json = VENDOR_DIR / "package.json"
    data = json.loads(pkg_json.read_text())
    return str(data["version"])


def _write_github_output(**kwargs: str) -> None:
    out_path = Path(os.environ["GITHUB_OUTPUT"])
    lines = [f"{k}={v}" for k, v in kwargs.items()]
    with out_path.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main() -> int:
    """Check and update vendored vercel.

    Returns:
        0 if no update was needed, 1 if an error occurred.

    """
    current = _read_current_vendor_version()
    latest_meta = npm_view("latest")
    latest = str(latest_meta.get("version", ""))
    if not latest:
        logger.error("Could not determine latest vercel version from npm.")
        _write_github_output(updated="false")
        return 1

    if current == latest:
        logger.info("Already up-to-date: vercel@%s", current)
        _write_github_output(updated="false")
        return 0

    logger.info("Updating vendored vercel from %s to %s...", current, latest)
    update_vendor(version=latest)

    # Verify write
    resolved = _read_current_vendor_version()
    if resolved != latest:
        logger.error("Update failed: expected %s, found %s", latest, resolved)
        _write_github_output(updated="false")
        return 1

    logger.info("Vendored vercel@%s", latest)
    _write_github_output(updated="true", new_version=latest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
