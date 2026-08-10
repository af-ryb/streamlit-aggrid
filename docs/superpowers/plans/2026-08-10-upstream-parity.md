# Upstream Parity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adopt the four things upstream `streamlit-aggrid` v2.0.0rc1 does better than this fork — static asset delivery, correct AG-Grid module registration, hotkey containment, result-carrying callbacks — and add the fast unit-test layer that makes them verifiable without a browser.

**Architecture:** The frontend bundle stops being inlined into every Streamlit session and starts being served as a content-hashed static file, declared through a Components v2 manifest (`[[tool.streamlit.component.components]]`) shipped inside the package. Because manifests are only discovered when a Streamlit `Runtime` exists, component registration becomes lazy. The remaining three changes are localized: a module-registration ledger and a keydown guard in `AgGridComponent.tsx`, an arity-detecting callback wrapper in `aggrid.py`, and a `test/unit/` tree selectable with `-m "not e2e"`.

**Tech Stack:** Python 3.10+, Streamlit 1.56 (Custom Components v2), pandas, hatchling + uv, React 18 + TypeScript, Vite 5 (library mode), AG-Grid 36.0.0, Yarn 4 via corepack, pytest + Playwright.

## Global Constraints

- Working branch is `upstream-parity`. Do not merge or rebase onto `main`/`v36.0`.
- The importable package stays `st_aggrid`. The **distribution** is renamed `streamlit-aggrid` → `st-aggrid`. This is deliberate: Streamlit's manifest scanner derives the package name from the distribution name (`_normalize_package_name`), so `find_spec("streamlit_aggrid")` must resolve for discovery to work in an editable install. Renaming the distribution is the smaller change.
- Project version moves `2.1.0` → `2.2.0`. The version appears in **two** files that must stay in sync: `pyproject.toml` and `st_aggrid/pyproject.toml`.
- Minimum Streamlit is raised to `>=1.56.0` — the version verified locally to ship `streamlit.components.v2.manifest_scanner` with `asset_dir` + glob support.
- `st_aggrid/frontend/build/` stays committed to git (the project is consumed via `pip install git+…`, and no build step runs at install time). The `!st_aggrid/frontend/build/` negation in `.gitignore` must survive.
- Yarn is not on `PATH`. Always invoke it as `corepack yarn …` from `st_aggrid/frontend`. Set `COREPACK_ENABLE_DOWNLOAD_PROMPT=0` to skip the prompt.
- No new runtime dependencies. `pandas` and `streamlit` remain the only two.
- AG-Grid stays at `36.0.0`; do not bump any `ag-grid-*` or `ag-charts-*` package.
- Python has no enforced formatter; match the surrounding style. `ruff` is available in the dev group.
- Commit after every task. Imperative mood, describing what changed.

---

## File Structure

**Task 1 — asset delivery**
- `pyproject.toml` — distribution rename, version, Streamlit floor.
- `st_aggrid/pyproject.toml` *(new)* — the in-wheel Components v2 manifest. Single responsibility: tell Streamlit where the built assets live.
- `st_aggrid/component.py` — rewritten: lazy registration by glob instead of eager inlining.
- `st_aggrid/aggrid.py` — one import and one call site follow the new accessor.
- `st_aggrid/frontend/vite.config.ts` — content-hashed output filenames; CSS minification re-enabled.
- `st_aggrid/frontend/package.json` — `build` wipes the output directory first (globs must match exactly one file).
- `test/unit/test_component_manifest.py` *(new)* — proves discovery, asset root and glob arity.
- `CLAUDE.md` — build/packaging notes.

**Task 2 — frontend correctness**
- `st_aggrid/frontend/src/AgGridComponent.tsx` — module-registration ledger; Streamlit hotkey guard.
- `test/grid_mixed_modules.py` *(new)* — Streamlit app: community grid rendered before an enterprise grid, plus a run counter.
- `test/test_grid_mixed_modules.py` *(new)* — Playwright tests for both behaviours.

**Task 3 — callbacks**
- `st_aggrid/aggrid.py` — `_callback_wants_result`, `_wrap_callback`, wired into both callback parameters.
- `test/unit/test_callbacks.py` *(new)* — arity detection and wrapper behaviour.

**Task 4 — test layer**
- `test/conftest.py` *(new)* — auto-marks everything outside `test/unit/` as `e2e`.
- `pyproject.toml` — registers the `e2e` marker.
- `test/unit/test_column_state.py` *(moved from `test/test_column_state.py`)*.
- `test/unit/test_result.py`, `test/unit/test_aggrid_utils.py`, `test/unit/test_shared.py`, `test/unit/test_grid_options_builder.py` *(new)*.
- `CLAUDE.md` — how to run the fast loop.

---

### Task 1: Serve the frontend bundle as a static asset

**Why this matters:** `st_aggrid/component.py` currently calls `.read_text()` on a 6.9 MB JS file and a 208 KB CSS file at import time and hands the raw strings to `st.components.v2.component`. Those strings travel to the browser inside the session's message stream on every session, are pinned in server memory for the process lifetime, and cannot be HTTP-cached. Declaring an `asset_dir` makes Streamlit serve them from `/_stcore/bidi-components/<component>/<file>` instead.

Two facts drive the design, both verified against the installed Streamlit 1.56:

1. `ComponentPathUtils.looks_like_inline_content` classifies a string as a *path* when it contains glob characters. Minified CSS containing `[` or `*` (attribute and universal selectors) would be misread as a glob — which is exactly why `cssMinify: false` exists today. Serving by path removes the ambiguity, so CSS minification can be turned back on.
2. `get_bidi_component_manager()` returns the Runtime's registry only when `Runtime.exists()`; otherwise it returns a throwaway manager with no manifests, and `build_definition_with_validation` raises `StreamlitAPIException` for a path-like `js`. Registration therefore **must** be lazy, or any plain-Python import of `st_aggrid` (including Task 4's unit suite) blows up.

**Files:**
- Modify: `pyproject.toml`
- Create: `st_aggrid/pyproject.toml`
- Modify: `st_aggrid/component.py` (full rewrite, currently 12 lines)
- Modify: `st_aggrid/aggrid.py:9` (import) and `st_aggrid/aggrid.py:345-350` (call site)
- Modify: `st_aggrid/frontend/vite.config.ts`
- Modify: `st_aggrid/frontend/package.json` (`scripts.build`)
- Modify: `CLAUDE.md`
- Test: `test/unit/test_component_manifest.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `st_aggrid.component.get_aggrid_component() -> Callable[..., Any]` — returns the CCv2 mounting command, registering it on first call. Replaces the module-level `_aggrid_component` object. The fully-qualified component key is the string `"st-aggrid.aggrid"`.

---

- [ ] **Step 1: Write the failing test**

Create `test/unit/test_component_manifest.py`:

```python
"""The Components v2 manifest must be discoverable at runtime.

Without it, ``st.components.v2.component(js="index-*.js")`` cannot resolve the
glob and the frontend bundle falls back to being inlined into every session.

Pure Python — no browser, no Streamlit runtime.
"""

from pathlib import Path

from streamlit.components.v2.manifest_scanner import scan_component_manifests

