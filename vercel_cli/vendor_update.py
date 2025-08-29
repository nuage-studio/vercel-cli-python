"""Vendor update helpers and CLI logic.

This module contains the reusable logic to vendor the npm ``vercel`` package
into ``vercel_cli/vendor`` and related utilities. It is imported by both the
CLI entry points and tests.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
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


# Keep the vendored CLI as small as possible: we only need the Python builder
# and a minimal runtime surface for the CLI itself. These dependency names will
# be retained from the upstream package.json; all others are dropped.
ALLOWED_RUNTIME_DEPENDENCIES: set[str] = {
    "@vercel/build-utils",
    "@vercel/detect-agent",
    "@vercel/python",
}


def sanitize_package_data(pkg_data: dict[str, Any]) -> dict[str, Any]:
    """Return sanitized package.json data enforcing our minimal runtime deps.

    - Remove devDependencies
    - Remove monorepo fields (packageManager, pnpm, workspaces)
    - Keep only ALLOWED_RUNTIME_DEPENDENCIES in dependencies
    - Keep keys sorted deterministically when written by caller

    Returns:
        dict: The sanitized package.json data.

    """
    data = dict(pkg_data)
    data.pop("devDependencies", None)
    for key in ("packageManager", "pnpm", "workspaces"):
        data.pop(key, None)
    original_deps: dict[str, str] = dict(data.get("dependencies", {}))
    filtered_deps = {
        name: version
        for name, version in original_deps.items()
        if name in ALLOWED_RUNTIME_DEPENDENCIES
    }
    data["dependencies"] = {k: filtered_deps[k] for k in sorted(filtered_deps.keys())}
    return data


def decode_maybe_bytes(value: bytes | str | None) -> str:
    """Decode a bytes or str value to a string.

    Returns:
        str: The decoded string.

    """
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return str(value)


def npm_pack(version: str, out_dir: Path) -> Path:
    """Pack a npm package into a tarball and return its path.

    Raises:
        RuntimeError: If the npm pack fails.

    Returns:
        Path: The path to the packed tarball.

    """
    out_dir.mkdir(parents=True, exist_ok=True)
    completed = npm(
        args=["pack", f"vercel@{version}"],
        return_completed_process=True,
        cwd=str(out_dir),
        capture_output=True,
    )
    if completed.returncode != 0:
        stderr = decode_maybe_bytes(getattr(completed, "stderr", b""))
        msg = f"npm pack failed for vercel@{version}: {stderr.strip()}"
        raise RuntimeError(msg)
    filename = decode_maybe_bytes(getattr(completed, "stdout", b""))
    filename = filename.strip()
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
    """Return a safe target path within dest for a tar member, or None to skip.

    Returns:
        Path: The safe target path.

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
            if member.issym() or member.islnk():  # skip links entirely
                continue
            target = safe_target_path(member.name, dest)
            if target is None:
                continue
            _extract_member(tf, member, target)


def npm_view(version: str) -> dict[str, Any]:
    """Return npm view JSON for vercel@version.

    Returns:
        dict: The npm view JSON.

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
        RuntimeError: If the tarball is invalid.

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
            msg = f"Integrity verification failed for npm tarball: {integrity}"
            raise RuntimeError(msg)
        return
    if shasum:
        hasher = hashlib.sha1()  # noqa: S324 - npm publishes SHA1 shasum
        with tgz_path.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                hasher.update(chunk)
        if hasher.hexdigest() != shasum:
            msg = f"SHA1 verification failed for npm tarball: {shasum}"
            raise RuntimeError(msg)
        return


def read_vendored_version() -> str:
    """Return the version of the vendored npm package.

    Returns:
        str: The version of the vendored npm package.

    """
    pkg_json = VENDOR_DIR / "package.json"
    data = json.loads(pkg_json.read_text())
    return str(data["version"])


def resolve_latest_version() -> str:
    """Return the latest version of the npm package.

    Returns:
        str: The latest version of the npm package.

    """
    meta = npm_view("latest")
    return str(meta.get("version", ""))


def update_vendor(version: str) -> None:
    """Update the vendored npm package to the given version."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        metadata = npm_view(version)
        tgz = npm_pack(version=version, out_dir=tmp)
        verify_tgz(
            tgz,
            integrity=metadata["dist"]["integrity"],
            shasum=metadata["dist"]["shasum"],
        )
        logger.info("Verified npm tarball integrity")

        work_dir = tmp / "work"
        extract_tgz(tgz, work_dir)

        pkg_json_path = work_dir / "package.json"
        try:
            pkg_data: dict[str, Any] = json.loads(pkg_json_path.read_text())
            pkg_data = sanitize_package_data(pkg_data)
            pkg_json_path.write_text(
                json.dumps(pkg_data, indent=2, sort_keys=True) + "\n"
            )
            logger.info(
                "Restricted dependencies to: %s",
                ", ".join(sorted(pkg_data["dependencies"].keys())),
            )
        except Exception as exc:  # noqa: BLE001 - emit context then re-raise
            logger.info("Warning: failed to sanitize package.json: %s", exc)

        npm(
            args=["install", "--omit=dev", "--no-package-lock", "--ignore-scripts"],
            return_completed_process=False,
            cwd=str(work_dir),
            env={"NODE_ENV": "production"},
            capture_output=True,
        )

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


def write_github_outputs(**kwargs: str) -> None:
    """Append key=value pairs to the file given by GITHUB_OUTPUT if set."""
    out_path = os.environ.get("GITHUB_OUTPUT")
    if not out_path:
        return
    lines = [f"{k}={v}" for k, v in kwargs.items()]
    with Path(out_path).open("a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
