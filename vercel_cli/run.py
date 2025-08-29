"""Console entrypoint for the Python-wrapped Vercel CLI.

Executes the vendored JavaScript CLI (``vercel_cli/vendor/dist/vc.js``) using
the Node.js runtime provided by ``nodejs-wheel-binaries``.
"""

from __future__ import annotations

import sys
from pathlib import Path

from nodejs_wheel.executable import node


def main() -> int:
    """Run the vendored Vercel CLI and return its exit code.

    Returns:
        The exit code of the vendored CLI.

    """
    here = Path(__file__).resolve().parent
    js_cli = here / "vendor" / "dist" / "vc.js"
    if not js_cli.exists():
        sys.stderr.write(
            f"Missing vendored CLI at {js_cli}. "
            "Run python scripts/update_vendor.py to vendor it.\n"
        )
        return 1
    # Pass through current environment and command-line arguments
    try:
        return node([str(js_cli), *sys.argv[1:]])  # type: ignore[no-any-return]
    except SystemExit as exc:
        # In case node() raises SystemExit with the code
        return int(exc.code) if exc.code is not None else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