PACKAGE_ROOT = (Path(__file__).resolve().parents[2] / "st_aggrid").resolve()
BUILD_DIR = PACKAGE_ROOT / "frontend" / "build"

DISTRIBUTION_NAME = "st-aggrid"
COMPONENT_NAME = "aggrid"


def _find_manifest():
    for manifest, package_root in scan_component_manifests():
        if manifest.name == DISTRIBUTION_NAME:
            return manifest, Path(package_root).resolve()
    return None, None


def test_manifest_is_discovered():
    manifest, package_root = _find_manifest()
    assert manifest is not None, (
        f"No manifest named {DISTRIBUTION_NAME!r}. If the distribution was just "
        "renamed, run `uv lock && uv sync` so the installed metadata matches."
    )
    assert package_root == PACKAGE_ROOT


def test_manifest_declares_the_aggrid_component():
    manifest, _ = _find_manifest()
    assert [c.name for c in manifest.components] == [COMPONENT_NAME]
    assert manifest.components[0].asset_dir == "frontend/build"


def test_asset_dir_resolves_to_the_build_output():
    manifest, package_root = _find_manifest()
    resolved = manifest.components[0].resolve_asset_root(package_root)
    assert Path(resolved).resolve() == BUILD_DIR


def test_each_asset_glob_resolves_to_exactly_one_file():
    # st.components.v2.component() raises unless a glob matches exactly one
    # file, so a stale bundle left behind by a previous build is a hard error.
    assert len(list(BUILD_DIR.glob("index-*.js"))) == 1
    assert len(list(BUILD_DIR.glob("index-*.css"))) == 1
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd /home/homelab/repo/streamlit-aggrid
uv run pytest test/unit/test_component_manifest.py -v
```

Expected: all four tests FAIL. `test_manifest_is_discovered` fails its assertion message (no manifest exists yet); the others fail with `AttributeError: 'NoneType' object has no attribute 'components'` or on the glob counts.

- [ ] **Step 3: Rename the distribution and raise the Streamlit floor**

In `pyproject.toml`, change three lines inside `[project]`:

```toml
[project]
name = "st-aggrid"
version = "2.2.0"
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
dependencies = ["streamlit >=1.56.0", "pandas >=1.4.0"]
```

Leave every other table (`[dependency-groups]`, `[build-system]`, `[tool.hatch.*]`, `[tool.pytest.ini_options]`) untouched. In particular `[tool.hatch.build.targets.wheel] only-include = ["st_aggrid"]` still names the *directory*, which is not being renamed.

- [ ] **Step 4: Create the in-wheel manifest**

Create `st_aggrid/pyproject.toml`:

```toml
# Minimal manifest shipped inside the wheel so Streamlit's Components v2
# manifest scanner can locate this component's assets at runtime.
#
# The scanner (streamlit/components/v2/manifest_scanner.py) looks for a
# pyproject.toml belonging to the distribution and resolves `asset_dir`
# relative to the package root it finds. Keeping a copy inside the package
# makes discovery work for both editable installs (found via the import spec)
# and wheels installed from git (found by walking the distribution's file list).
#
# `version` must be kept in sync with the root pyproject.toml.
[project]
name = "st-aggrid"
version = "2.2.0"

