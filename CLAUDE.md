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
├── AgGrid.py                # Main AgGrid() function + call_grid_api()
├── component.py             # CCv2 component registration (loads built JS/CSS)
├── result.py                # AgGridResult wrapper
├── grid_options_builder.py  # GridOptionsBuilder helper
├── shared.py                # JsCode, StAggridTheme, AgGridTheme, walk_gridOptions
├── aggrid_utils.py          # Data/gridOptions parsing
└── frontend/                # TypeScript/React frontend (Vite)
    ├── src/
    │   ├── index.tsx                 # CCv2 entry point
    │   ├── AgGridComponent.tsx       # Main React component
    │   ├── ThemeParser.tsx           # Theme handling
    │   ├── customColumns.tsx         # Custom column renderers
    │   ├── utils.ts                  # Frontend utilities
    │   ├── utils/parsers.ts          # Data parsing
    │   ├── utils/gridUtils.ts        # Grid helpers
    │   ├── hooks/useAutoCollect.ts   # Auto-collect hook
    │   ├── hooks/useExplicitApiCall.ts
    │   ├── components/GridToolBar.tsx
    │   ├── components/ErrorBoundary.tsx
    │   └── types/AgGridTypes.ts
    ├── vite.config.ts
    └── package.json
test/                        # Playwright e2e tests
```

## AG-Grid Version

**Current: 34.3.1**

AG-Grid packages in `st_aggrid/frontend/package.json`:
- `ag-grid-community` — `^34.3.1`
- `ag-grid-enterprise` — `34.3.1`
- `ag-grid-react` — `34.3.1`
- `ag-charts-enterprise` — `^12.3.1`

When updating AG-Grid:
1. Update all `ag-grid-*` packages in `st_aggrid/frontend/package.json`
2. Check if `ag-charts-enterprise` needs a compatible version bump
3. Review AG-Grid changelog for breaking changes (API renames, removed options, theme changes)
4. Rebuild frontend: `cd st_aggrid/frontend && yarn install && yarn build`
5. Run e2e tests: `pytest test/`
6. Update version references in `README.md`

## Build & Dev

```bash
# Frontend
cd st_aggrid/frontend
yarn install
yarn build          # outputs to st_aggrid/frontend/build/
yarn dev            # dev server on port 3001

# Full build (frontend + Python wheel)
yarn build          # root package.json — builds all workspaces then poetry build

# Tests (Playwright e2e)
pytest test/

# Python install (dev)
pip install -e .
```

Package manager: **yarn 4.1.0** (root), npm/yarn for frontend workspace.
Build tool: **Vite** (lib mode, single JS bundle + CSS).
Python build: **Poetry** (`poetry-core`).

## Key Design Decisions

- **CCv2 no-iframe**: Component registered via `st.components.v2.component()` in `component.py`. JS and CSS are read from the build directory and inlined.
- **CSS minification disabled**: `cssMinify: false` in vite.config.ts — Streamlit CCv2 inline CSS detection requires newlines.
- **Single JS bundle**: `inlineDynamicImports: true` — everything in one file for CCv2.
- **Arrow data transfer**: DataFrames sent as Arrow via CCv2, parsed in `utils/parsers.ts`.
- **Auto-collect pattern**: `collect` param specifies AG-Grid API methods to call after events; results returned via `AgGridResult`.
- **Explicit API calls**: `call_grid_api()` writes to `session_state`, executed on next rerun.

## Conventions

- Python: no formatter enforced, but `ruff` is in dev dependencies.
- TypeScript: standard React patterns, functional components with hooks.
- Commits: imperative mood, descriptive of what changed.
- Tests: Playwright-based e2e tests in `test/`, test apps are standalone Streamlit scripts.