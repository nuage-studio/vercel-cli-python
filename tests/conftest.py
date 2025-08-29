from __future__ import annotations

import io
import json
import tarfile
from typing import TYPE_CHECKING, Callable

import pytest

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def mk_pkg_tgz() -> Callable[[Path, str, dict[str, bytes] | None], Path]:
    def _make(
        tmp_path: Path, version: str, extra_files: dict[str, bytes] | None = None
    ) -> Path:
        """Create a small npm-like tgz with package/ prefix and a package.json.

        Returns:
            Path: The path to the created tgz.

        """
        tar_path = tmp_path / "vercel-pack.tgz"
        payload = {
            "name": "vercel",
            "version": version,
            "dependencies": {
                "@vercel/python": "5.0.0",
                "@vercel/build-utils": "11.0.2",
                "leftpad": "1.3.0",
            },
            "devDependencies": {"typescript": "5.2.2"},
            "packageManager": "pnpm@9",
        }
        pkg_json = json.dumps(payload).encode()
        with tarfile.open(tar_path, "w:gz") as tf:
            info = tarfile.TarInfo(name="package/package.json")
            info.size = len(pkg_json)
            tf.addfile(info, io.BytesIO(pkg_json))
            body = b"console.log('ok')\n"
            info = tarfile.TarInfo(name="package/index.js")
            info.size = len(body)
            tf.addfile(info, io.BytesIO(body))
            for name, content in (extra_files or {}).items():
                ti = tarfile.TarInfo(name=f"package/{name}")
                ti.size = len(content)
                tf.addfile(ti, io.BytesIO(content))
        return tar_path

    return _make