[[tool.streamlit.component.components]]
name = "aggrid"
asset_dir = "frontend/build"
```

The component's fully-qualified key becomes `"<project name>.<component name>"` = `"st-aggrid.aggrid"`.

- [ ] **Step 5: Reinstall so the distribution metadata matches**

```bash
cd /home/homelab/repo/streamlit-aggrid
uv lock && uv sync
```

Verify the old distribution is gone and the new one is present:

```bash
ls -d .venv/lib/python*/site-packages/*.dist-info | grep -i aggrid
```

Expected: exactly one entry, `st_aggrid-2.2.0.dist-info`. If `streamlit_aggrid-2.1.0.dist-info` is still there, run `uv sync --reinstall` and check again.

- [ ] **Step 6: Run the test to see discovery pass and the globs fail**

```bash
uv run pytest test/unit/test_component_manifest.py -v
```

Expected: the first three tests PASS; `test_each_asset_glob_resolves_to_exactly_one_file` FAILS, because the build still emits `index.js` / `style.css` rather than hashed names.

- [ ] **Step 7: Emit content-hashed filenames from Vite**

Replace the whole of `st_aggrid/frontend/vite.config.ts` with:

```ts
import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"

export default defineConfig({
  plugins: [react()],
  base: "./",
  define: {
    "process.env.NODE_ENV": JSON.stringify("production"),
  },
  build: {
    outDir: "build",
    chunkSizeWarningLimit: 5000, // AG-Grid is large (~7MB bundled)
    lib: {
      entry: "src/index.tsx",
      formats: ["es"],
      // Content-hashed so the browser cache invalidates on a real change.
      // st_aggrid/component.py globs these as index-*.js / index-*.css, and a
      // glob must match exactly one file — the `build` script wipes outDir
      // first so stale hashes can't accumulate.
      fileName: "index-[hash]",
    },
    rollupOptions: {
      output: {
        assetFileNames: "index-[hash][extname]",
        inlineDynamicImports: true, // single JS bundle
      },
    },
  },
  server: { port: 3001 },
})
```

Note what is deliberately gone: `cssMinify: false`. That flag existed because inline CSS was classified by `looks_like_inline_content`, which reads `[` and `*` in minified CSS as glob characters. Assets served by path are never passed through that heuristic, so minification is safe again.

Note what is deliberately absent: source maps. They would be genuinely useful, but `build/` is committed to git, and adding ~20 MB of `.map` blobs per rebuild is a worse trade than losing them.

- [ ] **Step 8: Make the build wipe its output directory**

In `st_aggrid/frontend/package.json`, change the `build` script only:

```json
  "scripts": {
    "dev": "vite",
    "build": "rm -rf build && tsc && vite build",
    "clean": "rm -rf build"
  },
```

- [ ] **Step 9: Rebuild the frontend and inspect the output**

```bash
cd /home/homelab/repo/streamlit-aggrid/st_aggrid/frontend
COREPACK_ENABLE_DOWNLOAD_PROMPT=0 corepack yarn build
ls -la build/
```

Expected: exactly two files, named `index-<hash>.js` and `index-<hash>.css`. If Vite emitted `style.css` instead of a hashed CSS name, the `assetFileNames` entry did not take effect — fix that before continuing rather than loosening the glob.

- [ ] **Step 10: Run the test to verify it passes**

```bash
cd /home/homelab/repo/streamlit-aggrid
uv run pytest test/unit/test_component_manifest.py -v
```

Expected: 4 passed.

- [ ] **Step 11: Rewrite the component registration**

Replace the whole of `st_aggrid/component.py` with:

```python
"""CCv2 component registration.

The frontend bundle is served from the directory declared as ``asset_dir`` in
``st_aggrid/pyproject.toml``, so it travels to the browser as a cacheable
static file rather than being inlined into every session's message stream.

Registration is lazy on purpose. ``st.components.v2.component`` resolves the
globs below against the component manifest, and manifests are only discovered
when a Streamlit ``Runtime`` exists (``Runtime.__init__`` calls
``discover_and_register_components``). Registering at import time would raise
``StreamlitAPIException`` for any plain-Python import of this package,
including the unit test suite.
"""

from __future__ import annotations

from typing import Any, Callable

import streamlit as st

# "<project name>.<component name>", both as declared in st_aggrid/pyproject.toml.
_COMPONENT_NAME = "st-aggrid.aggrid"

# Content-hashed filenames produced by vite.config.ts. Each glob must resolve
# to exactly one file; the frontend `build` script wipes the output directory
# first so a stale hash can never make this ambiguous.
_JS_GLOB = "index-*.js"
_CSS_GLOB = "index-*.css"

_component: Callable[..., Any] | None = None


def get_aggrid_component() -> Callable[..., Any]:
    """Return the CCv2 mounting command, registering it on first use."""
    global _component
    if _component is None:
        _component = st.components.v2.component(
            name=_COMPONENT_NAME,
            js=_JS_GLOB,
            css=_CSS_GLOB,
            html="<div></div>",
            isolate_styles=False,  # AG-Grid injects styles globally
        )
    return _component
```

- [ ] **Step 12: Point the call site at the accessor**

First find every importer:

```bash
cd /home/homelab/repo/streamlit-aggrid
grep -rn "_aggrid_component" --include=*.py .
```

Expected: only `st_aggrid/aggrid.py`. In that file change the import (line 9):

```python
from st_aggrid.component import get_aggrid_component
```

and the mount call (currently `result = _aggrid_component(...)` around line 345):

```python
    # Mount the component
    result = get_aggrid_component()(
        data=component_data,
        key=key,
        on_grid_state_change=on_grid_state_change,
        on_api_response_change=on_api_response_change,
    )
```

If `grep` turned up any other importer, update it the same way.

- [ ] **Step 13: Verify a plain import still works outside a Streamlit runtime**

```bash
cd /home/homelab/repo/streamlit-aggrid
uv run python -c "import st_aggrid; print('import OK'); print(st_aggrid.AgGrid)"
```

Expected: prints `import OK` and the function repr, with no `StreamlitAPIException`. This is the whole point of lazy registration — if it raises, the registration is still eager somewhere.

- [ ] **Step 14: Verify the real app renders from the served asset**

```bash
cd /home/homelab/repo/streamlit-aggrid
uv run pytest test/test_grid_initialization.py -v
```

Expected: 6 passed. A broken asset URL means the JS never loads and every `.ag-root` assertion fails, so this suite is a genuine end-to-end check of the new delivery path.

- [ ] **Step 15: Update the project notes**

In `CLAUDE.md`, under "## Build & Dev", replace the frontend block with:

```
# Frontend — `yarn` is NOT on PATH; invoke via corepack (Yarn 4 Berry).
cd st_aggrid/frontend
corepack yarn install
corepack yarn build   # rm -rf build && tsc && vite build → st_aggrid/frontend/build/
corepack yarn dev     # dev server on port 3001
```

and add a new section immediately after "## Key Design Decisions":

```
## Packaging & asset delivery

- Distribution name is **`st-aggrid`**; the importable package is `st_aggrid`.
  These must stay aligned: Streamlit's Components v2 manifest scanner derives
  the package name from the distribution name, so renaming either one alone
  breaks asset discovery.
- `st_aggrid/pyproject.toml` is the in-wheel component manifest
  (`asset_dir = "frontend/build"`). Its `version` must match the root
  `pyproject.toml` on every version bump.
- The bundle is served as a static asset, not inlined. Filenames are
  content-hashed (`index-<hash>.js` / `index-<hash>.css`) and each glob in
  `component.py` must match exactly one file — which is why `yarn build`
  wipes `build/` first.
- Component registration is lazy (`get_aggrid_component()`): manifests only
  exist once a Streamlit Runtime is up, so eager registration would break
  plain-Python imports.
- `st_aggrid/frontend/build/` is committed to git on purpose — the project is
  installed straight from git and nothing builds the frontend at install time.
```

Also update the "Current: 36.0.0" section's step 4 to mention that a rebuild changes the hashed filenames, so `git status` will show a delete + add rather than a modify.

- [ ] **Step 16: Commit**

```bash
cd /home/homelab/repo/streamlit-aggrid
git add pyproject.toml uv.lock st_aggrid/pyproject.toml st_aggrid/component.py \
        st_aggrid/aggrid.py st_aggrid/frontend/vite.config.ts \
        st_aggrid/frontend/package.json st_aggrid/frontend/build \
        test/unit/test_component_manifest.py CLAUDE.md
git commit -m "Serve frontend bundle as a manifest-declared static asset

Rename the distribution to st-aggrid so Streamlit's Components v2 manifest
scanner can resolve the package, declare frontend/build as asset_dir, emit
content-hashed filenames, and register the component lazily so plain-Python
imports keep working outside a Streamlit runtime."
```

---

### Task 2: Fix module registration and contain Streamlit's hotkeys

**Why this matters:** two independent frontend defects, both in `AgGridComponent.tsx`, both cheap to fix and both invisible to the current test suite.

1. `let modulesRegistered = false` at module scope (line 50) latches on the **first** grid rendered on a page. A community grid rendered before an enterprise grid permanently starves the enterprise grid of its modules — no sidebar, no tool panels, no pivot. Upstream avoids this by holding the flag in a per-instance `useRef`.
2. Without an iframe, a keystroke on a focused grid cell bubbles to `document`, where Streamlit binds single-key shortcuts (`r` = rerun, `c` = clear cache). Arrowing through a grid and typing `r` silently reruns the app.

**Files:**
- Modify: `st_aggrid/frontend/src/AgGridComponent.tsx:49-72` (registration) and the effect block around `:690-699`
- Create: `test/grid_mixed_modules.py`
- Test: `test/test_grid_mixed_modules.py`

**Interfaces:**
- Consumes: `AgGridData` from `./types/AgGridTypes` (already imported at `AgGridComponent.tsx:37`).
- Produces: nothing other tasks depend on. The exported default component keeps its current props.

---

- [ ] **Step 1: Write the failing test app**

Create `test/grid_mixed_modules.py`:

```python
"""Two grids on one page, community rendered BEFORE enterprise.

Guards two regressions:

1. Module registration. A single module-level "already registered" latch lets
   the first grid decide which AG-Grid bundle every later grid gets, so the
   enterprise grid's sidebar would never render.
2. Streamlit hotkey containment. `run_count` increments on every script run,
   so a rerun accidentally triggered by pressing "r" over a grid cell is
   visible in the DOM.
"""

import pandas as pd
import streamlit as st

from st_aggrid import AgGrid

st.session_state["run_count"] = st.session_state.get("run_count", 0) + 1

# A keyed container so the test can locate the counter as `.st-key-run_count`,
# the same addressing every other e2e test uses. `st.write` alone would need a
# text locator, which matches nested elements and trips Playwright's strict mode.
with st.container(key="run_count"):
    st.write(st.session_state["run_count"])

df = pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})

st.subheader("community")
AgGrid(df, key="community_grid", height=150)

st.subheader("enterprise")
AgGrid(
    df,
    key="enterprise_grid",
    height=150,
    enable_enterprise_modules=True,
    grid_options={
        "columnDefs": [{"field": "a"}, {"field": "b"}],
        "sideBar": {"toolPanels": ["columns"]},
    },
)
```

- [ ] **Step 2: Write the failing test**

Create `test/test_grid_mixed_modules.py`:

```python
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

from e2e_utils import StreamlitRunner

ROOT_DIRECTORY = Path(__file__).parent.parent.absolute()
BASIC_EXAMPLE_FILE = ROOT_DIRECTORY / "test" / "grid_mixed_modules.py"


@pytest.fixture(autouse=True, scope="module")
def streamlit_app():
    with StreamlitRunner(BASIC_EXAMPLE_FILE) as runner:
        yield runner


@pytest.fixture(autouse=True, scope="function")
def go_to_app(page: Page, streamlit_app: StreamlitRunner):
    page.goto(streamlit_app.server_url)
    page.get_by_role("img", name="Running...").is_hidden()


def test_both_grids_render(page: Page):
    expect(page.locator(".st-key-community_grid").locator(".ag-root")).to_be_visible()
    expect(page.locator(".st-key-enterprise_grid").locator(".ag-root")).to_be_visible()


def test_enterprise_grid_gets_its_modules_despite_the_community_grid(page: Page):
    """The sidebar only exists if AllEnterpriseModule was registered.

    A module-level latch set by the community grid above would swallow the
    enterprise registration and leave this locator empty.
    """
    enterprise = page.locator(".st-key-enterprise_grid")
    expect(enterprise.locator(".ag-side-bar")).to_be_visible()


def test_community_grid_has_no_sidebar(page: Page):
    community = page.locator(".st-key-community_grid")
    expect(community.locator(".ag-side-bar")).to_have_count(0)


def test_pressing_r_over_a_grid_cell_does_not_rerun_the_app(page: Page):
    """Streamlit binds "r" to rerun on the document. Without an iframe the grid
    must stop that key from escaping, or keyboard use silently reruns the app.
    """
    counter = page.locator(".st-key-run_count")

    community = page.locator(".st-key-community_grid")
    cell = community.locator(".ag-cell").first
    cell.click()

    # The click itself may trigger a rerun (selection). Let that settle before
    # taking the baseline, or the rerun it causes would be blamed on the "r".
    page.wait_for_timeout(1000)
    before = counter.inner_text()

    page.keyboard.press("r")
    page.wait_for_timeout(1500)

    assert counter.inner_text() == before
```

- [ ] **Step 3: Run the tests to verify they fail**

```bash
cd /home/homelab/repo/streamlit-aggrid
uv run pytest test/test_grid_mixed_modules.py -v
```

Expected: `test_both_grids_render` and `test_community_grid_has_no_sidebar` PASS; `test_enterprise_grid_gets_its_modules_despite_the_community_grid` FAILS (no `.ag-side-bar`) and `test_pressing_r_over_a_grid_cell_does_not_rerun_the_app` FAILS (`run_count` incremented).

- [ ] **Step 4: Replace the module-registration latch with a ledger**

In `st_aggrid/frontend/src/AgGridComponent.tsx`, replace lines 49-72 (from the `// Track whether modules have been registered…` comment through the end of `registerModules`) with:

```ts
// AG-Grid's ModuleRegistry is global and idempotent, but WHICH bundle to
// register is a per-grid decision driven by `enable_enterprise_modules`. A
// single "already registered" latch would let whichever grid renders first
// decide for every grid on the page — a community grid above an enterprise
// grid would permanently starve the latter of its modules. Track the bundles
// actually registered instead, so a later grid asking for a bundle we have
// not seen still gets it.
type ModuleBundle = "community" | "enterprise" | "enterprise+charts"

const registeredBundles = new Set<ModuleBundle>()

function bundleFor(data: AgGridData): ModuleBundle {
  const flag = data.enable_enterprise_modules
  if (flag === "enterprise+AgCharts") return "enterprise+charts"
  if (flag === true || flag === "enterpriseOnly") return "enterprise"
  return "community"
}

function registerModules(data: AgGridData) {
  const bundle = bundleFor(data)

  if (!registeredBundles.has(bundle)) {
    registeredBundles.add(bundle)

    if (bundle === "enterprise+charts") {
      ModuleRegistry.registerModules([
        AllEnterpriseModule.with(AgChartsEnterpriseModule),
      ])
    } else if (bundle === "enterprise") {
      ModuleRegistry.registerModules([AllEnterpriseModule])
    } else {
      ModuleRegistry.registerModules([AllCommunityModule])
    }
  }

  // Runs even when the bundle was already registered: a license key can
  // arrive with a later grid, and setting it again is idempotent.
  if (bundle !== "community" && data.license_key) {
    LicenseManager.setLicenseKey(data.license_key)
  }
}
```

- [ ] **Step 5: Add the Streamlit hotkey guard**

In the same file, insert this effect immediately **before** the existing unmount-cleanup effect (the one whose body is `return () => { refitCleanupRef.current?.() … }`, around line 690):

```tsx
  // Streamlit binds single-key shortcuts on the document ("r" reruns the app,
  // "c" clears the cache). Without an iframe a keystroke on a focused grid
  // cell bubbles all the way up, so arrowing around the grid and typing "r"
  // silently reruns. Keep those two keys inside the grid.
  //
  // stopPropagation() does not cancel the default action, so nothing that
  // depends on the browser's own handling breaks. Editable targets are skipped
  // outright so AG-Grid's inputs (filters, Find, quick-search) and our toolbar
  // keep full event semantics.
  useEffect(() => {
    const container = gridContainerRef.current
    if (!container) return

    const streamlitShortcuts = new Set(["r", "c"])

    const isEditableTarget = (target: EventTarget | null): boolean => {
      if (!(target instanceof HTMLElement)) return false
      const tag = target.tagName
      return (
        tag === "INPUT" ||
        tag === "TEXTAREA" ||
        tag === "SELECT" ||
        target.isContentEditable
      )
    }

    const stopStreamlitShortcuts = (e: KeyboardEvent) => {
      if (e.ctrlKey || e.metaKey || e.altKey) return
      if (!streamlitShortcuts.has(e.key.toLowerCase())) return
      if (isEditableTarget(e.target)) return
      e.stopPropagation()
    }

    container.addEventListener("keydown", stopStreamlitShortcuts, true)
    return () => {
      container.removeEventListener("keydown", stopStreamlitShortcuts, true)
    }
  }, [])
```

- [ ] **Step 6: Rebuild the frontend**

```bash
cd /home/homelab/repo/streamlit-aggrid/st_aggrid/frontend
COREPACK_ENABLE_DOWNLOAD_PROMPT=0 corepack yarn build
```

Expected: build succeeds with no TypeScript errors, and `build/` again holds exactly one `index-*.js` and one `index-*.css`.

- [ ] **Step 7: Run the tests to verify they pass**

```bash
cd /home/homelab/repo/streamlit-aggrid
uv run pytest test/test_grid_mixed_modules.py -v
```

Expected: 4 passed.

- [ ] **Step 8: Check for regressions in the existing suite**

```bash
cd /home/homelab/repo/streamlit-aggrid
uv run pytest test/test_grid_initialization.py test/test_grid_data_render.py \
              test/test_grid_return.py test/test_grid_35_3_features.py -v
```

Expected: all pass. `test_grid_35_3_features.py` exercises enterprise features, so it is the one most likely to notice a registration mistake.

- [ ] **Step 9: Commit**

```bash
cd /home/homelab/repo/streamlit-aggrid
git add st_aggrid/frontend/src/AgGridComponent.tsx st_aggrid/frontend/build \
        test/grid_mixed_modules.py test/test_grid_mixed_modules.py
git commit -m "Register AG-Grid modules per bundle and contain Streamlit hotkeys

A module-level latch let the first grid on a page decide which AG-Grid bundle
every later grid received, so a community grid above an enterprise grid
starved it of its modules. Track registered bundles instead. Also stop
unmodified 'r'/'c' from escaping the grid, where Streamlit binds them to
rerun and clear-cache."
```

---

### Task 3: Pass the grid result into user callbacks

**Why this matters:** `on_grid_state_change` and `on_api_response_change` are currently invoked with no arguments (`aggrid.py:336-342` installs `_noop` and passes the user's callable straight through), so a caller has to reach into `st.session_state[key]` and rebuild the result by hand. Upstream hands its callback the parsed return object. Existing zero-argument callbacks must keep working, so the wrapper detects arity instead of changing the contract unconditionally.

**Files:**
- Modify: `st_aggrid/aggrid.py` — add `import inspect` and the two helpers near the top; replace the callback-defaulting block at `:335-342`; pass wrapped callbacks at the mount call
- Test: `test/unit/test_callbacks.py`

**Interfaces:**
- Consumes: `st_aggrid.result.AgGridResult(component_result, original_data)` — already imported in `aggrid.py:10`. `get_aggrid_component()` from Task 1.
- Produces:
  - `st_aggrid.aggrid._callback_wants_result(callback: Callable) -> bool`
  - `st_aggrid.aggrid._wrap_callback(callback: Optional[Callable], key: Optional[str], original_data: Optional[pd.DataFrame]) -> Callable[[], None]`

---

- [ ] **Step 1: Write the failing test**

Create `test/unit/test_callbacks.py`:

```python
"""Callback arity detection and wrapping.

Callbacks used to be invoked with no arguments. They may now take the
AgGridResult, and both shapes must keep working — so the wrapper inspects the
signature rather than changing the contract for everyone.

Pure Python — no browser, no Streamlit runtime.
"""

import functools

import pytest

from st_aggrid.aggrid import _callback_wants_result, _wrap_callback


# --- _callback_wants_result ------------------------------------------------


def test_zero_arg_function_does_not_want_the_result():
    def cb():
        pass

    assert _callback_wants_result(cb) is False


def test_one_positional_arg_wants_the_result():
    def cb(result):
        pass

    assert _callback_wants_result(cb) is True


def test_var_positional_wants_the_result():
    def cb(*args):
        pass

    assert _callback_wants_result(cb) is True


def test_defaulted_positional_arg_wants_the_result():
    def cb(result=None):
        pass

    assert _callback_wants_result(cb) is True


def test_keyword_only_arg_does_not_want_the_result():
    def cb(*, result=None):
        pass

    assert _callback_wants_result(cb) is False


def test_lambda_arity_is_detected():
    assert _callback_wants_result(lambda: None) is False
    assert _callback_wants_result(lambda r: None) is True


def test_partial_with_the_arg_already_bound_does_not_want_the_result():
    def cb(a, b):
        pass

    assert _callback_wants_result(functools.partial(cb, 1, 2)) is False


def test_callable_object_is_inspected_without_counting_self():
    class Handler:
        def __call__(self, result):
            pass

    assert _callback_wants_result(Handler()) is True


def test_unreadable_signature_is_treated_as_zero_arity():
    # Some C callables have no introspectable signature. Guessing "takes an
    # argument" would raise TypeError at callback time, so fail the safe way.
    class Weird:
        __call__ = None

    assert _callback_wants_result(Weird()) is False


# --- _wrap_callback --------------------------------------------------------


def test_none_becomes_a_no_op():
    wrapped = _wrap_callback(None, key="g", original_data=None)
    assert wrapped() is None


def test_zero_arg_callback_is_passed_through_unchanged():
    def cb():
        pass

    assert _wrap_callback(cb, key="g", original_data=None) is cb


def test_result_callback_without_a_key_is_rejected():
    def cb(result):
        pass

    with pytest.raises(ValueError, match="key"):
        _wrap_callback(cb, key=None, original_data=None)


def test_result_callback_receives_an_aggrid_result(monkeypatch):
    import types

    import st_aggrid.aggrid as aggrid_module
    from st_aggrid.result import AgGridResult

    component_result = types.SimpleNamespace(
        grid_state={"eventName": "selectionChanged"},
        api_response=None,
        notes=None,
    )
    monkeypatch.setattr(
        aggrid_module.st, "session_state", {"my_grid": component_result}
    )

    seen = []

    def cb(result):
        seen.append(result)

    _wrap_callback(cb, key="my_grid", original_data=None)()

    assert len(seen) == 1
    assert isinstance(seen[0], AgGridResult)
    assert seen[0].event_name == "selectionChanged"
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd /home/homelab/repo/streamlit-aggrid
uv run pytest test/unit/test_callbacks.py -v
```

Expected: collection FAILS with `ImportError: cannot import name '_callback_wants_result' from 'st_aggrid.aggrid'`.

- [ ] **Step 3: Implement the helpers**

In `st_aggrid/aggrid.py`, add `import inspect` to the standard-library imports at the top (they currently start with `import uuid` / `import warnings`), then add both helpers immediately above `def AgGrid(`:

```python
def _callback_wants_result(callback: Callable) -> bool:
    """True if ``callback`` accepts the grid result as a positional argument.

    Callbacks were historically invoked with no arguments, so both arities have
    to keep working. Anything whose signature cannot be read is treated as
    zero-arity — the safe direction, since calling a zero-argument callable
    with an argument raises at the worst possible moment.
    """
    try:
        parameters = inspect.signature(callback).parameters.values()
    except (TypeError, ValueError):
        return False

    positional = (
        inspect.Parameter.POSITIONAL_ONLY,
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
        inspect.Parameter.VAR_POSITIONAL,
    )
    return any(p.kind in positional for p in parameters)


def _wrap_callback(
    callback: Optional[Callable],
    key: Optional[str],
    original_data: Optional[pd.DataFrame],
) -> Callable[[], None]:
    """Adapt a user callback to the zero-argument shape CCv2 expects.

    A callback that takes an argument is handed an ``AgGridResult`` built from
    the component state Streamlit stores under ``key``; a zero-argument
    callback is passed straight through.
    """
    if callback is None:
        return lambda: None

    if not _callback_wants_result(callback):
        return callback

    if key is None:
        raise ValueError(
            "A callback that accepts the grid result requires key= to be set, "
            "because the result is read back from st.session_state[key]."
        )

    def _dispatch() -> None:
        callback(
            AgGridResult(
                component_result=st.session_state.get(key),
                original_data=original_data,
            )
        )

    return _dispatch
```

`Callable` and `Optional` are already imported at `aggrid.py:3`; `pd` at `:5`; `st` at `:6`; `AgGridResult` at `:10`.

- [ ] **Step 4: Wire the wrappers into AgGrid()**

In `st_aggrid/aggrid.py`, replace the block that currently reads:

```python
    # Ensure callbacks are set so result attributes exist
    def _noop() -> None:
        return None

    if on_grid_state_change is None:
        on_grid_state_change = _noop
    if on_api_response_change is None:
        on_api_response_change = _noop
```

with:

```python
    # CCv2 callbacks take no arguments. Adapt any callback that asks for the
    # grid result, and keep a no-op in place otherwise so the component always
    # declares both state keys and the result attributes exist.
    on_grid_state_change = _wrap_callback(on_grid_state_change, key, original_data)
    on_api_response_change = _wrap_callback(on_api_response_change, key, original_data)
```

This block must stay **after** `original_data` is computed (it is assigned around line 298) and **before** the mount call.

- [ ] **Step 5: Run the test to verify it passes**

```bash
cd /home/homelab/repo/streamlit-aggrid
uv run pytest test/unit/test_callbacks.py -v
```

Expected: 14 passed.

- [ ] **Step 6: Document the new callback shape**

In `st_aggrid/aggrid.py`, update the two docstring entries in `AgGrid`'s Parameters section:

```
    on_grid_state_change : callable, optional
        Called when auto-collected grid state changes. May take no arguments,
        or a single argument which receives the ``AgGridResult``. The
        result-taking form requires ``key`` to be set.

    on_api_response_change : callable, optional
        Called when an explicit API call returns a response. May take no
        arguments, or a single argument which receives the ``AgGridResult``.
        The result-taking form requires ``key`` to be set.
```

- [ ] **Step 7: Check for regressions**

```bash
cd /home/homelab/repo/streamlit-aggrid
uv run pytest test/test_grid_return.py test/test_grid_saved_view.py -v
```

Expected: all pass — these exercise grids with callbacks and explicit API calls.

- [ ] **Step 8: Commit**

```bash
cd /home/homelab/repo/streamlit-aggrid
git add st_aggrid/aggrid.py test/unit/test_callbacks.py
git commit -m "Hand the AgGridResult to callbacks that ask for it

CCv2 callbacks take no arguments, so callers had to rebuild the result from
session_state by hand. Detect the callback's arity and pass an AgGridResult to
any callback that accepts one, leaving zero-argument callbacks untouched."
```

---

### Task 4: Add a fast, browser-free test layer

**Why this matters:** every test except `test/test_column_state.py` drives a real Streamlit app through Playwright, so there is no way to check Python-side logic in seconds. Upstream keeps a 553-line unit suite and defaults pytest to `-m "not e2e"`. This task builds the same split without touching the existing e2e scenarios, which are richer than upstream's and stay exactly as they are.

**Files:**
- Create: `test/conftest.py`
- Modify: `pyproject.toml` (`[tool.pytest.ini_options] markers`)
- Move: `test/test_column_state.py` → `test/unit/test_column_state.py`
- Create: `test/unit/test_result.py`, `test/unit/test_aggrid_utils.py`, `test/unit/test_shared.py`, `test/unit/test_grid_options_builder.py`
- Modify: `CLAUDE.md`

**Interfaces:**
- Consumes: `test/unit/` already exists (created in Task 1). `st_aggrid.aggrid` imports cleanly outside a runtime thanks to Task 1's lazy registration.
- Produces: the `e2e` pytest marker, auto-applied to every test outside `test/unit/`.

---

- [ ] **Step 1: Write the failing marker test**

Create `test/conftest.py`:

```python
"""Auto-mark the browser suite so the fast loop can select against it.

Everything under ``test/`` drives a real Streamlit app through Playwright
except ``test/unit/``, which is pure Python. Marking by location keeps
individual test files free of boilerplate and means a new e2e file is
correctly classified the moment it is created.
"""

from pathlib import Path

import pytest

UNIT_DIR = (Path(__file__).parent / "unit").resolve()


def pytest_collection_modifyitems(items):
    for item in items:
        path = Path(str(item.fspath)).resolve()
        if UNIT_DIR in path.parents:
            continue
        item.add_marker(pytest.mark.e2e)
```

- [ ] **Step 2: Run the fast selection to verify it fails**

```bash
cd /home/homelab/repo/streamlit-aggrid
uv run pytest -m "not e2e" --collect-only -q 2>&1 | tail -20
```

Expected: pytest warns `PytestUnknownMarkWarning: Unknown pytest.mark.e2e`, because the marker is not registered yet.

- [ ] **Step 3: Register the marker**

In `pyproject.toml`, replace the `[tool.pytest.ini_options]` table with:

```toml
[tool.pytest.ini_options]
addopts = "-m 'not slow'"
markers = [
    "slow: long-running performance tests (1M-row grid); excluded by default, run with -m slow",
    "e2e: drives a real browser via Playwright and needs a built frontend. Applied automatically to every test outside test/unit. Fast loop: pytest -m 'not e2e'",
]
```

`addopts` is deliberately unchanged: the default run still executes everything except the slow performance suite, so nobody's habits break. The fast loop is opt-in via `-m "not e2e"`.

- [ ] **Step 4: Run the fast selection to verify it passes**

```bash
cd /home/homelab/repo/streamlit-aggrid
uv run pytest -m "not e2e" -q
```

Expected: no `PytestUnknownMarkWarning`, and only `test/unit/` tests are collected — at this point `test_component_manifest.py` (4 tests) and `test_callbacks.py` (14 tests).

- [ ] **Step 5: Move the existing unit test**

```bash
cd /home/homelab/repo/streamlit-aggrid
git mv test/test_column_state.py test/unit/test_column_state.py
uv run pytest -m "not e2e" -q
```

Expected: the column-state tests are now part of the fast selection and still pass. Its module docstring says "fast to run via ``pytest test/test_column_state.py``" — update that path to `test/unit/test_column_state.py`.

- [ ] **Step 6: Write the AgGridResult tests**

Create `test/unit/test_result.py`:

```python
"""AgGridResult reads a CCv2 component result.

The component result is an attribute-accessible mapping; SimpleNamespace is a
faithful enough stand-in to test the accessors without a Streamlit runtime.
"""

import types

import pandas as pd

from st_aggrid.result import AgGridResult


def _component_result(**kwargs):
    base = {"grid_state": None, "api_response": None, "notes": None}
    base.update(kwargs)
    return types.SimpleNamespace(**base)


def test_missing_component_result_yields_empty_accessors():
    result = AgGridResult(component_result=None, original_data=None)
    assert result.selected_rows is None
    assert result.column_state is None
    assert result.filter_model is None
    assert result.event_name is None
    assert result.get("anything") is None


def test_data_returns_the_original_frame():
    df = pd.DataFrame({"a": [1, 2]})
    result = AgGridResult(component_result=_component_result(), original_data=df)
    pd.testing.assert_frame_equal(result.data, df)


def test_selected_rows_become_a_dataframe_without_internal_columns():
    component = _component_result(
        grid_state={
            "selectedRows": [
                {"a": 1, "::auto_unique_id::": "0"},
                {"a": 2, "::auto_unique_id::": "1"},
            ]
        }
    )
    result = AgGridResult(component_result=component, original_data=None)
    assert list(result.selected_rows.columns) == ["a"]
    assert result.selected_rows["a"].tolist() == [1, 2]


def test_empty_selection_is_none():
    component = _component_result(grid_state={"selectedRows": []})
    result = AgGridResult(component_result=component, original_data=None)
    assert result.selected_rows is None


def test_named_state_accessors():
    component = _component_result(
        grid_state={
            "columnState": [{"colId": "a"}],
            "filterModel": {"a": {"type": "equals"}},
            "sortModel": [{"colId": "a", "sort": "asc"}],
            "state": {"rowGroup": {"groupColIds": ["a"]}},
            "displayedRowCount": 7,
            "eventName": "filterChanged",
            "eventData": {"source": "ui"},
        }
    )
    result = AgGridResult(component_result=component, original_data=None)
    assert result.column_state == [{"colId": "a"}]
    assert result.filter_model == {"a": {"type": "equals"}}
    assert result.sort_model == [{"colId": "a", "sort": "asc"}]
    assert result.grid_state == {"rowGroup": {"groupColIds": ["a"]}}
    assert result.displayed_row_count == 7
    assert result.event_name == "filterChanged"
    assert result.event_data == {"source": "ui"}


def test_api_response_and_notes_pass_through():
    component = _component_result(
        api_response={"call_id": "x", "value": 1},
        notes={"token": 3, "notes": {"0": {"a": "hi"}}},
    )
    result = AgGridResult(component_result=component, original_data=None)
    assert result.api_response == {"call_id": "x", "value": 1}
    assert result.notes["token"] == 3


def test_get_and_getitem():
    component = _component_result(grid_state={"displayedRowCount": 3})
    result = AgGridResult(component_result=component, original_data=None)
    assert result.get("displayedRowCount") == 3
    assert result.get("missing", "fallback") == "fallback"
    assert result["displayedRowCount"] == 3

    try:
        result["missing"]
    except KeyError:
        pass
    else:
        raise AssertionError("expected KeyError for a missing key")
```

- [ ] **Step 7: Write the data/grid-options parsing tests**

Create `test/unit/test_aggrid_utils.py`:

```python
"""_parse_data_and_grid_options turns user input into the component payload."""

import json

import pandas as pd

from st_aggrid.aggrid_utils import _parse_data_and_grid_options
from st_aggrid.shared import JsCode


def _parse(data, grid_options=None, **kwargs):
    kwargs.setdefault("default_column_parameters", {})
    kwargs.setdefault("unsafe_allow_jscode", False)
    return _parse_data_and_grid_options(
        data,
        grid_options,
        kwargs["default_column_parameters"],
        kwargs["unsafe_allow_jscode"],
        use_json_serialization=kwargs.get("use_json_serialization", "auto"),
    )


def test_grid_options_are_derived_from_the_dataframe():
    df = pd.DataFrame({"names": ["a"], "ages": [1]})
    _data, grid_options, _types = _parse(df)
    fields = [c["field"] for c in grid_options["columnDefs"]]
    assert fields == ["names", "ages"]


def test_an_auto_row_id_column_is_added_when_get_row_id_is_absent():
    df = pd.DataFrame({"a": [1, 2, 3]})
    data, _grid_options, _types = _parse(df)
    assert data["::auto_unique_id::"].tolist() == ["0", "1", "2"]


def test_a_user_supplied_get_row_id_suppresses_the_auto_column():
    df = pd.DataFrame({"a": [1, 2]})
    data, _grid_options, _types = _parse(df, {"getRowId": "someJs"})
    assert "::auto_unique_id::" not in data.columns


def test_a_json_string_is_parsed_into_a_dataframe():
    payload = json.dumps([{"a": 1, "b": "x"}, {"a": 2, "b": "y"}])
    data, _grid_options, _types = _parse(payload)
    assert list(data["a"]) == [1, 2]


def test_grid_options_may_be_a_json_string():
    df = pd.DataFrame({"a": [1]})
    _data, grid_options, _types = _parse(
        df, json.dumps({"columnDefs": [{"field": "a", "headerName": "A"}]})
    )
    assert grid_options["columnDefs"][0]["headerName"] == "A"


def test_jscode_is_converted_only_when_unsafe_jscode_is_allowed():
    df = pd.DataFrame({"a": [1]})
    code = JsCode("function(){ return 1 }")

    _d, converted, _t = _parse(
        df, {"getRowId": code}, unsafe_allow_jscode=True
    )
    assert converted["getRowId"] == code.js_code

    _d, untouched, _t = _parse(
        df, {"getRowId": JsCode("function(){ return 1 }")}, unsafe_allow_jscode=False
    )
    assert isinstance(untouched["getRowId"], JsCode)


def test_dict_cells_fall_back_to_json_row_data():
    # Arrow unifies dict columns into one struct type, which flattens
    # per-row keys. JSON serialization keeps each row's shape.
    df = pd.DataFrame({"payload": [{"a": 1}, {"b": 2}]})
    data, grid_options, _types = _parse(df)
    assert data is None
    assert isinstance(grid_options["rowData"], str)
    assert json.loads(grid_options["rowData"])[1]["payload"] == {"b": 2}


def test_column_types_are_reported():
    df = pd.DataFrame({"a": [1], "b": ["x"]})
    _data, _grid_options, column_types = _parse(df)
    assert column_types["a"].kind == "i"
    assert column_types["b"].kind == "O"
```

- [ ] **Step 8: Write the shared-helpers tests**

Create `test/unit/test_shared.py`:

```python
"""JsCode, walk_grid_options and StAggridTheme."""

from st_aggrid.shared import (
    AgGridTheme,
    JsCode,
    StAggridTheme,
    walk_grid_options,
)


def test_jscode_is_wrapped_in_placeholders_and_flattened():
    code = JsCode(
        """
        function(params) {
            return params.value
        }
        """
    ).js_code
    assert code.startswith("::JSCODE::")
    assert code.endswith("::JSCODE::")
    assert "\n" not in code
    assert "return params.value" in code


def test_jscode_strips_comments():
    code = JsCode(
        """
        function(params) {
            // never send this to the browser
            return 1
        }
        """
    ).js_code
    assert "//" not in code
    assert "never send this" not in code


def test_jscode_strips_block_comments():
    code = JsCode("function(){ /* gone */ return 1 }").js_code
    assert "gone" not in code


