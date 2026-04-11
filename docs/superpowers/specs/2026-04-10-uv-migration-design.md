# Migration: Poetry → uv

**Date:** 2026-04-10
**Branch:** `v2_component`
**Status:** Design approved, awaiting implementation plan

## Goal

Replace Poetry with uv as the Python dependency manager and build driver for `streamlit-aggrid`. Use `hatchling` as the PEP 517 build backend. Preserve current wheel contents (Python package + compiled frontend assets + JSON schemas).

## Context

The repository is a fork of PablocFonseca/streamlit-aggrid on branch `v2_component`. It is a Streamlit Custom Components v2 package: a Python wrapper (`st_aggrid/`) plus a TypeScript/React frontend (`st_aggrid/frontend/`) built via Vite. The built frontend assets (`st_aggrid/frontend/build/`) must be shipped inside the Python wheel.

Current state:
- `pyproject.toml` uses `poetry-core` build backend with `[tool.poetry]` packages/include and `[tool.poetry.group.dev.dependencies]`.
- A `uv.lock` already exists (246KB, 41 packages) — generated while `pyproject.toml` still carried Poetry config. `.venv` is uv-managed (uv 0.9.26, Python 3.13.7).
- `poetry.lock` is still committed (149KB).
- No CI workflows (`.github/` has only `ISSUE_TEMPLATE`).
- Root `package.json` has `"build": "yarn workspaces foreach -Avi run build && poetry build"`.
- `CLAUDE.md` documents Poetry in two spots (lines 69 and 80).
- `README.md` does not reference Poetry.

## Non-Goals

- No change to the frontend build toolchain (Vite, yarn 4.1.0 workspaces).
- No change to the Python package layout (`st_aggrid/` stays).
- No change to runtime dependencies or Python version floor (`>=3.10`).
- No README revisions (Poetry is not mentioned there).
- No CI changes (none exist).

## Decisions

| # | Decision | Rationale |
|---|---|---|
| 1 | Build backend: **hatchling** | Mature, well-documented, flexible inclusion rules for non-Python files (`frontend/build/`, `json/`). Default choice for uv-managed libraries. |
| 2 | Dev deps: **`[dependency-groups]` (PEP 735)** | Direct equivalent of `[tool.poetry.group.dev.dependencies]`. Stays out of the published wheel. uv reads it natively. |
| 3 | Release build: **`uv build`** | Since we are already on uv, use its bundled PEP 517 frontend. No extra dev dependency on the `build` package. |
| 4 | `poetry.lock`: **delete**, commit new `uv.lock` | Single source of truth. No parallel consumers of Poetry remain. |
| 5 | Lock file: **regenerate** via `uv lock` | Current `uv.lock` was built against Poetry-shaped `pyproject.toml`. Regenerate to match new build backend + dependency-groups layout. |

## Target `pyproject.toml`

```toml
[project]
name = "streamlit-aggrid"
version = "2.0.0"
description = "Streamlit component implementation of ag-grid (CCv2, no iframe)"
readme = "README.md"
requires-python = ">=3.10"
license = { text = "MIT" }
authors = [{ name = "Pablo Fonseca", email = "pablo.fonseca+pip@gmail.com" }]
keywords = ["streamlit", "ag-grid", "component"]
classifiers = [
    "Programming Language :: Python :: 3",
    "License :: OSI Approved :: MIT License",
    "Operating System :: OS Independent",
]
dependencies = ["streamlit >=1.44.0", "pandas >=1.4.0"]

[project.urls]
homepage = "https://github.com/PablocFonseca/streamlit-aggrid"

[dependency-groups]
dev = [
    "bs4 >=0.0.2",
    "playwright >=1.51.0",
    "pytest >=8.3.5",
    "pytest-playwright >=0.7.0",
    "watchdog >=6.0.0",
    "ruff",
    "streamlit-code-editor >=0.1.12",
    "pytest-cov >=6.2.1",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["st_aggrid"]
artifacts = ["st_aggrid/frontend/build/**"]

[tool.hatch.build.targets.sdist]
include = [
    "/st_aggrid",
    "/README.md",
    "/LICENSE",
    "/pyproject.toml",
]
artifacts = ["st_aggrid/frontend/build/**"]
```

**Rationale for non-obvious bits:**

