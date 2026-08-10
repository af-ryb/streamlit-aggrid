# CLAUDE.md — streamlit-aggrid

## Project

Streamlit AG-Grid component v2, built on **Custom Components v2** (CCv2, no iframe).
Fork of [PablocFonseca/streamlit-aggrid](https://github.com/PablocFonseca/streamlit-aggrid).
Active branch: `v2_component`.

Read-only grid — no cell editing. Focus: display, selection, filtering, sorting, export.

## Architecture

```
st_aggrid/                   # Python package
├── __init__.py              # Public API exports
├── aggrid.py                # Main AgGrid() function + call_grid_api()
├── component.py             # CCv2 component registration (declares JS/CSS globs, lazy)
├── pyproject.toml           # In-wheel component manifest (asset_dir, name, version)
├── result.py                # AgGridResult wrapper
├── grid_options_builder.py  # GridOptionsBuilder helper
├── shared.py                # JsCode, StAggridTheme, AgGridTheme, walk_grid_options
├── aggrid_utils.py          # Data/gridOptions parsing
├── ratio.py                 # Validation for stRatio column declarations
└── frontend/                # TypeScript/React frontend (Vite)
    ├── src/
    │   ├── index.tsx                 # CCv2 entry point
    │   ├── AgGridComponent.tsx       # Main React component
    │   ├── ThemeParser.tsx           # Theme handling
    │   ├── customColumns.tsx         # Custom column renderers
    │   ├── utils.ts                  # Frontend utilities
    │   ├── utils/parsers.ts          # Data parsing
    │   ├── utils/gridUtils.ts        # Grid helpers
    │   ├── aggFuncs/stRatio.ts        # Built-in ratio aggregator + comparator
    │   ├── hooks/useAutoCollect.ts   # Auto-collect hook
    │   ├── hooks/useExplicitApiCall.ts
    │   ├── components/GridToolBar.tsx
    │   ├── components/ErrorBoundary.tsx
    │   └── types/AgGridTypes.ts
    ├── vite.config.ts
    └── package.json
test/                        # test/unit is pure Python; everything else is Playwright e2e
```

## AG-Grid Version

**Current: 36.0.0**

AG-Grid packages in `st_aggrid/frontend/package.json`:
- `ag-grid-community` — `^36.0.0`
- `ag-grid-enterprise` — `36.0.0`
- `ag-grid-react` — `36.0.0`
- `ag-charts-enterprise` — `^14.0.0`

Note: `ag-grid-enterprise` hard-pins `ag-grid-community` at the exact same version,
and depends on `ag-charts-*` at an exact version too — bump all `ag-grid-*` in
lockstep and keep `ag-charts-enterprise` aligned (36.0 requires `ag-charts` 14.0.x),
or the build hits a duplicate-`ag-charts-types` type mismatch.

When updating AG-Grid:
1. Update all `ag-grid-*` packages in `st_aggrid/frontend/package.json`
2. Check if `ag-charts-enterprise` needs a compatible version bump
3. Review AG-Grid changelog for breaking changes (API renames, removed options, theme changes)
4. Rebuild frontend: `cd st_aggrid/frontend && corepack yarn install && corepack yarn build`
   (filenames are content-hashed — a rebuild changes them, so `git status` shows
   a delete + an add for `st_aggrid/frontend/build/*`, not a modify)
5. Run e2e tests: `pytest -m e2e`
6. Update version references in `README.md`

## Build & Dev

```bash
# Frontend — `yarn` is NOT on PATH; invoke via corepack (Yarn 4 Berry).
cd st_aggrid/frontend
corepack yarn install
corepack yarn build   # rm -rf build && tsc && vite build → st_aggrid/frontend/build/
corepack yarn dev     # dev server on port 3001

# Full build (frontend + Python wheel)
corepack yarn build   # root package.json — builds all workspaces then uv build

# Tests
pytest -m "not e2e"   # fast: pure-Python unit suite in test/unit (seconds)
pytest                # everything except the slow 1M-row performance suite
pytest -m slow        # the performance suite on its own

# Python env (dev)
uv sync        # creates .venv, installs deps + dev group (editable)
uv run pytest  # run tests inside the uv-managed env
```

Package manager: **Yarn 4.1.0 (Berry)** via **corepack** — bare `yarn` is not on PATH, so run `corepack yarn …` (set `COREPACK_ENABLE_DOWNLOAD_PROMPT=0` to skip the prompt). The pinned release is committed at `.yarn/releases/yarn-4.1.0.cjs`.
Build tool: **Vite** (lib mode, single JS bundle + CSS).
Python build: **hatchling** (via `uv build`).

## Key Design Decisions

- **CCv2 no-iframe**: Component registered lazily via `st.components.v2.component()` in `component.py` (see Packaging & asset delivery). JS and CSS are served from `frontend/build` as static assets, not inlined.
- **CSS minification enabled**: assets are served by path (glob-matched filename), not read into an inline string, so `looks_like_inline_content`'s glob-character heuristic never sees the minified CSS — `cssMinify: false` is no longer needed.
- **Single JS bundle**: `inlineDynamicImports: true` — everything in one file for CCv2.
- **Arrow data transfer**: DataFrames sent as Arrow via CCv2, parsed in `utils/parsers.ts`.
- **Auto-collect pattern**: `collect` param specifies AG-Grid API methods to call after events; results returned via `AgGridResult`.
- **Explicit API calls**: `call_grid_api()` writes to `session_state`, executed on next rerun.
- **Built-in `stRatio` aggregator**: `Σnum/Σden` rollups declared as data in
  `colDef.context["stRatio"]`, registered from `parseGridOptions` so both the
  mount and the live-update paths get it. Correct under row grouping and pivot;
  the value object implements AG-Grid 36's `IAggFuncResult` (`toNumber`, not
  `valueOf` — `valueOf` leaves a column containing a null unsorted). Python
  validates the declaration against the DataFrame, never against `columnDefs`.

## Packaging & asset delivery

- Distribution name is **`st-aggrid`**; the importable package is `st_aggrid`.
  These must stay aligned: Streamlit's Components v2 manifest scanner derives
  the package name from the distribution name, so renaming either one alone
  breaks asset discovery.
- The distribution was renamed `streamlit-aggrid` → `st-aggrid` in 2.2.0. `pip
  install` does not uninstall the old distribution, and its dist-info RECORD
  still claims `st_aggrid/*` — running `pip uninstall streamlit-aggrid` after
  installing `st-aggrid` deletes files the new install owns. Existing users
  must `pip uninstall -y streamlit-aggrid` *before* upgrading (see README).
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

## Conventions

- Python: no formatter enforced, but `ruff` is in dev dependencies.
- TypeScript: standard React patterns, functional components with hooks.
- Commits: imperative mood, descriptive of what changed.
- Tests: `test/unit/` is pure Python (no browser, no Streamlit runtime).
  Everything else is Playwright e2e — a `test_*.py` driving a standalone
  Streamlit app of the same name — and is auto-marked `e2e` by
  `test/conftest.py`.
- Ratio tests never hand-type an expected number: `test/ratio_fixture.py` owns
  the data and the arithmetic, and declares the nodes it cannot discriminate.