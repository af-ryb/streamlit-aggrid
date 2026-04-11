# Poetry → uv Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Poetry with uv as the dependency manager and build driver for `streamlit-aggrid`, using `hatchling` as the PEP 517 build backend, while preserving wheel contents (Python package + compiled frontend assets + JSON schemas).

**Architecture:** Single-commit migration on branch `v2_component`. `pyproject.toml` loses all `[tool.poetry]` sections; dev deps move to PEP 735 `[dependency-groups]`; build backend becomes `hatchling` with `artifacts` directive to keep `frontend/build/` in the wheel. `package.json` build script replaces `poetry build` with `uv build`. `poetry.lock` is deleted, `uv.lock` is regenerated, `.venv` is synced in place. `CLAUDE.md` updated with new build/dev commands.

**Tech Stack:** uv 0.9.26, hatchling (latest), Python 3.13 (`.venv` already in place), yarn 4.1.0 workspaces, Vite (untouched).

**Spec:** `docs/superpowers/specs/2026-04-10-uv-migration-design.md`

---

## Task 1: Replace `pyproject.toml`

**Files:**
- Modify: `pyproject.toml` (full rewrite)

- [ ] **Step 1: Verify starting state**

Run:
```bash
cat pyproject.toml | grep -c '\[tool.poetry'
```
Expected: `2` (matches `[tool.poetry]` and `[tool.poetry.group.dev.dependencies]`)

Run:
```bash
grep -c 'poetry-core' pyproject.toml
```
Expected: `1`

- [ ] **Step 2: Overwrite `pyproject.toml`**

Replace the entire contents of `pyproject.toml` with:

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

- [ ] **Step 3: Verify no poetry references remain**

Run:
```bash
grep -c 'poetry' pyproject.toml
```
Expected: `0`

Run:
```bash
grep -c 'hatchling' pyproject.toml
```
Expected: `2` (once in `requires`, once in `build-backend`)

Run:
```bash
grep -c 'dependency-groups' pyproject.toml
```
Expected: `1`

- [ ] **Step 4: Do NOT commit yet**

The commit happens after locking, syncing, and verifying the build (Task 6). Leave staged state clean.

---

## Task 2: Delete `poetry.lock` and regenerate `uv.lock`

**Files:**
- Delete: `poetry.lock`
- Modify: `uv.lock` (regenerated)

- [ ] **Step 1: Delete `poetry.lock`**

Run:
```bash
rm poetry.lock
```

Run:
```bash
ls poetry.lock 2>&1 || echo "deleted"
```
Expected: `ls: cannot access 'poetry.lock': No such file or directory` followed by `deleted`

- [ ] **Step 2: Regenerate `uv.lock`**

Run:
```bash
uv lock
```

Expected: uv prints `Resolved N packages in Xms`. No errors. If uv complains about `pyproject.toml` parse errors, re-check Task 1 Step 2 — the TOML must be valid.

- [ ] **Step 3: Verify `uv.lock` exists and is non-empty**

Run:
```bash
test -s uv.lock && echo "ok"
```
Expected: `ok`

Run:
```bash
head -2 uv.lock
```
Expected: starts with `version = 1` and `revision = N`.

---

## Task 3: Sync `.venv` to new lock

**Files:**
- Modify: `.venv/` (in place, managed by uv)

- [ ] **Step 1: Sync environment**

Run:
```bash
uv sync
```

Expected: uv reports either "Audited N packages" (no changes) or "Installed/Uninstalled/Updated N packages". No resolver or installer errors.

- [ ] **Step 2: Verify the package is importable**

Run:
```bash
uv run python -c "import st_aggrid; print(st_aggrid.__file__)"
```
Expected: prints a path like `/home/homelab/repo/streamlit-aggrid/st_aggrid/__init__.py`. If `ImportError` or a stale path (pointing inside `.venv/lib/...`), the editable install is broken — re-run `uv sync --reinstall-package streamlit-aggrid`.

- [ ] **Step 3: Verify dev tools are available**

Run:
```bash
uv run pytest --version
```
Expected: prints a pytest version ≥ 8.3.5.

Run:
```bash
uv run ruff --version
```
Expected: prints a ruff version.

- [ ] **Step 4: Verify tests can be collected (no import errors in tests)**

Run:
```bash
uv run pytest --collect-only test/ 2>&1 | tail -20
```
Expected: pytest lists collected test items without ImportError / ModuleNotFoundError / collection errors. If tests use Playwright and browsers are not installed, you may see Playwright-specific warnings — those are acceptable for `--collect-only` since no test runs. What matters: no collection errors from import failures.