def test_walk_grid_options_applies_func_to_every_leaf():
    options = {
        "a": 1,
        "nested": {"b": 2},
        "list": [{"c": 3}],
    }
    walk_grid_options(options, lambda v: v * 10 if isinstance(v, int) else v)
    assert options["a"] == 10
    assert options["nested"]["b"] == 20
    assert options["list"][0]["c"] == 30


def test_theme_enum_membership():
    assert "streamlit" in AgGridTheme
    assert "not-a-theme" not in AgGridTheme


def test_custom_theme_builds_a_serializable_dict():
    theme = (
        StAggridTheme(base="balham")
        .with_params(accentColor="#ff0000", rowHeight=30)
        .with_parts("colorSchemeDark", "iconSetMaterial")
    )
    assert theme["themeName"] == "custom"
    assert theme["base"] == "balham"
    assert theme["params"] == {"accentColor": "#ff0000", "rowHeight": 30}
    assert theme["parts"] == ["colorSchemeDark", "iconSetMaterial"]


def test_theme_parts_are_deduplicated_in_order():
    theme = StAggridTheme(base="alpine").with_parts("a", "b").with_parts("b", "c")
    assert theme["parts"] == ["a", "b", "c"]


def test_theme_without_a_base_has_no_theme_name():
    theme = StAggridTheme()
    assert "themeName" not in theme
    assert theme["params"] == {}
    assert theme["parts"] == []
