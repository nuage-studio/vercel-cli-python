"""CLI to help vendoring the Vercel CLI."""

from __future__ import annotations

import argparse
import logging
from typing import NoReturn

from .vendor_update import (
    read_vendored_version,
    resolve_latest_version,
    update_vendor,
    write_github_outputs,
)

logger = logging.getLogger(__name__)
__all__ = ["cmd_check", "cmd_update", "main"]


def cmd_update(args: argparse.Namespace) -> int:
    """Update the vendored version of the Vercel CLI.

    Returns:
        int: 0 if successful, 1 if there was an error.

    """
    version = args.version or "latest"
    if version == "latest":
        version = resolve_latest_version()
    update_vendor(version=version)
    if args.github_outputs:
        write_github_outputs(updated="true", new_version=version)
    logger.info(version)
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    """Check the current version of the Vercel CLI against the latest version.

    Returns:
        int: 0 if successful, 1 if there was an error.

    """
    current = read_vendored_version()
    latest = resolve_latest_version()
    if latest and latest != current:
        if args.vendor:
            update_vendor(latest)
        if args.github_outputs:
            write_github_outputs(updated="true", new_version=latest)
        logger.info(latest)
        return 0
    if args.github_outputs:
        write_github_outputs(updated="false")
    logger.info(current)
    return 0


def main(argv: list[str] | None = None) -> NoReturn:
    """Entry point for the CLI.

    Raises:
        SystemExit: Always exits with 0.

    """
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser(prog="vendor")
    ap.add_argument("-q", "--quiet", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)

    ap_update = sub.add_parser("update", help="Vendor a specific or latest version")
    ap_update.add_argument(
        "version", nargs="?", help="npm version (e.g. 46.0.2) or 'latest'"
    )
    ap_update.add_argument(
        "--github-outputs",
        action="store_true",
        help="Write GHA outputs updated/new_version",
    )
    ap_update.set_defaults(func=cmd_update)

    ap_check = sub.add_parser(
        "check", help="Check npm latest vs current and optionally vendor"
    )
    ap_check.add_argument(
        "--vendor", action="store_true", help="Vendor latest if newer than current"
    )
    ap_check.add_argument(
        "--github-outputs",
        action="store_true",
        help="Write GHA outputs updated/new_version",
    )
    ap_check.set_defaults(func=cmd_check)

    args = ap.parse_args(argv)
    rc = args.func(args)
    raise SystemExit(rc)