- `artifacts = ["st_aggrid/frontend/build/**"]` — hatchling by default respects `.gitignore`, which excludes `build/` at the project root. The `.gitignore` negation `!st_aggrid/frontend/build/` exists to re-allow the frontend artifacts in git, but hatchling's `artifacts` directive is the documented way to ensure compiled assets that are produced as part of the build (and that might otherwise be gitignored) make it into both wheel and sdist. Declared on both targets explicitly.
- `st_aggrid/json/*.json` — hatchling includes non-Python files inside a discovered package by default, so no explicit rule needed (sits inside `st_aggrid/`, picked up via `packages`).
- `sdist.include` uses leading `/` to anchor to project root (hatchling-specific glob syntax).
- Caret specifiers (`^0.0.2`) are Poetry-specific; PEP 440 uses `>=` with no upper bound. The intent of `^X.Y.Z` in Poetry was "compatible within the same major", but in practice for this project a lower bound is sufficient — the lock file pins exact versions anyway.

## Target `package.json` build script

Replace line 13:

```diff
- "build": "yarn workspaces foreach -Avi run build && poetry build",
+ "build": "yarn workspaces foreach -Avi run build && uv build",
```

`uv build` produces `dist/*.whl` and `dist/*.tar.gz`. `dist/` is already gitignored.

## `CLAUDE.md` updates

**Line 69** (Build & Dev section, comment on `yarn build`):

```diff
- yarn build          # root package.json — builds all workspaces then poetry build
+ yarn build          # root package.json — builds all workspaces then uv build
```

**Line 80** (Key Design Decisions):

```diff
- Python build: **Poetry** (`poetry-core`).
+ Python build: **hatchling** (via `uv build`).
```

**Replace the `# Python install (dev)` block** in Build & Dev with:

```markdown
# Python env (dev)
uv sync             # creates .venv, installs deps + dev group (editable)
uv run pytest test/ # run tests inside the uv-managed env
```

## Lock file and environment

Steps, in order:

1. `rm poetry.lock`
2. `uv lock` — regenerate against new pyproject.toml
3. `uv sync` — update `.venv` in place to match new lock
4. `uv run pytest --collect-only test/` — smoke check that the environment imports cleanly and pytest can discover tests

The existing `.venv` does not need to be recreated — uv updates it in place.

## Verification checklist

Before committing:

- [ ] `uv sync` runs cleanly, no resolver errors
- [ ] `uv run python -c "import st_aggrid; print(st_aggrid.__file__)"` imports the package
- [ ] `uv run pytest --collect-only test/` collects the existing Playwright tests without import errors
- [ ] `uv build` produces a wheel in `dist/`
- [ ] Wheel contents: `python -m zipfile -l dist/streamlit_aggrid-2.0.0-py3-none-any.whl` shows:
  - `st_aggrid/*.py` (Python modules)
  - `st_aggrid/frontend/build/...` (compiled JS/CSS)
  - `st_aggrid/json/*.json` (schema files)
- [ ] No references to `poetry` remain in `pyproject.toml`, `package.json`, `CLAUDE.md` (searched via grep, excluding `poetry.lock` which is deleted)

## Commit strategy

Single commit on `v2_component`:

```
migrate: poetry -> uv

- pyproject.toml: hatchling build-backend, dependency-groups (PEP 735)
- package.json: uv build replaces poetry build
- delete poetry.lock, regenerate uv.lock
- CLAUDE.md: update build/dev instructions
```

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Wheel missing `frontend/build` due to hatchling default exclusion | `artifacts` directive explicitly re-adds it to both wheel and sdist; verified via wheel contents check in verification checklist |
| uv lock resolver produces significantly different versions vs current lock | Expected drift is small (same package set, same constraints). Verified by running tests after `uv sync` |
| Someone pulls the branch with Poetry still installed and tries `poetry build` | Acceptable breakage — the whole point of the migration. CLAUDE.md documents the new flow |
| Frontend build script relies on Poetry implicitly | Checked: only the `uv build` replacement is needed; frontend `yarn build` is independent |

## Out of scope / future work

- Add a GitHub Actions workflow for CI (build + tests) using `astral-sh/setup-uv`. Currently no CI exists; adding one is a separate change.
- Publish to PyPI (currently distributed via git). Out of scope.
