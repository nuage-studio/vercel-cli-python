"""Console entrypoint for the Python-wrapped Vercel CLI.

Executes the vendored JavaScript CLI (``vercel_cli/vendor/dist/vc.js``) using
the Node.js runtime provided by ``nodejs-wheel-binaries``.

Can be used both as a command-line tool and programmatically by other Python libraries.
"""

from __future__ import annotations

import sys
from pathlib import Path

from nodejs_wheel.executable import node


def run_vercel(
    args: list[str] | None = None,
    cwd: str | Path | None = None,
    env: dict[str, str] | None = None,
) -> int:
    """Run the vendored Vercel CLI with the given arguments.

    This function can be called programmatically by other Python libraries
    instead of using subprocess calls.

    Args:
        args: List of command-line arguments for the Vercel CLI.
              If None, uses sys.argv[1:] (for CLI usage).
        cwd: Working directory for the command. If None, uses current directory.
        env: Environment variables for the command. If None, uses os.environ.

    Returns:
        The exit code of the vendored CLI.

    Example:
        ```python
        from vercel_cli.run import run_vercel

        # Deploy current directory
        exit_code = run_vercel(["deploy"])

        # Deploy specific directory with custom env
        exit_code = run_vercel(
            ["deploy", "--prod"],
            cwd="/path/to/project",
            env={"VERCEL_TOKEN": "my-token"}
        )
        ```

    """
    here = Path(__file__).resolve().parent
    js_cli = here / "vendor" / "dist" / "vc.js"

    # Determine arguments
    command_args = sys.argv[1:] if args is None else args

    # Prepare the full command
    full_args = [str(js_cli), *command_args]

    # Prepare working directory
    working_dir = cwd or Path.cwd()

    try:
        return node(args=full_args, cwd=working_dir, env=env)
    except SystemExit as exc:
        # In case node() raises SystemExit with the code
        return int(exc.code) if exc.code is not None else 1


def main() -> int:
    """Run the vendored Vercel CLI using command-line arguments.

    This is the entry point for the CLI tool. It uses sys.argv for arguments.

    Returns:
        The exit code of the vendored CLI.

    """
    return run_vercel()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
