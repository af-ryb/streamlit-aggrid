# Per-column colour-scale picker in the grid's menus, and removal of the settled redraw — Design

**Status:** designed against the code and a throwaway spike, not yet implemented
**Branch:** `feature/color-scale-picker` (off `main` at `916aee2`)
**Date:** 2026-09-20
**Release:** 2.5.0 (additive public API; one internal removal)
**Consumer tasks:** stream 9, slices 9.3 and 9.5 (`dash-ai-TASKS.md`)

All `path:line` references are to this repository at `916aee2` unless the path
starts with `web_app/`, which is the consumer (`hitapps_analytics`). The
consumer's side of 9.3 gets its own spec in that repository; this document
fixes only the contract it will be written against (see "Consumer contract").

The two slices ship in one PR because both touch `AgGridComponent.tsx` and so
share one frontend rebuild and one full e2e run. They are otherwise
independent, and land as separate commits in the order **9.5 first**, with a
full e2e run between them, so that a regression is attributable.

---

# Part A — 9.5: remove the settled redraw

## Problem

Commit `5339f85` (2026-08-16) added a second `redrawRows()` after a config
update, fired from a debounced `displayedColumnsChanged` listener, to cure
stacked cells after a value column was added to a horizontally scrolled pivot
grid. On 2026-09-18 the real cause of that family of defects was found: AG-Grid
36.0.x does not dispatch `gridColumnsChanged` when a value column is added to a
live pivot grid, so the new column's cells never receive their
`leftChanged`/`widthChanged` listeners. AG-Grid 36.1.0 fixes it (fork 2.4.3,
PR #6). The settled redraw treated the symptom — `redrawRows` recreates the
cells at the correct `left` but adds no listeners — and is now dead weight: a
second full row redraw on every config update.

Evidence (2026-09-18, on 36.1.0, arming line disabled): the guard test
`test_adding_a_value_column_while_scrolled_does_not_stack_cells`
(`test/test_grid_cohort_pivot.py:532`) and its four neighbours (`:452`, `:478`,
`:565`, `:610`) pass. Not verified: a full run without it — this slice is that
run — and that the original `5339f85` defect on 36.0.0 went through this exact
mechanism. The latter would need a downgrade and does not change the decision,
so it stays unverified and the docstrings say so.

## Change

All in `st_aggrid/frontend/src/AgGridComponent.tsx`:

| Remove | Where |
| --- | --- |
| `redrawPendingRef`, `redrawSettleCleanupRef` and their comments | `:191-197` |
| the arming line and the comment block above it | `:640-652` |
| the debounced `displayedColumnsChanged` listener and its cleanup closure | `:874-908` |
| the two teardown lines in the unmount effect | `:809-810` |

Kept: the first `clearStats` + `redrawRows()` (`:637-638`) and its comment
(`:627-636`) — that one makes a changed `cellStyle`/`cellClass` reach painted
cells and has nothing to do with this defect. The `debounce` import stays; the
`fitGridWidth` refit still uses it.

`test/test_grid_cohort_pivot.py`: the module docstring (`:31-35`, "repaints
once the column layout has settled") and the guard test's docstring
(`:539-552`, "the redraw ran while the column layout was still in flight …
Guards the settled-redraw") are rewritten to name the mechanism:
`gridColumnsChanged` not dispatched on 36.0.x, cells without position
listeners, fixed by the 36.1.0 pin. The comment at `:458-461` ("puts the
settled-redraw under load") is reworded. The test itself is unchanged and
remains the guard — now for the pin, which `CLAUDE.md` already documents.

## Done when

The four removals are in, `:637-638` is untouched, the guard test and
`test_a_value_column_added_live_*` are green, no settled-redraw wording
survives in `AgGridComponent.tsx` or the cohort suite's docstrings, and the
whole e2e suite is green **before** Part B's first commit.

---

# Part B — 9.3: per-column colour-scale picker

## Problem

A colour scale is a build-time property: the page declares it in
`colDef.context["stColorScale"]`, and the most a reader can do is switch a
whole block's painting on or off. The goal is to let the reader choose scheme,
mode and direction **for one column**, from the grid's own menus, without a
rerun — and to have the choice survive a rerun and a saved view.

## What the spike established (2026-09-20, AG-Grid 36.1.0, throwaway code)

Driven through `JsCode` menu callbacks against the unmodified 2.4.3 bundle:

1. **`subMenu` + `checked` render correctly** in the v36 column menu (⋮, the
   non-tabbed menu) and in the cell context menu. The callbacks run on every
   open, so a `checked` computed from live state is always current.
2. **Playwright can drive both**: hover the header, click
   `.ag-header-cell-menu-button`; `click(button="right")` on a cell; hover a
   `.ag-menu-option` to open its sub menu; a tick is
   `.ag-menu-option-icon .ag-icon-tick`.
3. **`refreshCells({force: true, columns})` re-runs `cellStyle`**: neutral →
   diverging → reversed repainted with no rerun.
4. **"None" leaves the old colour on screen.** `stColorScaleCellStyle` returns
   `null` when nothing resolves (`colorScales/index.ts:168`), and ag-grid-react
   keeps the previous inline style on `null` — the very reason `UNPAINTED`
   exists (`:33-40`). Today that path is unreachable after first paint; a
   picker makes it the common case.
5. **Mutating `colDef.context` does not work in pivot mode.** A pivot result
   column's `colDef.context` is *not* the source column's object
   (`sharedContext: false`), so a mutation on the source repainted nothing.
   `colDef.pivotValueColumn` does resolve the source column from a result
   column, in both menus.
6. **`params.context` is the grid's own `context` object**, by identity
   (`params.context === api.getGridOption("context")`). AG-Grid does not clone
   it.
7. **AG-Grid writes the inferred `cellDataType` into the colDef**
   (`region: "text"`, `metric_a: "number"`), so "is this column numeric" is
   answerable in the frontend without Python's help.
8. **36.1.0 has a public hook for the Columns tool panel.**
   `getColumnMenuItems` (`ag-grid-community/.../entities/gridOptions.d.ts:1939`)
   is called with `source: "columnMenu" | "columnsToolPanel" | "columnChooser"`
   and a custom item with a sub menu rendered and fired from a right-click on a
   Columns-panel row. It **takes precedence over `getMainMenuItems`** for the
   column menu.

Finding 8 overturns a premise of the owner's 2026-09-01 decision. The Columns
panel was dropped then "on facts, not taste": `ToolPanelContextMenu` was
internal and no grid option existed. That was true of 36.0 and is not true of
36.1.0, which this fork is pinned to and may not go below. The panel is also
the better surface on a pivot grid: it lists each metric once, where the
header shows one result column per pivot key. This design therefore takes
**three** entry points through **two** hooks; see "Menu".

## Design decisions

Agreed with the owner on 2026-09-20:

1. **The reader's choice is its own layer, not a mutation of `colDef.context`.**
   Findings 5 and 6 settle this on evidence, and there are two further reasons.
   `updateGridOptions` (`AgGridComponent.tsx:528`) installs fresh colDefs from
   Python on every config rerun and would erase a mutation. And echoing the
   choice back through `columnDefs` would fail the `isEqual(prevGo, currGo)`
   gate (`:506`), sending every menu click's rerun down the whole
   config-update path: `applyColumnState`, `setRowGroupColumns`,
   `refreshClientSideRowModel`, `redrawRows`, tool-panel re-open.
2. **The menu offers scheme (without `fill`), mode, `reverse` and a reset.**
   `scope`, a free `anchor`/`span` and `fill`'s colour stay build-time.
3. **`color_scale_state` is read at mount only**, like `initial_state`. A live
   prop would inherit the capture↔prop lag `columns_state` already suffers
   from: two quick clicks, and the rerun from the first writes the prop back
   over the second. A view switch remounts the grid by `key` anyway.

4. **The Columns tool panel is a third entry point** (finding 8; confirmed by
   the owner on 2026-09-20). It reverses the 2026-09-01 exclusion, whose
   factual premise no longer holds on 36.1.0.

## Scope

**In.** A grid-level opt-in; an override layer in the resolver; the menu on
three surfaces; one fork-owned collect method and one synthetic `update_on`
event; a mount-only restore prop; validation, README, tests.

**Out.** The consumer's `grid_state.py`/Saved Views work (own spec). Any
change to the arithmetic, palettes or population logic. A legend. Scope,
anchor values or fill colour in the menu. Localisation of the menu labels
(English literals, as the toolbar's are).

## Public contract

### Opt-in

```python
gb.configure_color_scale(scheme="neutral", interactive=True)
# or, without the builder:
grid_options["context"] = {"stColorScale": {"interactive": True}}
```

`interactive` is a **grid-level-only** key of the existing declaration.
`interactive=True` with no other key is a complete, valid grid-level
declaration. Without it, nothing in this document happens: no slot is filled,
no menu item appears, no context key is injected, `color_scale_state` is
ignored — byte-for-byte today's behaviour.

The menu needs the enterprise bundle (`ColumnMenuModule`,
`ContextMenuModule`). On a community grid the opt-in still fills the slots and
still honours `color_scale_state`, but adds no menu; logged under `debug`.

**Toggling `interactive` on a live grid.** It takes effect on the next config
update, in both directions, with no remount. The hooks are installed only when
the parsed options are interactive — a grid that never opts in never gets a
wrapper around its menus — so switching `interactive` **on** installs them
through `updateGridOptions`, fills the slots, honours `color_scale_state` and
adds the item to the column menu, the cell menu and the Columns panel at once.
Switching it **off** cannot take a wrapper away again (`updateGridOptions`
writes the keys it is handed and never clears one it is not), which is why both
hooks re-check the live flag on every open: the item then disappears from every
surface at once. The README states this.

*Corrected 2026-09-20 during implementation, twice. This section first claimed
both hooks were `@initial` (`gridOptions.d.ts:1921-1939`) and so creation-only.
Task 6's reviewer checked the typings and narrowed the claim to the column
hook, and the resulting asymmetry was documented rather than engineered away.
The final review measured the shipped runtime instead of the typings: `@initial`
on these keys is typings-only — `getColumnMenuItems` is absent from
`INITIAL_GRID_OPTION_KEYS` (`ag-grid-community/dist/package/main.cjs.js`),
`updateGridOptions` writes every key it is given, and `_resolveColumnMenuItems`
(`ag-grid-enterprise/dist/package/main.cjs.js`) reads the callback through
`gos.getCallback` on every open. There is no asymmetry, and the e2e test
`test_interactive_takes_effect_on_a_live_grid_in_both_directions` now pins the
behaviour.*

### The override layer

Resolution gains a third layer, the reader's:

```
grid-level defaults  <  the column's own declaration  <  the reader's override
```

An override is keyed by the **source column's colId** — for a pivot result
column, `colDef.pivotValueColumn.getColId()` — so a choice made on a metric
applies to every result column of that metric, and survives pivot keys coming
and going. Its value is:

| Override | Meaning |
| --- | --- |
| absent | resolve exactly as today |
| `false` | unpainted, whatever the column declares |
| `{scheme?, mode?, reverse?}` | merged per key over the two lower layers; **activates** a column that carries no declaration of its own |

Only what the reader touched is stored, never a full declaration, so a page
that later changes its defaults still reaches every column the reader left
alone. Keys accumulate as written and are never normalised away; "Reset to
default" deletes the entry.

A column whose own declaration is `false` stays off whatever the override
says: that is the page author's opt-out, it also removes the menu item (see
"Eligibility"), and only a stale saved state could carry an override for it.

If the merge *with* an override resolves to nothing (a saved `mode: "anchor"`
on a column whose page code has since dropped `anchor`/`span`), the override is
ignored for that resolution and the column resolves without it. A saved view
must never be able to blank or break a column.

### State out

```python
AgGrid(..., collect=["getColumnState", "stGetColorScaleState"],
       update_on=[..., "stColorScaleChanged"])
result.color_scale_state   # {"metric_a": {"scheme": "diverging"}, "ratio": False} | {} | None
```

* `stGetColorScaleState` is a **fork-owned collect method**. It is resolved
  from a small registry inside the collector before the `GridApi` is
  consulted; the `GridApi` object is not patched (its extensibility is not a
  documented guarantee). The result lands under `colorScaleState`, exposed as
  `AgGridResult.color_scale_state`. Like every collect method it is read on
  **every** collect, whatever event triggered it, so the value is never stale.
* `stColorScaleChanged` is a **synthetic event**. It is not an AG-Grid event
  and never reaches `addEventListener`; the menu action calls the collector
  directly (`collectNow`, `hooks/useAutoCollect.ts:103`) when — and only when —
  the name is in `update_on`. Its event data is
  `{colId, source: "uiColorScaleMenu"}`; the `source` deliberately does not
  start with `api`, which the collector would drop as programmatic (`:126-138`).
  A debounce on it is rejected, exactly as for the lifecycle events.

### State in

```python
AgGrid(..., color_scale_state={"metric_a": {"scheme": "diverging"}})
```

Read once, at mount; later changes to the prop are ignored until the grid
remounts (a changed `key`). Unknown colIds are kept silently — columns come
and go with the page's controls, and an entry for an absent column costs
nothing and must survive until the column returns. Ignored entirely on a grid
that is not `interactive`.

## Frontend

### `colorScales/overrides.ts` (new, pure, imports nothing)

Owns the layer's arithmetic so it can be exercised by a `__checks__` file
under plain `node`:

* `type Override = false | { scheme?: string; mode?: string; reverse?: boolean }`
* `sanitizeState(raw: unknown): Map<string, Override>` — the guard copy of
  Python's validation: keeps `false` and objects, keeps only the three keys
  with values of the right type, drops everything else. Never throws.
* `serializeState(map): Record<string, Override>` — plain object, for the
  collector.
* `applyChoice(map, colId, choice, hasOwnDeclaration)` — the menu's one write
  path: `{scheme}`, `{mode}`, `{reverse}` merge into the entry; `"none"` writes
  `false` when the column has its own declaration and deletes the entry when it
  does not (there is nothing to switch off); `"reset"` deletes the entry.

### `colorScales/index.ts`

* `ST_COLOR_SCALE_OVERRIDES = "stColorScaleOverrides"` — the reserved key
  under the grid `context` that holds the live `Map`.
* `readColorScaleConfig(colDef, gridContext, override?)` gains the third
  layer as specified above, including activation and the
  fall-back-when-unresolvable rule. With `override === undefined` it is
  today's function, unchanged.
* `resolveFor(colDef, column, gridContext)` — the one place that derives the
  source colId (`colDef.pivotValueColumn ?? column`), looks the override up in
  `gridContext[ST_COLOR_SCALE_OVERRIDES]` and calls `readColorScaleConfig`.
  `stColorScaleCellStyle` and `paintedColumnIds` both go through it, so the
  `modelUpdated` invalidation (`:340`) also repaints columns that are painted
  only because the reader said so.
* `stColorScaleCellStyle`: when nothing resolves **and the grid is
  interactive**, return `{ ...UNPAINTED }` instead of `null` (finding 4). A
  non-interactive grid keeps returning `null`.
* `registerColorScales`: on an interactive grid, attach the built-in to every
  colDef for which `callerCellStyleSource` is `null`, not only to columns whose
  declaration resolves (trap 1 — the slot must exist before the reader asks).
  The `defaultColDef.cellStyle` warning is raised **once per grid** in this
  mode rather than once per column, and says that the picker is unavailable.

### `colorScales/menu.ts` (new)

`registerColorScaleMenu(gridOptions, runtime)` installs the hooks;
`runtime = { overrides: Map, onChange: (colId: string) => void }`.

**Hooks.** `getColumnMenuItems` serves the column menu, the Columns tool panel
and the Column Chooser; `getContextMenuItems` serves the cell. Each wraps what
the caller supplied and appends — a built-in is a default, not a reservation:

* `getColumnMenuItems`: call the caller's `getColumnMenuItems` if there is
  one; else, for `source === "columnMenu"`, this column's own
  `mainMenuItems` if it has one (returned as is — see the third bullet), then
  the caller's `getMainMenuItems` if there is one (ours would otherwise shadow
  both, finding 8); else `params.defaultItems`. Then append.
* `getContextMenuItems`: the caller's may return a `Promise`
  (`gridOptions.d.ts:2728`); append inside `.then` when it does.
* A hook that returns nothing means "show the defaults" to AG-Grid, so
  `params.defaultItems` — not an empty list — is the fallback in both wrappers,
  and no leading separator is emitted when the base list is empty.
* A per-column menu replaces its column's menu outright, picker included, and
  the README says so. AG-Grid gives this for free for `colDef.columnMenuItems`
  (36.1) and `colDef.contextMenuItems`, both resolved *before* the grid-level
  hook the picker installs. `colDef.mainMenuItems` (`colDef.d.ts:553`) is
  resolved *after* it, so a wrapper that always installs `getColumnMenuItems`
  swallows it; the wrapper reproduces that step of
  `_resolveColumnMenuItems` itself and returns the colDef's menu unappended.

**Eligibility.** With `source = colDef.pivotValueColumn ?? params.column`, the
item is appended iff all of:

1. `params.column` is non-null and the grid's live `context` is still
   interactive;
2. `source.getColDef().cellStyle === stColorScaleCellStyle` — the slot is
   ours. This one identity check covers a caller's `cellStyle` from any of the
   three sources, the auto-group column (never walked by `eachColDef`), and a
   non-interactive grid;
3. the column's own declaration is not `false` and does not resolve to
   `fill` — `false` is the page author's explicit "not this column", and a
   fill marks a structural column, not a measurement;
4. the column is a measure: it has its own declaration, or an `aggFunc`, or
   `cellDataType === "number"` (finding 7), or `type` includes
   `"numericColumn"`.

**Shape.**

```
Colour scale ▸  None
                Neutral
                Positive
                Diverging
                Rank
                ─────────
                Mode ▸  Min–max / Z-score / Anchor*
                Reverse
                ─────────
                Reset to default**
```

`checked` comes from the fully resolved configuration at open time. `Mode` is
disabled unless the resolution is a ramp; `Anchor*` is listed only when the
lower layers carry a finite `anchor` and a positive `span`. `Reverse` is
disabled when nothing resolves. `Reset to default**` is listed only when an
override exists for the column.

**Action.** `applyChoice` → `clearStats(api)` → `refreshCells({force: true,
columns})`, where `columns` is every displayed column whose source is this one
(all result columns of the metric in pivot mode) → `runtime.onChange(colId)`.

### `utils/parsers.ts`

`parseGridOptions(data, streamlitTheme?, runtime?)`. When the parsed options
are interactive and a `runtime` is given, it sets
`gridOptions.context[ST_COLOR_SCALE_OVERRIDES] = runtime.overrides` and calls
`registerColorScaleMenu` — after `registerColorScales`, and only on an
enterprise bundle. Injection happens after the `cloneDeep` at `:17`, so the
`Map` is shared, not copied.

### `AgGridComponent.tsx`

* `colorScaleRuntimeRef`: created once per mount; `overrides` seeded from
  `sanitizeState(data.color_scale_state)`, `onChange` reading `collectNow` and
  the wanted-flag through refs (`collectNow` is declared after the
  `gridOptions` memo at `:399`).
* **Both** `parseGridOptions` call sites — the memo (`:400`) and the live
  update (`:507`) — pass the same runtime. That is what makes the choice
  survive `updateGridOptions`: the new `context` object carries the same `Map`.
  Because the `Map` is in `context` before the first cell is styled, a restored
  choice paints on first render, with no unpainted flash.
* `colorScaleEventWanted`: derived from `updateOn` next to `lifecycleWanted`
  (`:470`); `onChange` calls
  `collectNow("stColorScaleChanged", {colId, source: "uiColorScaleMenu"})` only
  when it is true.
* `useAutoCollect` receives `extraCollectors = { stGetColorScaleState: { key:
  "colorScaleState", read: () => serializeState(overrides) } }`.

### `hooks/useAutoCollect.ts`

* New option `extraCollectors?: Record<string, { key: string; read: () =>
  unknown }>`, consulted in the collect loop (`:145`) before the `GridApi`. An
  explicit `key` because `toKey` only strips a leading `get`.
* `SYNTHETIC_EVENTS = new Set(["stColorScaleChanged"])`, skipped in the
  listener loop next to `LIFECYCLE_EVENTS` (`:183`) — a listener for it would
  be dead, not harmful, but the debug log should say why there is none.

### `types/AgGridTypes.ts`

`color_scale_state?: unknown` on `AgGridData`; `colorScaleState` on
`GridStateResult`.

## Python

* `color_scale.py`
  * `interactive` joins `_KNOWN_KEYS`; must be a `bool`; **rejected at column
    level** with a message that it is a grid-level key.
  * A caller-supplied `context["stColorScaleOverrides"]` is rejected: the key
    is reserved.
  * `validate_color_scale_state(state)`: `None` passes; otherwise a `dict` of
    `str` → `False` or a `dict` whose keys are a subset of
    `("scheme", "mode", "reverse")`, each checked by the existing
    `_validate_declaration` rules, with `scheme: "fill"` rejected. **Shape
    only** — it never checks resolution against `columnDefs` and never rejects
    an unknown colId. A malformed state is a programming error and raises; a
    stale one is the reader's history and must not.
* `grid_options_builder.py`: `configure_color_scale(..., interactive:
  Optional[bool] = None)`, keyword-only, written like the other keys.
* `aggrid.py`: `color_scale_state: Optional[Dict] = None`, validated next to
  `validate_color_scale_columns` (`:423`), passed in the component payload next
  to `initial_state` (`:490`). `SYNTHETIC_UPDATE_ON_EVENTS =
  frozenset({"stColorScaleChanged"})`; `validate_update_on` rejects a debounce
  on it with the same error shape as for lifecycle events. Docstrings for both.
* `result.py`: `color_scale_state` property over `colorScaleState`.
* Version `2.5.0` in both `pyproject.toml` files; README section "Letting the
  reader choose a colour scale" under the declarative colour scales, plus the
  Auto-Collect section's note on the fork-owned method and synthetic event;
  `CLAUDE.md` architecture tree and the colour-scale design-decision bullet.

## Consumer contract

What the consumer spec may rely on, and nothing more:

* `configure_color_scale(interactive=True)` turns the picker on for a grid;
  omitting it is today's grid.
* Append `"stGetColorScaleState"` to `collect` and `"stColorScaleChanged"` to
  `update_on`; read `result.color_scale_state`. It is present on every collect,
  so it can be captured under the same programmatic-event filter as
  `column_state`.
* Pass the saved value as `color_scale_state=`. It needs **no per-mount
  freezing** — the fork reads it at mount only — but passing the same frozen
  restore snapshot the consumer already keeps is equally correct.
* The state is a third key of `block.settings` beside `grid_state`, **not** a
  part of the `GridVisibility`/`derive_overlay` surface
  (`web_app/src/bi_core/charts/grid_state.py:62-86`): that overlay is owned by
  the page's controls and recomputed every rerun; this one is owned by the
  reader and changes rarely.
* Turning `interactive` on or off for a live grid takes effect on the next
  config update, on all three surfaces at once. No remount is needed either
  way.
* `show_color_scale` stays the block-level switch. Off means no declarations,
  no `interactive`, no `color_scale_state` passed; the saved choice stays in
  `settings` and returns when the switch does.

## Tests

### Node checks — `src/colorScales/__checks__/overrides.check.ts`

`sanitizeState` (junk in, clean map out; never throws), `serializeState`
round trip, every `applyChoice` branch including "none" on a declared vs. an
undeclared column and "reset".

### Unit — `test/unit/`

`interactive`: accepted at grid level alone and with other keys, non-bool
rejected, rejected at column level; the reserved context key rejected;
`configure_color_scale(interactive=True)` output. `validate_color_scale_state`:
`None`, `{}`, `False`, each key's bad value, unknown key, `fill`, `True`,
non-dict; an unknown colId and an unresolvable-but-well-formed entry both
pass. `validate_update_on`: the synthetic name bare passes, debounced raises.

### E2E — `test/grid_color_scale_picker.py` + `test/test_grid_color_scale_picker.py`

Expected colours come from `color_scale_fixture.expected_rgba`, never typed.
Grids, appended in order: (0) flat interactive, with a declared column, an
undeclared numeric column, a text column, a `fill` column and a column with
its own `cellStyle`; (1) pivot interactive with the Columns side bar; (2) flat,
**not** interactive; (3) interactive with a caller `getMainMenuItems`
(`JsCode`); (4) interactive, mounted with `color_scale_state`, showing
`result.color_scale_state` and a button that bumps the grid's `key`.

* header ⋮: pick a scheme on the undeclared column — painted, no rerun
  happened (a rerun counter in the app stays put when `stColorScaleChanged` is
  not in `update_on`);
* context menu: same sub menu, tick on the current value; change mode, then
  reverse; colours match the fixture each time;
* "None" on a painted column clears the colour (finding 4's regression test);
  "Reset to default" restores the declared one;
* eligibility: no item on the text, `fill` and own-`cellStyle` columns, nor on
  the auto-group column; no item anywhere on grid 2, whose menus and colours
  are otherwise identical to today's;
* pivot: a choice from one result column's header repaints **all** result
  columns of that metric; the Columns-panel right-click offers the same sub
  menu and does the same;
* composition: grid 3 shows the caller's item and ours;
* state: the choice appears in `result.color_scale_state`; after a rerun and
  after a remount fed from it, the grid paints the choice on first render;
* the choice survives a config-only rerun that goes through
  `updateGridOptions` (a widget that flips an unrelated grid option).

The whole existing e2e suite stays green; `test_grid_color_scale.py` in
particular proves the non-interactive path is unchanged.

## Risks

* **`getColumnMenuItems` is new in 36.1.** It is public and typed, and the
  spike drove it, but it has one release of history. Containment: the wrapper
  is one function; falling back to `getMainMenuItems` for the header loses
  only the Columns-panel surface.
* **UNPAINTED on every cell of an interactive grid.** Each undeclared cell now
  gets `{backgroundColor: "", fontWeight: ""}`. This clears only inline
  properties the built-in itself sets; class-based and row-level styling are
  untouched. The e2e non-painted-column assertions cover it.
* **Sub menu clipping on short grids.** Popups are confined to the grid by
  default, and the sub menu opened flush with the grid's bottom edge in the
  spike. If the e2e run shows clipping on a realistic short grid, the remedy
  is `popupParent: document.body` — possible because CCv2 has no iframe — and
  it is a separate, grid-wide decision, not made here.
* **Measure heuristic.** Rule 4 of eligibility could offer the item on a
  numeric identifier column. Harmless — the reader simply does not pick it —
  and the page author's opt-out already exists: `color_scale=False` on that
  column (rule 3).
* **Not verified by the spike:** the override layer end to end in pivot mode
  (the spike proved the mutation path fails there and that `params.context`
  identity holds, which is what the layer rests on, but the layer itself did
  not exist yet). The pivot e2e test is the first implementation milestone for
  that reason.

## Done when

On a grid with `interactive=True` the reader changes scheme, mode and
direction of a single column from the ⋮ menu, from a cell right-click and from
the Columns panel; the picture updates without a rerun; "None" and "Reset"
behave as specified; the choice is reported through `collect`, survives a
rerun, a config update and a remount fed from `color_scale_state`; a grid
without the opt-in behaves exactly as in 2.4.3; node checks, the unit suite
and the entire e2e suite are green and cover all three entry points.
