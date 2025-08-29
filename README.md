vercel-cli: Python package wrapper for Vercel CLI
=================================================

**vercel-cli** packages the npm `vercel` CLI for Python environments. It vendors the npm package under `vercel_cli/vendor/` and uses the bundled Node.js runtime provided by `nodejs-wheel-binaries`, so you can run `vercel` without installing Node.js.

Quick start
-----------

- **Install**:

```bash
pip install vercel-cli
```

- **Use** (same arguments and behavior as the official npm CLI):

```bash
vercel --version
vercel login
vercel deploy
```

What this provides
------------------

- **No system Node.js required**: The CLI runs via the Node binary from `nodejs-wheel-binaries` (currently Node 22.x).
- **Vendored npm package**: The `vercel` npm package (production deps only) is checked into `vercel_cli/vendor/`.
- **Console entrypoint**: The `vercel` command maps to `vercel_cli.run:main`, which executes `vercel_cli/vendor/dist/vc.js` with the bundled Node runtime.

Requirements
------------

- Python 3.8+
- macOS, Linux, or Windows supported by the Node wheels

How it works
------------

At runtime, `vercel_cli.run` locates `vercel_cli/vendor/dist/vc.js` and launches it via the Node executable exposed by `nodejs_wheel_binaries`. All CLI arguments and environment variables are passed through unchanged.

Updating the vendored Vercel CLI (maintainers)
----------------------------------------------

There are two ways to update the vendored npm package under `vercel_cli/vendor/`:

1) Manual update to a specific version

```bash
# Using the console script defined in pyproject.toml
uv run update-vendor 46.0.2
# or equivalently
uv run python scripts/update_vendor.py 46.0.2
```

This will:

- fetch `vercel@46.0.2` from npm,
- verify integrity/shasum,
- install production dependencies with `npm install --omit=dev`, and
- copy the result into `vercel_cli/vendor/`.

2) Automatic check-and-release (GitHub Actions)

The workflow `.github/workflows/release.yml` checks npm `latest` and, if newer than the vendored version, will:

- vendor the new version using `scripts/check_and_update.py`,
- commit the changes and create a tag `v<version>`,
- build distributions, and
- publish to PyPI (requires `PYPI_API_TOKEN`).

Versioning
----------

The Python package version is derived dynamically from the vendored `package.json` via Hatch’s version source:

```toml
[tool.hatch.version]
path = "vercel_cli/vendor/package.json"
pattern = '"version"\s*:\s*"(?P<version>[^\\"]+)"'
```

Development
-----------

- Build backend: `hatchling`
- Dependency management: `uv` (see `uv.lock`)
- Tests: `pytest` with coverage in `tests/`
- Lint/format: `ruff`; type-check: `basedpyright`

Common commands (using `uv`):

```bash
# Run tests with coverage
uv run pytest --cov=vercel_cli --cov-report=term-missing

# Lint and format
uv run ruff check .
uv run ruff format .

# Type-check
uv run basedpyright

# Build wheel and sdist
uv run --with build python -m build
```

Notes
-----

- If `vercel_cli/vendor/dist/vc.js` is missing, the entrypoint will exit with an error prompting you to run the vendoring script.
- The vendored Vercel CLI includes its own license; see `vercel_cli/vendor/LICENSE`.
