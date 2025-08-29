#!/usr/bin/env python3
"""Update the vendored npm package.

This vendors the specified `vercel` npm version into `vercel_cli/vendor`,
including production dependencies, with integrity verification and safe
extraction.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import logging
import shutil
import tarfile
import tempfile
from contextlib import suppress
from pathlib import Path
from typing import Any

from nodejs_wheel.executable import npm

ROOT = Path(__file__).resolve().parents[1]
VENDOR_DIR = ROOT / "vercel_cli" / "vendor"

logger = logging.getLogger(__name__)


def _decode_maybe_bytes(value: bytes | str | None) -> str:
    """Return a text string for subprocess outputs that may be bytes or str.

    Args:
        value: The value to decode (bytes|str|None).

    Returns:
        Decoded string (empty string for None).

    """
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return str(value)


def npm_pack(version: str, out_dir: Path) -> Path:
    """Pack a npm package into a tarball.

    Args:
        version: npm version to pack
        out_dir: directory to pack into

    Returns:
        Path to the tarball

    Raises:
        RuntimeError: if npm pack did not produce a tarball

    """
    out_dir.mkdir(parents=True, exist_ok=True)
    # npm pack produces a tgz named like vercel-<version>.tgz
    completed = npm(
        ["pack", f"vercel@{version}"],
        cwd=str(out_dir),
        return_completed_process=True,
        capture_output=True,
    )
    if completed.returncode != 0:
        stderr = _decode_maybe_bytes(getattr(completed, "stderr", b""))
        msg = f"npm pack failed for vercel@{version}: {stderr.strip()}"
        raise RuntimeError(msg)
    # npm returns filename on stdout; prefer it if present
    filename = _decode_maybe_bytes(completed.stdout).strip()
    if filename:
        candidate = out_dir / filename
        if candidate.exists():
            return candidate
    tgzs = list(out_dir.glob("vercel-*.tgz"))
    if not tgzs:
        msg = f"npm pack did not produce a tarball for vercel@{version}"
        raise RuntimeError(msg)
    return tgzs[0]


def safe_target_path(member_name: str, dest: Path) -> Path | None:
    """Return a safe target path within dest for a tar member.

    Returns:
        A `Path` within `dest` for safe members, or ``None`` to skip the entry.

    """
    if not member_name.startswith("package/"):
        return None
    rel = member_name[len("package/") :]
    if not rel or rel == ".":
        return None
    rel_path = Path(rel)
    if rel_path.is_absolute():
        return None
    for part in rel_path.parts:
        # Disallow traversal attempts, including disguised with whitespace
        if part.strip() != part:
            return None
        if part.strip() in {".", ".."}:
            return None
    return dest / rel_path


def _extract_member(tf: tarfile.TarFile, member: tarfile.TarInfo, target: Path) -> None:
    if member.isdir():
        target.mkdir(parents=True, exist_ok=True)
        return
    if member.isreg():
        target.parent.mkdir(parents=True, exist_ok=True)
        extracted = tf.extractfile(member)
        if extracted is None:
            return
        with target.open("wb") as f:
            shutil.copyfileobj(extracted, f)
        with suppress(PermissionError):
            target.chmod(member.mode)
        return


def extract_tgz(tgz_path: Path, dest: Path) -> None:
    """Safely extract a tarball into a directory, stripping the package/ prefix."""
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tgz_path) as tf:
        for member in tf.getmembers():
            # Skip links entirely
            if member.issym() or member.islnk():
                continue
            target = safe_target_path(member.name, dest)
            if target is None:
                continue
            _extract_member(tf, member, target)


def npm_view(version: str) -> dict[str, Any]:
    """Return npm view JSON for vercel@version.

    Returns:
        A dict with optional key `dist` containing `integrity` and `shasum`.

    """
    cp = npm(
        ["view", f"vercel@{version}", "--json"],
        return_completed_process=True,
        capture_output=True,
    )
    return json.loads(cp.stdout)


def verify_tgz(tgz_path: Path, integrity: str | None, shasum: str | None) -> None:
    """Verify tarball against npm integrity or shasum if available.

    Raises:
        RuntimeError: if verification fails when metadata is provided.

    """
    if integrity:
        try:
            algo, b64digest = integrity.split("-", 1)
            algo = algo.lower()
            expected = base64.b64decode(b64digest)
        except Exception as exc:
            msg = f"Invalid integrity: {integrity}"
            raise RuntimeError(msg) from exc
        try:
            hasher = getattr(hashlib, algo)()
        except AttributeError as exc:
            msg = f"Unsupported integrity algorithm: {algo}"
            raise RuntimeError(msg) from exc
        with tgz_path.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                hasher.update(chunk)
        if hasher.digest() != expected:
            msg = "Integrity verification failed for npm tarball"
            raise RuntimeError(msg)
        return
    if shasum:
        hasher = hashlib.sha1()  # noqa: S324 - npm publishes SHA1 shasum
        with tgz_path.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                hasher.update(chunk)
        if hasher.hexdigest() != shasum:
            msg = "SHA1 verification failed for npm tarball"
            raise RuntimeError(msg)
        return


def update_vendor(version: str) -> None:
    """Update the vendored npm package.

    Args:
        version: npm version to vendor

    """
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        # Fetch metadata first (integrity/shasum), then pack and verify
        metadata = npm_view(version)

        tgz = npm_pack(version=version, out_dir=tmp)

        verify_tgz(
            tgz,
            integrity=metadata["dist"]["integrity"],
            shasum=metadata["dist"]["shasum"],
        )
        logger.info("Verified npm tarball integrity")

        # Extract to a temp working directory and install prod deps
        work_dir = tmp / "work"
        extract_tgz(tgz, work_dir)

        # Remove devDependencies to avoid fetching private monorepo-only packages
        # that are not published to the public npm registry (e.g. @vercel-internals/*).
        # We already install with --omit=dev, but some npm versions can still
        # traverse dev deps during tree building. Stripping them guarantees
        # production-only resolution.
        pkg_json_path = work_dir / "package.json"
        try:
            pkg_data = json.loads(pkg_json_path.read_text())
            if pkg_data.pop("devDependencies", None) is not None:
                logger.info("Stripped devDependencies from vendored package.json")
            # Also drop optional workspace-only fields that are irrelevant for vendoring
            for key in ("packageManager", "pnpm", "workspaces"):
                if pkg_data.pop(key, None) is not None:
                    logger.info("Removed %s from vendored package.json", key)
            pkg_json_path.write_text(
                json.dumps(pkg_data, indent=2, sort_keys=True) + "\n"
            )
        except Exception as exc:  # noqa: BLE001 - emit context then re-raise
            logger.info("Warning: failed to sanitize package.json: %s", exc)

        # Use install instead of ci, as npm pack tarball lacks a lockfile
        # Force production-only install and avoid creating a lockfile
        npm(
            ["install", "--omit=dev", "--no-package-lock", "--ignore-scripts"],
            cwd=str(work_dir),
            env={"NODE_ENV": "production"},
            capture_output=True,
        )

        # Clean and repopulate vendor dir
        if VENDOR_DIR.exists():
            for child in VENDOR_DIR.iterdir():
                if child.name == ".gitkeep":
                    continue
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink()
        VENDOR_DIR.mkdir(parents=True, exist_ok=True)

        shutil.copytree(work_dir, VENDOR_DIR, dirs_exist_ok=True)


def main() -> None:
    """Run the CLI entry point."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "version",
        default="latest",
        help="npm version to vendor, e.g. 46.0.2 or latest",
        nargs="?",
    )
    args = ap.parse_args()

    update_vendor(version=args.version)

    # Verify the vendored package.json has a version
    data = json.loads((VENDOR_DIR / "package.json").read_text())
    resolved = str(data["version"])  # must exist in npm package
    logger.info("Vendored vercel@%s", resolved)


if __name__ == "__main__":
    main()
