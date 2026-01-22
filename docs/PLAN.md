# Plan: Convert laserbeak (Node) to Python

## Goals
- Port the CLI and library from `../laserbeak` (Node/TypeScript) into a Python project in this repo.
- Preserve user-visible CLI behavior, config precedence, and JSON output contracts.
- Support both standalone CLI usage and importing as a Python module from other projects.
- Follow modern Python project conventions (pyproject, src layout, typed code, linting/testing).

## Non-goals
- No feature additions or behavior changes unless required for parity.
- No implementation in this step; this file is the plan only.

## Discovery
1. Read `../laserbeak/README.md`, `package.json`, and `src/**` to understand CLI commands, options, and outputs.
2. Inventory runtime dependencies and how they map to Python equivalents (HTTP client, config parsing, color/emoji output, cookie extraction).
3. Review tests in `../laserbeak/tests/**` to capture expected behavior and fixtures.

## Project layout (Python)
1. Create `pyproject.toml` with metadata, console script entry point, library exports, dependencies, and tooling config.
2. Use `src/` layout, e.g. `src/laserbeak/` for library and `src/laserbeak/cli.py` for CLI.
3. Add `tests/` with `pytest`, mirroring behavior in `../laserbeak/tests/**`.

## Core migration steps
1. Map CLI commands and global options to a Python CLI framework (e.g., Typer/Click), matching command names and flags.
2. Port the GraphQL client and auth resolution logic (cookie precedence, env vars, config files).
3. Port config parsing for JSON5 (`.laserbeakrc.json5` and `~/.config/laserbeak/config.json5`).
4. Implement JSON/text output formatting and plain/no-color/no-emoji modes.
5. Port rate limiting, pagination, and query ID cache logic.

## Tooling and quality
1. Use `uv` for Python version management, virtualenv creation, and dependency installation.
2. Add formatting/linting (`ruff`, `black` or `ruff format`) and type checking (`mypy` or `pyright`).
2. Add test tooling (`pytest`, `pytest-cov`) and basic CI-friendly commands.
3. Document dev workflow and release notes in `README.md` / `CHANGELOG.md`.

## Packaging and distribution
1. Define console script `laserbeak` entry point in `pyproject.toml`.
2. Ensure package data (query id cache, templates) is included.
3. Provide install instructions equivalent to Node version.

## Validation
1. Run unit tests and key CLI commands in dry-run mode.
2. Compare JSON outputs with Node version for parity.
3. Verify config precedence and auth resolution.

## Deliverables
- Python source under `src/`.
- Tests under `tests/`.
- `pyproject.toml` and tooling configs.
- Updated `README.md` for Python usage.
