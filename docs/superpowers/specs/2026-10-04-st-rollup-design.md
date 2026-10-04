# `stRollup` — a built-in aggregator that shows server-computed group totals — Design

**Status:** implemented on feature/st-rollup (2.6.0)
**Branch:** `feature/st-rollup` (off `main` at `33c3e27`)
**Date:** 2026-10-04
**Release:** 2.6.0 (additive public API)
**Consumer task:** stream 9, slice "9.5 — `stRollup`" as filed in `dash-ai-TASKS.md`
on 2026-10-04; blocks the pivot variant for distinct-count sources
(`designs/dash-ai-PIVOT_VARIANT_DESIGN.md`, "Серверные итоги для
distinct-источников" and "План работ — пилот `overview_dau`", item 6)

All `path:line` references are to this repository at `33c3e27` unless the path
starts with `web_app/`, which is the consumer (`hitapps_analytics`). The
consumer's side (the `CUBE` query, the split of its answer, the pivot variant)
has its own plan in that repository; this document fixes only the contract it
is written against (see "Consumer contract").

---

## Problem

A group row's value in AG-Grid is computed from its children. For a distinct
count (`dau`, `payers`) that is wrong: the distinct users of a group are not
derivable from the distinct users of its children. Measured on 2026-10-04
(`dau_ads`, 30 days × `app_version`): the sum of leaves over-states `dau` ×3.23
on a version row and ×5.70 on the grand total.

The exact totals are computed by BigQuery (`GROUP BY CUBE` over the loaded
dimension slots), which returns one row per grouping set. The grid must
**show** them, not compute them: each group row looks up its own total in a
table the server sent, and a group with no entry in that table shows an empty
cell — never the sum of its children, because a silently substituted sum is
exactly the error this aggregator exists to prevent.

## Design decisions

Each was put to the owner and chosen on 2026-10-04.

| # | Question | Decision | Rejected |
|---|---|---|---|
| 1 | How the totals table travels | A second DataFrame, through the **same transport as `rowData`** (Arrow, or JSON when the leaves go JSON); parsed by the same frontend code; its index injected into `gridOptions.context` | A JSON table with keys pre-serialised by the caller: the caller cannot reproduce how Streamlit's Arrow-JS renders a `date32` value, and a mismatch is a silent miss |
| 2 | Grid filters vs server totals | A group whose subtree lost **any** leaf to a filter shows an empty cell; untouched groups keep their exact total | Blank all totals while any filter is active (loses the common case); always show the server total (silently disagrees with visible rows); leave it to the consumer |
| 3 | Python API | A dedicated `AgGrid(..., rollup={...})` parameter | The table inside `grid_options["context"]`: makes `grid_options` a JSON/DataFrame hybrid for no saving — the consumer's `render_managed_grid` already forwards `**agg_kwargs` to `AgGrid` (`web_app/src/bi_core/charts/grid_state.py:563`) |
| 4 | Reporting a miss that indicates a bug | Empty cell + one `console.warn` per totals table, always on (not only under `debug`) | `debug`-only; a visible marker in the cell |

Saved views were checked and do not interact with the table: a saved view
persists `GridLayoutState` (`web_app/src/bi_core/charts/registry.py:235`) —
column state, AG-Grid `GridState`, colour-scale state — never `grid_options`,
and `api.getState()` does not include `context`. Every consumer grid locks its
aggregation with `allowedAggFuncs=[m.grid_agg()]`, so a saved `sum` cannot
replace `stRollup` through the panel.

## Scope

In:
- the `stRollup` aggregator, registered on every grid like `stRatio`;
- the `rollup` parameter, its transport, and its validation;
- the grid-filter rule (decision 2) and the miss warning (decision 4);
- re-aggregation when the totals table changes without the leaves changing.

Out:
- `pivotMode=True` (the aggregator returns `null` there; the consumer's pivot
  variant is row-grouping only, `pivotMode=False`);
- tree data (`treeData`/`getDataPath`);
- server-side or infinite row models;
- any builder helper (`GridOptionsBuilder.configure_rollup`) — not needed
  with decision 3;
- computing anything from the totals (ratios on total rows are already
  materialised per row by the consumer and arrive as ordinary metric columns
  of the totals table).

## What AG-Grid 36.1.0 does with group keys (measured against `main.cjs.js`)

The key matching below is built on these facts; each is cited so a version
bump can re-check them.

- **A group node's key is `getKeyForNode`'s result**
  (`ag-grid-community/dist/package/main.cjs.js:36800`): the column's
  `keyCreator(params)` when defined, else the value unchanged if it is a
  string or `null`/`undefined`, else `String(value)`. The number `1` groups
  under `"1"`.
- **`null`, `undefined` and `""` all group under the key `""`** when
  `groupAllowUnbalanced` is off (`ag-grid-enterprise/.../main.cjs.js:37223–37229`,
  `createGroupForEmpty`). A real NULL `app_version` is therefore the group
  `""` — distinct from an absent level (whose field is not in the ancestry at
  all), but not distinguishable from an empty string. That is the grid's
  behaviour, and the key normalisation reproduces it rather than fighting it.
- With `groupAllowUnbalanced` on, null-keyed leaves skip that level and no
  group node with key `""` exists for it; nothing to match, nothing to break.
- **Aggregation runs after the filter stage and before `filter_aggregates`.**
  `childrenAfterFilter` is current when an aggFunc is called;
  `allChildrenCount` is **not** — it is set in `FilterAggregatesStage`
  (`ag-grid-enterprise/.../main.cjs.js:31315`), after aggregation, so during
  an aggFunc call it holds the previous pass's count. The filter rule counts
  leaves itself.
- AG-Grid aggregates only filtered children unless `groupAggFiltering` or
  `suppressAggFilteredOnly` is set (`main.cjs.js:31049`, `filteredOnly`).

## Public contract

### Python

```python
AgGrid(
    leaves_df,
    grid_options=grid_options,
    rollup={
        "data": totals_df,                               # required
        "dimensions": ["event_date", "app_version"],      # required, non-empty
        "flags": {"app_version": "_grouping_app_version"},  # optional
    },
)
```

- `data`: a pandas (or polars, converted the way `data` is) DataFrame holding
  **the whole `CUBE` answer** — one row per grouping set and value
  combination, *including the full-grain set* (all flags 0). The deepest group
  of a grouping over every dimension is keyed by all of them, so without the
  full-grain rows its lookup would miss. Columns: every dimension, every flag,
  and the metric columns `stRollup` columns read.
- `dimensions`: the fields the totals are keyed by. Names are row-data
  fields — the same names the grid groups by.
- `flags`: dimension → flag column. Default for a dimension not listed:
  `_grouping_<dimension>`. Flag semantics are BigQuery's `GROUPING()`:
  **1 — the level is absent (rolled up) in this row; 0 — present**, even when
  its value is NULL. The row whose flags are all 1 is the grand total. The
  aggregator reads the flags, never NULL, to decide what is absent.

### Column declaration

```python
gb.configure_column("dau", aggFunc="stRollup", allowedAggFuncs=["stRollup"])
gb.configure_column("users", aggFunc="stRollup",
                    context={"stRollup": {"field": "dau_exact"}})
```

`context["stRollup"]` is optional. `field` names the totals-table column to
read; it defaults to the colDef's `field`. Any value column may use
`stRollup`, including a ratio column whose total-row value the server already
computed.

### Semantics, per row

| Row | Value |
|---|---|
| leaf | the cell's own value (AG-Grid never calls an aggFunc for a leaf) |
| group or grand total, key found, no leaf of its subtree filtered out | the totals table's value |
| key found, but a filter removed at least one leaf of its subtree | empty (`null`) — see decision 2 |
| key not found | empty (`null`); warns once if the miss indicates a bug (below) |
| `pivotMode=True` | empty (`null`) |
| no totals table on this grid (e.g. `stRollup` arrived from restored state) | empty (`null`) — **not** a sum, unlike `stRatio`'s fallback |

The returned value is a plain `number | null` (non-finite → `null`), so a
`valueFormatter` written for a number keeps working.

## Python

### `st_aggrid/rollup.py` (new) — validation

`validate_rollup(rollup, grid_options, data_dtypes)`, called from `AgGrid`
next to `validate_ratio_columns` (`st_aggrid/aggrid.py:446`). Walks colDefs
with `_coldefs.iter_column_defs` and names columns with `column_label`, like
`ratio.py`. Raises `ValueError` for:

1. A colDef with `aggFunc == "stRollup"` and `rollup is None`; or `rollup`
   given and no colDef declares `stRollup`.
2. `rollup` not a dict; `data` not a DataFrame; `dimensions` not a non-empty
   list of non-empty strings, or with duplicates; `flags` not a
   `dict[str, str]`, or naming a field that is not a dimension.
3. A dimension missing from the totals table, or (when the leaves' dtypes are
   known) from the row data. A flag column missing from the totals table, or
   holding anything but 0/1 (nullable integer NA counts as invalid).
4. A `stRollup` column whose `field` (resolved as above) is not a column of
   the totals table.
5. A dimension whose *serialisation class* differs between the leaves and the
   totals table. The class is "number" for any numeric non-bool column (int or
   float, nullable or not: they render to the same AG-Grid key), "bool" for
   booleans, and otherwise `pd.api.types.infer_dtype` (`"date"`, `"string"`,
   `"datetime"`, ...). Dtypes are not compared: on pandas 2 a `datetime.date`
   column and the ISO strings `prepare_frame` makes from `datetime64` are both
   `object`. Differing classes serialise differently, the keys never meet, and
   every lookup misses — silently, were it not for this check. The leaves'
   classes are computed after `prepare_frame`, before any JSON serialisation.
6. Two totals rows with the same key after normalisation (present dimensions
   only, with `None`/NaN/`""` collapsed to `""` exactly as the grid does).
   This catches the NULL-vs-empty-string collision and any duplicated
   grouping set.

When the grid has no DataFrame (`data=None`, rows in `grid_options["rowData"]`)
the checks against the leaves (3's row-data half, and 5) are skipped, as
`ratio.py` skips its field check; everything else still runs.

Rule 6 normalises in Python with `str()` for non-string values. That is the
grid's rule for numbers and strings; for the value types where Python's and
JavaScript's `String` differ (floats like `1.0`, dates) a Python-side
duplicate check can only under-report, never false-alarm, which is acceptable
for a guard. The frontend key, not this check, is authoritative.

### Transport — `st_aggrid/aggrid_utils.py` and `aggrid.py`

- The per-frame preparation `_parse_data_and_grid_options` applies to `data`
  today — polars → pandas, `datetime64` → `isoformat()` strings
  (`st_aggrid/aggrid_utils.py:85–89`) — moves into one function, applied to
  both frames. The totals frame is prepared **on a copy**: today's conversion
  assigns into the caller's frame, and the caller's totals must not change.
- The totals table follows the leaves' transport. If the leaves go as Arrow,
  `component_data["rollup_data"]` is the prepared DataFrame. If the leaves are
  JSON-serialised (`use_json_serialization=True`, or `"auto"` deciding so),
  the totals are serialised by the same `to_json(orient="records",
  default_handler=str)` call. A `date32` value renders differently through
  the two paths, so mixing them would make every date key miss. A grid with
  no DataFrame (`data=None`, rows already in `grid_options["rowData"]`) has
  JSON leaves, so its totals go JSON as well.
- `component_data["rollup_meta"] = {"dimensions": [...], "flags": {dim: col}}`
  with defaults filled in, so the frontend never re-derives a default.
- No `::auto_unique_id::` on the totals: they are not grid rows.
- Absent `rollup`: both keys are `None`; nothing else changes.

## Frontend

### `aggFuncs/rollupKey.ts` (new, pure, imports nothing)

- `toGroupKey(value, keyCreator?)`: reproduces `getKeyForNode` followed by
  the grid's empty-group rule — `keyCreator` result if given, else a string
  as is, else `String(value)`; `null`/`undefined`/`""` → `""`.
- `canonicalKey(pairs: Record<string, string>)`: entries sorted by field
  name, `JSON.stringify`'d. Order-independence is what lets a regrouped panel
  (levels reordered or removed) find its totals without a re-query.
- `nodeKey(node)`: walks from the node to the root. For each group node
  (`level >= 0`), field = `rowGroupColumn.getColDef().field ?? rowGroupColumn.getColId()`,
  key = `node.key ?? ""`. The root yields `{}`. Typed structurally (a minimal
  node interface), so the module stays import-free and checkable in Node.

### `aggFuncs/stRollup.ts` (new)

- `ST_ROLLUP = "stRollup"`; `ST_ROLLUP_INDEX` — the `context` key the index
  lives under (`"stRollup"`).
- `buildRollupIndex(rows, meta, columnDefs, context)` →
  `{ map: Map<string, row>, dimensions: Set<string>, sampleKeys: string[] }`.
- The index reaches the aggregator through one mutable holder per mount,
  `{ index, debug, warned, notedPivot }`, injected into `context` — the same
  pattern as the colour-scale override `Map`, so swapping the table never
  needs `setGridOption("context")`.
  For each row: the present dimensions (flag 0) are converted with
  `toGroupKey`, passing the `keyCreator` of the colDef whose `field` is that
  dimension (called with `{value, colDef, data: row, context}`; a
  `keyCreator` that needs a node is not supported and is documented as such).
- `stRollupAggFunc(params)`:
  1. `params.api.isPivotMode()` → `null` (one `debug` log per grid).
  2. No holder or no index in `params.context` (the grid got no `rollup`) →
     `null`, silently: there is no holder to carry a `debug` flag.
  3. Filter rule: when `!groupAggFiltering && !suppressAggFilteredOnly`,
     count the node's leaves reachable through `childrenAfterFilter`; fewer
     than `allLeafChildren.length` → `null`. Cost is the subtree size per
     group, `O(rows × depth)` per pass.
  4. Look up `canonicalKey(nodeKey(params.rowNode))`. Hit → the row's
     `field` value, non-finite → `null`.
  5. Miss → `null`. When every field of the node's key is in
     `index.dimensions`, `CUBE` guarantees the entry exists, so the miss is a
     desync (serialisation, a stale table, flags lost upstream):
     `console.warn` once per totals table (the holder's `warned`, reset when
     the table's content changes) with the node's key and up to three
     `sampleKeys`. A miss with a field outside `dimensions` (the user grouped
     by a column the server did not roll up) is silent.
- `registerStRollup(gridOptions, debug)` → `registerAggFunc` (`foldSums.ts:146`),
  which attaches `stAggComparator` (nulls last both ways) and lets a
  caller-supplied `aggFuncs.stRollup` win.

### `utils/parsers.ts`

- `parseData`'s Arrow / JSON-string / array branches are factored into one
  function taking the raw payload, used for `rowData` and `rollup_data` alike.
  Same code, same JS values — the premise of decision 1.
- `parseGridOptions` calls `registerStRollup` beside the three ratio
  aggregators (`parsers.ts:47–49`), and, when a parsed index is supplied,
  sets `gridOptions.context = {...context, [ST_ROLLUP_INDEX]: index}` after the
  `cloneDeep`, so every parse — mount and each live update — carries it.

### `AgGridComponent.tsx`

- The parsed totals rows are kept stable by content (a rerun re-sends an
  equal payload as a new object), the index is memoised on them, the meta and
  the parsed `columnDefs`, and the holder is passed to `parseGridOptions` on
  both the mount path and the `updateGridOptions` path.
- When the totals' **content** changes (rows or meta, by deep equality), call
  `api.refreshClientSideRowModel("aggregate")` and reset `warned`: AG-Grid
  does not re-aggregate on a `context` change. Issued whether or not the row
  data changed too. On the Arrow path every rerun sends new row objects,
  which AG-Grid treats as updates; on the JSON path the rows arrive as a string
  the rowData memo compares by value, so equal rows produce no update and a new
  totals table would never be shown. A redundant refresh is cheap.

### `types/AgGridTypes.ts`

`rollup_data?: unknown` and
`rollup_meta?: { dimensions: string[]; flags: Record<string, string> } | null`.

## Consumer contract

What `hitapps_analytics` relies on, and nothing more:

- `AgGrid(..., rollup={"data", "dimensions", "flags"?})`, passed through
  `render_managed_grid(**agg_kwargs)` unchanged.
- `aggFunc="stRollup"` on every distinct-count column and every ratio column
  whose total-row value comes from the server; `allowedAggFuncs` locked as
  today.
- Leaves in `data` = the `CUBE` rows whose flags are all 0; `rollup["data"]`
  = the whole `CUBE` answer, those rows included. Flags named
  `_grouping_<column>` (the default naming). Dimension dtypes identical in
  both frames — taking both from one query result keeps them so.
- `pivotMode=False`, ordinary row grouping.
- A group with no exact total shows empty; a grid filter that removed a leaf
  under a group empties that group's total; neither is an error.

## Tests

### Node checks — `src/aggFuncs/__checks__/rollupKey.check.ts`

`toGroupKey`: number → string, `null`/`undefined`/`""` → `""`, `keyCreator`
honoured. `canonicalKey`: same pairs in any insertion order → same key.
`nodeKey`: a two-level chain → both fields; root → `{}`; a NULL group →
`{app_version: ""}`, distinct from the key without `app_version`.

### Unit — `test/unit/test_rollup.py`

One case per validation rule above (1–6), the defaults of `flags`, the
`data=None` skip, and that the caller's totals frame is not mutated.

### E2E — `test/grid_rollup.py` + `test/test_grid_rollup.py`

`test/rollup_fixture.py` owns the leaves, the totals and the expected value of
every node, in the manner of `test/ratio_fixture.py`. Every total differs
from the sum of its children, so a substituted sum fails the test. Cells are
read by row index (AG-Grid positions rows absolutely; DOM order is not row
order).

1. Grand total, a one-level group, a two-level group show the table's values.
2. Reordering the two levels, then removing one, shows the right totals with
   no rerun.
3. Grouping by a field outside `dimensions` → empty totals, no warning.
4. A totals table with one key deliberately corrupted → empty cell and
   exactly one `console.warn`.
5. A real NULL `app_version` group shows its own total, distinct from the
   rolled-up row's.
6. A date dimension as `date32` (`datetime.date` column) and as `datetime64`
   both match.
7. The same grid with `use_json_serialization=True` matches too.
8. A filter on a dimension: the surviving group keeps its total, its parent
   and the grand total go empty. A filter on a metric: every group that lost
   a leaf goes empty.
9. `suppressAggFilteredOnly=True` with a filter: nothing goes empty.
10. A rerun with a new totals table and identical leaves shows the new
    totals.
11. `pivotMode=True` → empty totals.

## Documentation

- README: a section "Server-computed totals (`stRollup`)" after "Declarative
  aggregation without JavaScript": the problem, the `rollup` parameter, the
  flags, the semantics table, the filter rule.
- CLAUDE.md: `rollup.py` and the two new `aggFuncs` files in Architecture; a
  Key Design Decisions entry (the table travels with the leaves' transport;
  key = normalised group key, order-free; empty, never a sum).
- Version 2.6.0 in the root `pyproject.toml` and `st_aggrid/pyproject.toml`.

## Risks

- **A `keyCreator` on a dimension column that depends on the node** cannot be
  reproduced for a totals row (there is no node). Documented as unsupported;
  the miss warning makes it visible.
- **The filter rule's cost** is `O(rows × depth)` per aggregation pass. Fine
  for the consumer's grids (two levels, hundreds to low thousands of leaves);
  if a large grid ever needs it, carry the count up the tree the way
  `foldChildren` carries sums.
- **AG-Grid internals the design leans on** — the `""` empty-group key,
  `getKeyForNode`'s stringification, aggregation running before
  `filter_aggregates` — are cited above with line numbers. Tests 5, 6 and 8
  fail if a version bump changes any of them.
- **Python's duplicate check (rule 6)** normalises with Python's `str()` and
  can under-report for floats and dates; it is a guard, not the key.

## Done when

- `node src/aggFuncs/__checks__/rollupKey.check.ts` passes.
- `pytest -m "not e2e"` passes, including `test/unit/test_rollup.py`.
- `pytest` passes, including `test/test_grid_rollup.py`, with the rebuilt
  bundle committed.
- README, CLAUDE.md and both `pyproject.toml` versions updated.