---

## Task 4: Replace `package.json` build script

**Files:**
- Modify: `package.json:13`

- [ ] **Step 1: Verify current state**

Run:
```bash
grep -n 'poetry build' package.json
```
Expected: `13:    "build": "yarn workspaces foreach -Avi run build && poetry build",`

- [ ] **Step 2: Edit line 13**

In `package.json`, replace the exact string:

`"build": "yarn workspaces foreach -Avi run build && poetry build",`

with:

`"build": "yarn workspaces foreach -Avi run build && uv build",`

- [ ] **Step 3: Verify**

Run:
```bash
grep -c 'poetry' package.json
```
Expected: `0`

Run:
```bash
grep -n 'uv build' package.json
```
Expected: `13:    "build": "yarn workspaces foreach -Avi run build && uv build",`

---

## Task 5: Update `CLAUDE.md`

**Files:**
- Modify: `CLAUDE.md:69` (yarn build comment)
- Modify: `CLAUDE.md:80` (Python build decision)
- Modify: `CLAUDE.md` Python install block (replace `pip install -e .` block with uv commands)

- [ ] **Step 1: Update line 69**

In `CLAUDE.md`, replace the exact line:

`yarn build          # root package.json — builds all workspaces then poetry build`

with:

`yarn build          # root package.json — builds all workspaces then uv build`

- [ ] **Step 2: Update line 80**

In `CLAUDE.md`, replace the exact line:

`Python build: **Poetry** (`poetry-core`).`

with:

`Python build: **hatchling** (via `uv build`).`

- [ ] **Step 3: Replace the Python install block**