```

- [ ] **Step 9: Write the GridOptionsBuilder tests**

Create `test/unit/test_grid_options_builder.py`:

```python
"""GridOptionsBuilder derives colDefs from a DataFrame and merges overrides."""

import pandas as pd

from st_aggrid.grid_options_builder import GridOptionsBuilder


def test_from_dataframe_creates_one_col_def_per_column():
    df = pd.DataFrame({"names": ["a"], "ages": [1]})
    options = GridOptionsBuilder.from_dataframe(df).build()
    assert [c["field"] for c in options["columnDefs"]] == ["names", "ages"]
    assert [c["headerName"] for c in options["columnDefs"]] == ["names", "ages"]


def test_numeric_columns_get_numeric_types():
    df = pd.DataFrame({"ages": [1], "names": ["a"]})
    options = GridOptionsBuilder.from_dataframe(df).build()
    by_field = {c["field"]: c for c in options["columnDefs"]}
    assert by_field["ages"]["type"] == ["numericColumn", "numberColumnFilter"]
    assert by_field["names"]["type"] == []


def test_datetime_columns_get_date_types():
    df = pd.DataFrame({"when": pd.to_datetime(["2026-01-01"])})
    options = GridOptionsBuilder.from_dataframe(df).build()
    assert options["columnDefs"][0]["type"] == [
        "dateColumnFilter",
        "shortDateTimeFormat",
    ]


