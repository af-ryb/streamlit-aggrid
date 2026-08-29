# Requirement: group-dimension cell notes (annotate row groups by field=value)

Status: **proposed / foundation** · Builds on: shipped flat read-only + editable Cell
Notes (AG-Grid 35.3, branch `v35.3`). · Consumer: UA Performance pivot/grouped grids.

> This is a design foundation to pick up later. A small **debug probe**
> (`debug_group_notes`) ships now to validate the riskiest assumption before the
> full feature is built — see "De-risk" below.

## Background — what already ships

AG-Grid 35.3 added **Cell Notes** (Enterprise). This component already exposes:

- `notes={rowId: {colId: note}}` — read-only display notes seeded from the host,
  keyed by `getRowId` + column field.
- `notes_editable=True` — editable notes with a sticky write-back surfaced as
  `result.notes`.

Implementation: a `notesDataSource` whose `getNote({rowNode, column})` looks up
`store[rowNode.id][column.getColId()]` (see `st_aggrid/frontend/src/AgGridComponent.tsx`,
the `notesDataSource` memo). Works well for **flat grids with a stable `getRowId`**.

## Problem — flat keying doesn't fit pivot/grouped grids

In pivot mode both coordinates are **grid-generated**, so `{rowId: {colId}}` never
matches:

- **Rows** are group rows with grid-generated ids, and `getRowId` is **not** called
  for group rows — your business keys never reach them.
- **Columns** are pivot result (secondary) columns with synthetic colIds; the real
  measure is on `colDef.pivotValueColumn`, the column dimension path on
  `colDef.pivotKeys`.

(Confirmed against `node.getRoute()` / `colDef.pivotKeys` / `colDef.pivotValueColumn`
in 35.3.) `getNote` still fires — it just never finds a match, so nothing renders
(no error). Conceptually, a note on an aggregated metric value is also ambiguous.

## Direction — annotate row-group DIMENSIONS, not value cells

Decided model: a note is a **predicate over a row's dimension values**, not a cell
coordinate.

- Key = a set of `{field: value}` constraints, e.g.
  `{"campaign": "my-important-campaign"}` or `{"campaign": "X", "country": "US"}`.
- A note matches a group row iff its constraint set is a **subset** of that row's
  dimension ancestry — so it shows **regardless of which other fields the grid is
  grouped by, or in what order**.
- Single-field (`campaign`) and multi-field (`campaign`+`country`) both work.
- Notes attach at the **group / dimension** level, never on metric cells.

### Matching semantics

- Build the row's dimension map by walking `node` → `node.parent`, collecting
  `{node.field: node.key}` (the `groupDimensionAncestry` helper, already added for the
  probe).
- A note matches iff every `(field, value)` in `match` is present in the ancestry map
  (string compare — `node.key` is a string).
- Display on the **boundary node**: `match(node) && !match(node.parent)` — the mark
  sits on the row where the constraint set first becomes complete, not smeared across
  every descendant. Make it configurable: `scope: "boundary" | "subtree"`.
- A note is only visible when its field(s) are in the **active row groups**; otherwise
  it's simply not shown (expected).

### Display nuance — depends on `groupDisplayType`

- `groupRows` (full-width group rows — the UA grid's likely layout) → requires the
  **`FullWidthNotesDataSource`** variant (`supportsFullWidthRows: true`; `getNote`
  receives `location: 'fullWidthRow'`).
- auto group column (`singleColumn` / `multipleColumns`) → standard cell notes on the
  group column.

One datasource can serve both. **The full-width path is the main unknown to validate**
(hence the probe).

## Proposed Python API

```python
notes_groups = [
    {"match": {"campaign": "my-important-campaign"}, "note": "Key campaign"},
    {"match": {"campaign": "X", "country": "US"},
     "note": {"text": "Check ROAS", "author": "ops"}},
]
AgGrid(df, go, enable_enterprise_modules=True, notes_groups=notes_groups)
```

- `match`: dict of `{field: value}` (values stringified to match `node.key`).
- `note`: string or Note object (`{text, author, createdAt, metadata, ...}`); `readOnly`
  is forced in read-only mode.
- optional `scope`: `"boundary"` (default) | `"subtree"`.

## Scope estimate (read-only)

| File | Change | ~LOC |
|------|--------|------|
| `st_aggrid/aggrid.py` | `notes_groups` param, enterprise gate, passthrough, docstring | ~25 |
| `AgGridTypes.ts` | `notes_groups?: Array<{match, note, scope?}>` | ~3 |
| `AgGridComponent.tsx` | match/boundary logic; extend datasource to `FullWidthNotesDataSource` (group rows + group column); include in `refreshNotes` | ~50–70 |
| `test/` | grouped grid + `notes_groups`; assert mark on the right group **independent of grouping order** | ~50 |

≈ **110–150 LOC, ~half a day**. The flat path is untouched — group matching is an added
branch in the same `getNote`.

## Out of scope (for now)

- Editable / write-back for group notes (would need to reverse-derive `match` keys and a
  result surface).
- Notes on metric / value cells and pivot composite keys (explicitly dropped — see
  "Problem").
- Flat-mode leaf-row matching: same predicate model works, but a leaf row has many
  cells, so it needs a "which column" rule (default: the cell of the `match` field).

## De-risk — the group-notes probe (ships now)

`debug_group_notes=True` installs a diagnostic `FullWidthNotesDataSource` that, for every
group row, **logs its dimension ancestry** to the console and **renders a note** showing
that ancestry. Run it on the real UA grid to confirm:

1. group rows get note indicators → the **full-width path works** in your
   `groupDisplayType`;
2. the logged `{field: key}` values are the **exact strings** to put in `match`.

It reuses the same `groupDimensionAncestry` helper the real feature will use.

```python
AgGrid(df, go, enable_enterprise_modules=True, debug=True, debug_group_notes=True)
```

## Open questions to resolve before building

- Full-width group-row note marker + whether it renders in the UA `groupDisplayType`
  (the probe answers this).
- `node.key` stringification when a dimension value is numeric / formatted.
- `boundary` vs `subtree` default.
- Flat-mode expectation (out of scope above, but confirm).

## Key files / references

- `st_aggrid/aggrid.py` — params + passthrough.
- `st_aggrid/frontend/src/AgGridComponent.tsx` — `groupDimensionAncestry`, the
  `notesDataSource` memo (flat + diagnostic; future `notes_groups` matcher).
- `st_aggrid/frontend/src/types/AgGridTypes.ts` — payload fields.
- AG-Grid types: `node_modules/ag-grid-community/dist/types/src/interfaces/notes.d.ts`
  (`NotesDataSource` / `FullWidthNotesDataSource` / `Note`).