In `CLAUDE.md`, locate this block (it's inside the `## Build & Dev` code fence, near the end of the fenced shell block):

```
# Python install (dev)
pip install -e .
```

Replace it with:

```
# Python env (dev)
uv sync             # creates .venv, installs deps + dev group (editable)
uv run pytest test/ # run tests inside the uv-managed env
```

- [ ] **Step 4: Verify no poetry references remain in CLAUDE.md**

Run:
```bash
grep -ni 'poetry' CLAUDE.md
```
Expected: no output.

Run:
```bash
grep -n 'uv build\|uv sync\|hatchling' CLAUDE.md
```
Expected: three lines matched (one `uv build`, one `uv sync`, one `hatchling`).

---

## Task 6: Build wheel and verify contents

**Files:**
- Creates: `dist/streamlit_aggrid-2.0.0-py3-none-any.whl`
- Creates: `dist/streamlit_aggrid-2.0.0.tar.gz`

These are gitignored via `.gitignore:17` (`dist/`), so they won't be committed.

**Assumption:** Frontend has been previously built and `st_aggrid/frontend/build/` already exists. If it doesn't, run `cd st_aggrid/frontend && yarn build` first — but normally it's already present from prior development (the frontend is rebuilt via `yarn workspaces foreach run build` as part of the top-level `yarn build`, but for this migration task we only verify the Python build step).

- [ ] **Step 1: Verify frontend build exists**

Run:
```bash
test -d st_aggrid/frontend/build && ls st_aggrid/frontend/build/ | head
```
Expected: lists files (at minimum `index.js` or similar bundled assets). If empty/missing, run `cd st_aggrid/frontend && yarn install && yarn build && cd ../..` before proceeding.

- [ ] **Step 2: Clean any prior `dist/`**

Run:
```bash
rm -rf dist/
```

- [ ] **Step 3: Build sdist and wheel**

Run:
```bash
uv build
```

Expected: uv output ends with two "Successfully built" lines, one for sdist (`.tar.gz`) and one for wheel (`.whl`). No build errors.

- [ ] **Step 4: Verify wheel filename and existence**

Run:
```bash
ls dist/
```
Expected: exactly two files — `streamlit_aggrid-2.0.0-py3-none-any.whl` and `streamlit_aggrid-2.0.0.tar.gz`.

- [ ] **Step 5: Inspect wheel contents — Python modules**

Run:
```bash
python -m zipfile -l dist/streamlit_aggrid-2.0.0-py3-none-any.whl | grep '\.py$'
```
Expected: lists all Python modules under `st_aggrid/` — at minimum:
- `st_aggrid/__init__.py`
- `st_aggrid/AgGrid.py`
- `st_aggrid/component.py`
- `st_aggrid/result.py`
- `st_aggrid/shared.py`
- `st_aggrid/aggrid_utils.py`
- `st_aggrid/grid_options_builder.py`

- [ ] **Step 6: Inspect wheel contents — frontend build artifacts**

Run:
```bash
python -m zipfile -l dist/streamlit_aggrid-2.0.0-py3-none-any.whl | grep 'frontend/build'
```
Expected: at least one file listed under `st_aggrid/frontend/build/` (bundled JS and CSS). If empty — the `artifacts` directive didn't work; stop and debug hatchling config before continuing.

- [ ] **Step 7: Inspect wheel contents — JSON schemas**

Run:
```bash
python -m zipfile -l dist/streamlit_aggrid-2.0.0-py3-none-any.whl | grep '\.json$'
```
Expected: lists the 5 JSON files — `columnEvents.json`, `columnProps.json`, `gridEvents.json`, `gridOptions.json`, `rowEvents.json` under `st_aggrid/json/`.

- [ ] **Step 8: Inspect wheel metadata**

Run:
```bash
python -m zipfile -e dist/streamlit_aggrid-2.0.0-py3-none-any.whl /tmp/wheel-check/
cat /tmp/wheel-check/streamlit_aggrid-2.0.0.dist-info/METADATA | head -30
```
Expected: `Name: streamlit-aggrid`, `Version: 2.0.0`, `Requires-Dist: streamlit >=1.44.0`, `Requires-Dist: pandas >=1.4.0`. No `bs4`, `playwright`, `pytest`, etc. in `Requires-Dist` (dev deps must not leak into wheel metadata since we used `[dependency-groups]`, not `[project.optional-dependencies]`).

- [ ] **Step 9: Clean up**

Run:
```bash
rm -rf /tmp/wheel-check dist/
```

---

## Task 7: Final grep sweep for lingering poetry references

**Files:** (no modifications — verification only)

- [ ] **Step 1: Search for any remaining poetry references in tracked files**

Run:
```bash
git ls-files | grep -v '^poetry\.lock$' | xargs grep -l 'poetry' 2>/dev/null
```
Expected: no output (no tracked files mention poetry). If any file is printed, inspect it and decide whether it needs an update — `README.md`, `LICENSE`, `MANIFEST.in`, etc. should not mention poetry; if they do and we missed it in the spec, add a step to fix and re-run this check.

- [ ] **Step 2: Confirm `poetry.lock` is not tracked**

Run:
```bash
git status --short poetry.lock
```
Expected: ` D poetry.lock` (deleted, staged or unstaged) — meaning git knows the file is gone.

---

## Task 8: Commit the migration

**Files:** all of the above (staged together).

- [ ] **Step 1: Review the full change set**

Run:
```bash
git status --short
```
Expected:
```
 M CLAUDE.md
 M package.json
 M pyproject.toml
 D poetry.lock
 M uv.lock
```
(Exact prefix may differ — ` M` for unstaged modifications is fine; we'll stage explicitly.)

Run:
```bash
git diff --stat pyproject.toml package.json CLAUDE.md
```
Expected: shows the three files with insertions/deletions. No surprise hunks.

- [ ] **Step 2: Stage files explicitly**

Run:
```bash
git add pyproject.toml package.json CLAUDE.md uv.lock
git rm poetry.lock
```

- [ ] **Step 3: Verify staging**

Run:
```bash
git status --short
```
Expected:
```
M  CLAUDE.md
M  package.json
M  pyproject.toml
D  poetry.lock
M  uv.lock
```
(All entries staged — column 1 populated, column 2 empty.)

- [ ] **Step 4: Commit**

Run:
```bash
git commit -m "$(cat <<'EOF'
migrate: poetry -> uv

- pyproject.toml: hatchling build-backend, dependency-groups (PEP 735)
- package.json: uv build replaces poetry build
- delete poetry.lock, regenerate uv.lock
- CLAUDE.md: update build/dev instructions

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 5: Verify commit landed**

Run:
```bash
git log -1 --stat
```
Expected: shows the new commit with 5 files changed (CLAUDE.md, package.json, pyproject.toml, poetry.lock, uv.lock). `poetry.lock` line shows deletion count matching old lock file size; `uv.lock` shows changes.

- [ ] **Step 6: Post-commit smoke test**

Run:
```bash
uv run pytest --collect-only test/ 2>&1 | tail -5
```
Expected: pytest collects tests without errors (same as Task 3 Step 4). Final sanity check that the committed state is a working env.

---

## Done

Migration complete. The branch `v2_component` now uses uv + hatchling exclusively. Next time someone clones the repo, they run `uv sync` instead of `poetry install`, and `yarn build` invokes `uv build` instead of `poetry build`.