def test_from_dataframe_enables_fit_grid_width():
    df = pd.DataFrame({"a": [1]})
    options = GridOptionsBuilder.from_dataframe(df).build()
    assert options["autoSizeStrategy"] == {"type": "fitGridWidth"}


def test_dotted_column_names_suppress_field_dot_notation():
    df = pd.DataFrame({"a.b": [1]})
    options = GridOptionsBuilder.from_dataframe(df).build()
    assert options["suppressFieldDotNotation"] is True


def test_default_column_parameters_are_routed_to_default_col_def():
    df = pd.DataFrame({"a": [1]})
    options = GridOptionsBuilder.from_dataframe(df, filter=True).build()
    assert options["defaultColDef"]["filter"] is True


def test_configure_column_merges_into_an_existing_col_def():
    df = pd.DataFrame({"a": [1]})
    gb = GridOptionsBuilder.from_dataframe(df)
    gb.configure_column("a", header_name="Alpha", width=120)
    options = gb.build()
    assert options["columnDefs"][0]["headerName"] == "Alpha"
    assert options["columnDefs"][0]["width"] == 120


def test_configure_columns_batches_overrides():
    df = pd.DataFrame({"a": [1], "b": [2]})
    gb = GridOptionsBuilder.from_dataframe(df)
    gb.configure_columns(["a", "b"], resizable=False)
    options = gb.build()
    assert all(c["resizable"] is False for c in options["columnDefs"])


