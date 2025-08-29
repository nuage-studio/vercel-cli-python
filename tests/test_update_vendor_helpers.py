from __future__ import annotations

import hashlib
import io
import tarfile
from typing import TYPE_CHECKING

import pytest

from scripts.update_vendor import (
    ALLOWED_RUNTIME_DEPENDENCIES,
    extract_tgz,
    safe_target_path,
    sanitize_package_data,
    verify_tgz,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_safe_target_path_basics(tmp_path: Path) -> None:
    dest = tmp_path
    # Valid file under package/
    assert safe_target_path("package/index.js", dest) == dest / "index.js"
    # Skip root, outside, traversal, or non-package
    assert safe_target_path("index.js", dest) is None
    assert (
        safe_target_path("package/.. /x", dest) is None
    )  # space prevents false positive
    assert safe_target_path("package/..", dest) is None
    assert safe_target_path("package/", dest) is None


def _make_tgz_with_file(tmp_path: Path, members: dict[str, bytes]) -> Path:
    tar_path = tmp_path / "pkg.tgz"
    with tarfile.open(tar_path, "w:gz") as tf:
        for name, content in members.items():
            data = content
            ti = tarfile.TarInfo(name=name)
            ti.size = len(data)
            tf.addfile(ti, io.BytesIO(data))
    return tar_path


def test_extract_tgz_skips_links(tmp_path: Path) -> None:
    tar_path = tmp_path / "l.tgz"
    with tarfile.open(tar_path, "w:gz") as tf:
        # add a safe file
        data = b"console.log('ok')\n"
        ti = tarfile.TarInfo(name="package/index.js")
        ti.size = len(data)
        tf.addfile(ti, io.BytesIO(data))
        # add a symlink that should be skipped
        link = tarfile.TarInfo(name="package/link")
        link.type = tarfile.SYMTYPE
        link.linkname = "../outside"
        tf.addfile(link)

    out = tmp_path / "out"
    extract_tgz(tar_path, out)
    assert (out / "index.js").exists()
    assert not (out / "link").exists()


def test_verify_tgz_with_shasum(tmp_path: Path) -> None:
    # Create a tarball and compute sha1
    content = {"package/file.txt": b"hello"}
    tar_path = _make_tgz_with_file(tmp_path, content)

    h = hashlib.sha1()
    with tar_path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    verify_tgz(tar_path, integrity=None, shasum=h.hexdigest())

    with pytest.raises(RuntimeError):
        verify_tgz(tar_path, integrity=None, shasum="deadbeef")


def test_sanitize_package_data_filters_dependencies() -> None:
    pkg = {
        "name": "vercel",
        "version": "0.0.0",
        "dependencies": {
            "@vercel/python": "5.0.0",
            "@vercel/node": "5.3.17",
            "@vercel/build-utils": "11.0.2",
            "@vercel/detect-agent": "0.2.0",
            "chokidar": "4.0.0",
            "jose": "5.9.6",
        },
        "devDependencies": {"typescript": "4.9.5"},
        "packageManager": "pnpm@9",
        "pnpm": {},
        "workspaces": ["packages/*"],
    }
    out = sanitize_package_data(pkg)
    assert "devDependencies" not in out
    for k in ("packageManager", "pnpm", "workspaces"):
        assert k not in out
    # Only allowed dependencies remain
    assert set(out["dependencies"].keys()) == set(ALLOWED_RUNTIME_DEPENDENCIES)
