from __future__ import annotations

import base64
import hashlib
import io
import json
import tarfile
from types import SimpleNamespace
from typing import TYPE_CHECKING, Callable
from unittest.mock import MagicMock

import pytest

from vercel_cli import vendor_update
from vercel_cli.vendor_update import (
    ALLOWED_RUNTIME_DEPENDENCIES,
    extract_tgz,
    safe_target_path,
    sanitize_package_data,
    verify_tgz,
)

if TYPE_CHECKING:
    from pathlib import Path


def _make_tgz_with_file(tmp_path: Path, members: dict[str, bytes]) -> Path:
    tar_path = tmp_path / "pkg.tgz"
    with tarfile.open(tar_path, "w:gz") as tf:
        for name, content in members.items():
            data = content
            ti = tarfile.TarInfo(name=name)
            ti.size = len(data)
            tf.addfile(ti, io.BytesIO(data))
    return tar_path


def test_npm_pack_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class FakeCompleted:
        returncode = 1
        stderr = b"boom"

    def fake_npm(*_args: object, **_kwargs: object) -> FakeCompleted:
        return FakeCompleted()

    monkeypatch.setattr(vendor_update, "npm", fake_npm)

    with pytest.raises(RuntimeError) as ei:
        vendor_update.npm_pack("1.2.3", tmp_path)
    assert "npm pack failed" in str(ei.value)