def test_configure_auto_height_sets_dom_layout():
    df = pd.DataFrame({"a": [1]})
    gb = GridOptionsBuilder.from_dataframe(df)
    gb.configure_auto_height(True)
    assert gb.build()["domLayout"] == "autoHeight"


def test_build_turns_col_defs_into_a_list():
    df = pd.DataFrame({"a": [1]})
    options = GridOptionsBuilder.from_dataframe(df).build()
    assert isinstance(options["columnDefs"], list)
```

- [ ] **Step 10: Run the whole fast suite**

```bash
cd /home/homelab/repo/streamlit-aggrid
uv run pytest -m "not e2e" -v
```

Expected: everything passes and the run finishes in a couple of seconds. If any assertion above turns out to encode a wrong expectation about existing behaviour, fix the **test** to match the code — this task adds coverage, it does not change behaviour.

- [ ] **Step 11: Confirm the e2e selection is unchanged**

```bash
cd /home/homelab/repo/streamlit-aggrid
uv run pytest -m "e2e" --collect-only -q 2>&1 | tail -5
```

Expected: every `test/test_grid_*.py` test is collected and nothing from `test/unit/` is.

- [ ] **Step 12: Document the fast loop**

In `CLAUDE.md`, replace the "# Tests (Playwright e2e)" block under "## Build & Dev" with:

```
# Tests
pytest -m "not e2e"   # fast: pure-Python unit suite in test/unit (seconds)
pytest                # everything except the slow 1M-row performance suite
pytest -m slow        # the performance suite on its own
```

and under "## Conventions", replace the Tests line with:

```
- Tests: `test/unit/` is pure Python (no browser, no Streamlit runtime).
  Everything else is Playwright e2e — a `test_*.py` driving a standalone
  Streamlit app of the same name — and is auto-marked `e2e` by
  `test/conftest.py`.