def test_npm_pack_fallback_to_glob(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    fallback = out_dir / "vercel-1.2.3.tgz"
    fallback.write_bytes(b"tgz")

    class FakeCompleted:
        returncode = 0
        stdout = b""  # empty => triggers glob fallback

    monkeypatch.setattr(vendor_update, "npm", MagicMock(return_value=FakeCompleted()))
    p = vendor_update.npm_pack("1.2.3", out_dir)
    assert p == fallback


def test_npm_pack_uses_stdout_filename(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    out_dir = tmp_path / "o"
    out_dir.mkdir()
    fname = out_dir / "vercel-2.2.2.tgz"
    fname.write_bytes(b"x")

    class FakeCompleted:
        returncode = 0
        stdout = b"vercel-2.2.2.tgz\n"

    monkeypatch.setattr(vendor_update, "npm", MagicMock(return_value=FakeCompleted()))
    got = vendor_update.npm_pack("2.2.2", out_dir)
    assert got == fname


def test_verify_tgz_integrity_success_and_failure(tmp_path: Path) -> None:
    tar_path = _make_tgz_with_file(tmp_path, {"package/file.txt": b"hello"})

    h = hashlib.sha512()
    with tar_path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    integrity = "sha512-" + base64.b64encode(h.digest()).decode()

    verify_tgz(tar_path, integrity=integrity, shasum=None)

    with pytest.raises(RuntimeError):
        verify_tgz(tar_path, integrity="sha512-AAAA", shasum=None)


def test_verify_tgz_with_shasum(tmp_path: Path) -> None:
    content = {"package/file.txt": b"hello"}
    tar_path = _make_tgz_with_file(tmp_path, content)

    h = hashlib.sha1()
    with tar_path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    verify_tgz(tar_path, integrity=None, shasum=h.hexdigest())

    with pytest.raises(RuntimeError):
        verify_tgz(tar_path, integrity=None, shasum="deadbeef")


def test_verify_tgz_unsupported_algo(
    tmp_path: Path, mk_pkg_tgz: Callable[[Path, str], Path]
) -> None:
    tar_path = mk_pkg_tgz(tmp_path, "1.0.0")
    with pytest.raises(RuntimeError):
        vendor_update.verify_tgz(tar_path, integrity="foo-AAAA", shasum=None)


def test_verify_tgz_invalid_integrity_format(
    tmp_path: Path, mk_pkg_tgz: Callable[[Path, str], Path]
) -> None:
    tar_path = mk_pkg_tgz(tmp_path, "1.0.0")
    with pytest.raises(RuntimeError):
        vendor_update.verify_tgz(tar_path, integrity="sha512", shasum=None)


def test_verify_tgz_shasum_mismatch(
    tmp_path: Path, mk_pkg_tgz: Callable[[Path, str], Path]
) -> None:
    tar_path = mk_pkg_tgz(tmp_path, "1.0.0")
    with pytest.raises(RuntimeError):
        vendor_update.verify_tgz(tar_path, integrity=None, shasum="deadbeef")


def test_decode_maybe_bytes_varixants() -> None:
    assert not vendor_update.decode_maybe_bytes(None)
    assert vendor_update.decode_maybe_bytes(b"abc") == "abc"
    assert vendor_update.decode_maybe_bytes("xyz") == "xyz"


def test_safe_target_path_basics(tmp_path: Path) -> None:
    dest = tmp_path
    assert safe_target_path("package/index.js", dest) == dest / "index.js"
    assert safe_target_path("index.js", dest) is None
    assert safe_target_path("package/.. /x", dest) is None
    assert safe_target_path("package/..", dest) is None
    assert safe_target_path("package/", dest) is None


def test_extract_tgz_skips_links(tmp_path: Path) -> None:
    tar_path = tmp_path / "l.tgz"
    with tarfile.open(tar_path, "w:gz") as tf:
        data = b"console.log('ok')\n"
        ti = tarfile.TarInfo(name="package/index.js")
        ti.size = len(data)
        tf.addfile(ti, io.BytesIO(data))
        link = tarfile.TarInfo(name="package/link")
        link.type = tarfile.SYMTYPE
        link.linkname = "../outside"
        tf.addfile(link)

    out = tmp_path / "out"
    extract_tgz(tar_path, out)
    assert (out / "index.js").exists()
    assert not (out / "link").exists()


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
    assert set(out["dependencies"].keys()) == set(ALLOWED_RUNTIME_DEPENDENCIES)


def test_update_vendor_happy_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    mk_pkg_tgz: Callable[[Path, str], Path],
) -> None:
    tgz = mk_pkg_tgz(tmp_path, "9.9.9")

    h = hashlib.sha512()
    with tgz.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    integrity = "sha512-" + base64.b64encode(h.digest()).decode()
    sh = hashlib.sha1()
    with tgz.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sh.update(chunk)
    shasum = sh.hexdigest()

    monkeypatch.setattr(
        vendor_update,
        "npm_view",
        MagicMock(return_value={"dist": {"integrity": integrity, "shasum": shasum}}),
    )
    monkeypatch.setattr(vendor_update, "npm_pack", MagicMock(return_value=tgz))
    monkeypatch.setattr(
        vendor_update, "npm", MagicMock(return_value=SimpleNamespace(returncode=0))
    )
    monkeypatch.setattr(vendor_update, "VENDOR_DIR", tmp_path / "vendor")

    vendor_update.update_vendor("9.9.9")

    pkg = json.loads((vendor_update.VENDOR_DIR / "package.json").read_text())
    assert pkg["version"] == "9.9.9"
    assert "devDependencies" not in pkg
    assert set(pkg["dependencies"]) <= vendor_update.ALLOWED_RUNTIME_DEPENDENCIES


def test_update_vendor_handles_invalid_json_and_cleans(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    tar_path = tmp_path / "bad.tgz"
    with tarfile.open(tar_path, "w:gz") as tf:
        bad = b"{invalid json}"
        info = tarfile.TarInfo(name="package/package.json")
        info.size = len(bad)
        tf.addfile(info, io.BytesIO(bad))
        body = b"console.log('ok')\n"
        info = tarfile.TarInfo(name="package/index.js")
        info.size = len(body)
        tf.addfile(info, io.BytesIO(body))

    h = hashlib.sha512()
    with tar_path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    integrity = "sha512-" + base64.b64encode(h.digest()).decode()
    sh = hashlib.sha1()
    with tar_path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sh.update(chunk)
    shasum = sh.hexdigest()

    monkeypatch.setattr(
        vendor_update,
        "npm_view",
        MagicMock(return_value={"dist": {"integrity": integrity, "shasum": shasum}}),
    )
    monkeypatch.setattr(vendor_update, "npm_pack", MagicMock(return_value=tar_path))
    monkeypatch.setattr(
        vendor_update, "npm", MagicMock(return_value=SimpleNamespace(returncode=0))
    )

    vdir = tmp_path / "vendor"
    (vdir / "old_dir").mkdir(parents=True)
    (vdir / "old_file.txt").write_text("x")
    monkeypatch.setattr(vendor_update, "VENDOR_DIR", vdir)

    vendor_update.update_vendor("0.0.1")

    assert not (vdir / "old_dir").exists()
    assert not (vdir / "old_file.txt").exists()
    assert (vdir / "index.js").exists()