```

- [ ] **Step 13: Commit**

```bash
cd /home/homelab/repo/streamlit-aggrid
git add pyproject.toml test/conftest.py test/unit CLAUDE.md
git add -u test/
git commit -m "Add a browser-free unit test layer selectable with -m 'not e2e'

Every test but one drove a real browser, so Python-side logic had no fast
feedback loop. Auto-mark everything outside test/unit as e2e and cover
AgGridResult, the data/gridOptions parser, JsCode, walk_grid_options,
StAggridTheme and GridOptionsBuilder."
```

---

## Verification

After all four tasks:

```bash
cd /home/homelab/repo/streamlit-aggrid
uv run pytest -m "not e2e" -v     # fast suite, seconds
uv run pytest -v                  # full suite except the slow performance run
git log --oneline upstream-parity ^v36.0
```

Expected: the fast suite passes; the full suite passes; four commits on the branch.

## Out of scope

Deliberately excluded, and why:

- **Removing `st_aggrid/frontend/build/` from git.** The project is installed straight from git, and no build step runs at install time, so the built bundle has to be committed.
- **Source maps.** Genuinely useful, but with `build/` committed they would add tens of megabytes of blobs per rebuild.
- **`isolate_styles` as a parameter.** Needs an audit of AG-Grid Enterprise popups (context menus, tool panels) under a shadow root with an explicit `popupParent` before the default can be trusted.
- **`should_grid_return` / JsCode collectors, `parse_multi_index`, upstream's `styles.py` helpers.** Worthwhile, independently scoped, and not part of items 1/3/4/5.
