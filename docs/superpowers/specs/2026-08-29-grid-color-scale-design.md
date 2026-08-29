# Declarative Colour Scales — Design

**Status:** designed against the code, not yet validated against a running grid
**Branch:** `grid-color-scale` (off `main`)
**Date:** 2026-08-29

## Problem

Every grid in the main consumer (`hitapps_analytics`) that wants a heat-map
column background ships its own `JsCode` cell styler. There are five of them:

| Module | Constant |
|---|---|
| `data_sources/entities/funnel_saj/js_funcs.py` | `js_color_gradient_styler` |
| `web/dashboards/payers_intelligence/js_funcs.py` | `js_column_gradient_styler` |
| `web/dashboards/payers_intelligence/js_funcs.py` | `js_pivot_column_gradient_styler` |
| `web/dashboards/cohort/js_funcs.py` | `js_color_gradient_styler` |
| `web/dashboards/iap_dash/grid_builder.py` | re-uses the cohort one |

The consumer already has a declarative switch for the feature —
`TableBlockSettings.show_color_scale`, plus per-dashboard overrides in
`funnel/chart_builder.py` and `cohort/chart_builder.py`. What it does not have
is a way for that boolean to mean anything without hand-written JavaScript, so
each dashboard picks a styler by hand and each grid builder threads a
`cell_style=… if color_scale_enabled else None` argument through its column
configuration.

This is the same shape as the problem the built-in aggregators solved: the
application holds the intent in structured form and JavaScript is only the
executor. It also forces `allow_unsafe_jscode=True` on every grid that colours
a column.

Three defects come along with the duplication:

1. **Quadratic cost.** Every one of the five calls
   `forEachNodeAfterFilterAndSort` *per painted cell*. For a grid of `N` rows
   and `M` painted columns that is `O(N² · M)` per repaint.
2. **Inconsistent population.** The flat payers styler scans leaf rows only
   (`if (!node.data) return`). The other four mix group aggregates and leaves
   into one min/max. For a ratio column that is harmless; for a summed column
   (`iap_revenue`) the top group total sets the maximum and washes every leaf
   out.
3. **A `console.log` per painted cell** in the cohort styler.

## Scope

**In.** Three built-in colour schemes, declared from Python, applied by the
frontend as a cell background; grid-level defaults with per-column opt-in;
Python-side validation of the declaration; a memoised statistics pass that
removes the quadratic cost.

**Out.** Runtime activation from the columns tool panel (phase 2 — see
*Deferred*), the `reverse` direction flag (phase 2), custom user-supplied
colours, any AG-Grid version bump, and the consumer-side migration itself.

## Public contract

### Declaration

The key is `stColorScale`, nested in `context` exactly as `stRatio` and its two
siblings are. Two levels:

```python
# grid-level defaults  →  gridOptions["context"]["stColorScale"]
gb.configure_color_scale(scheme="positive")

# per-column opt-in    →  colDef["context"]["stColorScale"]
gb.configure_column("iap_revenue", color_scale=True)                     # inherit the grid default
gb.configure_column("arppu",       color_scale={"scheme": "diverging"})  # override
gb.configure_column("installs",    color_scale=False)                    # explicitly off
```

A grid-level declaration alone paints nothing. It only supplies defaults; a
column is painted when, and only when, it carries its own `stColorScale` entry
that is not `False`.

Python writes the value it was given — `True`, `False` or the dict — rather
than normalising `True` into `{}`. The three states stay distinguishable in the
JSON, and the Python side stays trivial.

Both `configure_color_scale` and `configure_column(color_scale=…)` **merge**
into any existing `context` rather than replacing it. Replacing it would delete
the `stRatio` declaration on the very columns the consumer paints — its metric
columns carry both.

### Resolution

Per column, in the frontend:

```
raw = colDef.context?.stColorScale
raw is undefined | null | false   →  not painted
own    = raw === true ? {} : raw
merged = { ...gridContext.stColorScale, ...own }        // shallow; column keys win
```

A per-key shallow merge is what makes phase 2 cheap: `reverse` becomes one more
key in the same merge, with no change to the shape of the API.

### Keys

| Key | Values | Default |
|---|---|---|
| `scheme` | `"neutral"` \| `"positive"` \| `"diverging"` | required at one of the two levels |
| `mode` | `"minmax"` \| `"zscore"` | the scheme's own default (below) |
| `skip_non_positive` | `bool` | the scheme's own default (below) |

`reverse` is reserved for phase 2 and rejected by validation until then, so a
consumer cannot come to depend on it being ignored.

### Python API

```python
class GridOptionsBuilder:
    def configure_color_scale(
        self,
        scheme: str,
        mode: str | None = None,
        skip_non_positive: bool | None = None,
    ) -> None: ...

    def configure_column(
        self, field, header_name=None, color_scale=None, **other_column_properties
    ) -> None: ...
```

`configure_color_scale` writes only the keys it was given — a `None` argument is
omitted, not written as null, so the scheme's own default survives.

`configure_column`'s new `color_scale` parameter is `None` by default and the
method behaves exactly as today when it is not passed. When it is passed, the
value is merged into the column's `context` under `stColorScale`, preserving
both any `context` already stored on that colDef from an earlier
`configure_column` call and any `context=` passed in the same call.

### Validation

New module `st_aggrid/color_scale.py`, modelled on `st_aggrid/ratio.py`:

```python
COLOR_SCALE_CONTEXT_KEY = "stColorScale"
COLOR_SCALE_SCHEMES = ("neutral", "positive", "diverging")
COLOR_SCALE_MODES = ("minmax", "zscore")

def validate_color_scale_columns(grid_options) -> None: ...
```

Called from `st_aggrid/aggrid.py` alongside `validate_ratio_columns`. Unlike the
ratio validator it needs no DataFrame — a colour scale names no data fields, only
a shape — so it runs unconditionally, including for a grid fed entirely through
`grid_options["rowData"]`.

Rules:

1. A grid-level `context['stColorScale']`, when present, must be a dict. A bare
   `True` there would mean nothing, since the grid level never activates
   painting.
2. A column-level entry must be `True`, `False` or a dict.
3. Any dict may contain only `scheme`, `mode` and `skip_non_positive`.
4. `scheme` must be a string in `COLOR_SCALE_SCHEMES`; `mode` a string in
   `COLOR_SCALE_MODES`; `skip_non_positive` a `bool` (and not an `int` — `bool`
   is an `int` subclass, the same trap `ratio.py`'s `_is_number` documents).
5. For every column whose entry is not `False`, the **resolved** declaration
   (grid defaults merged with the column's own) must carry a valid `scheme`.
   This is where `color_scale=True` with no grid-level default is caught.

Error messages follow `ratio.py`'s convention of naming the location:
`column 'cpi': context['stColorScale']['scheme'] must be one of ('neutral',
'positive', 'diverging'), got 'green'.`

The resolution rule therefore exists twice — once here, producing the actionable
error, and once in the frontend as a guard. That is deliberate: the frontend
copy has to cope with grid options that never went through `GridOptionsBuilder`,
and returning `null` there is a better failure than throwing inside a cell
renderer. The Python copy is the one that talks to the developer.

`_iter_column_defs` and `_label` move out of `ratio.py` into a new
`st_aggrid/_coldefs.py`, imported by both validators. They are private helpers
with no behaviour of their own; a second hand-written copy of the depth-first
colDef walk is exactly the kind of thing that drifts.

Exports added to `st_aggrid/__init__.py` and `__all__`, mirroring the ratio
constants: `COLOR_SCALE_CONTEXT_KEY`, `COLOR_SCALE_SCHEMES`,
`COLOR_SCALE_MODES`, `validate_color_scale_columns`.

## Population

For a cell being painted in column `colId` on node `node`:

```
api.forEachNodeAfterFilterAndSort(row => keep row when
      row.footer !== true                  // grand total is not a comparable row
   && row.rowPinned == null                // nor is a pinned row
   && row.level === node.level             // compare like with like
   && extractValue(rowValue) !== null
   && (!skipNonPositive || value > 0))
```

where `rowValue = row.group ? row.aggData?.[colId] : row.data?.[colId]` and
`colId = params.column.getColId()`.

The group/leaf branch also covers pivot mode: there `row.data[colId]` is
undefined because `colId` names a pivot result column, and the group branch is
what carries the value — the mechanism `funnel_saj/js_funcs.py` already
documents in a comment.

Footer and pinned rows are excluded from the population **and** are never
painted, matching `js_pivot_column_gradient_styler`, which is the only one of
the five that gets this right today.

### Value extraction

One helper, used both for the painted cell and for every population member:

| Input | Result |
|---|---|
| has a `toNumber()` method | `toNumber()` — the `StAggValue` the built-in aggregators return |
| object with `value !== undefined` | `.value` |
| object with `numerator`/`denominator` | `den > 0 ? num / den : null` — the legacy shape in `funnel_saj` |
| `number` | itself |
| `null`, `undefined`, `''`, `NaN`, `±Infinity`, anything else | `null` |

`foldSums.ts` already has a private `sortValue` that unwraps `toNumber()`.
`extractValue` is a strict superset of it and stays a separate function on
purpose: widening `sortValue` to the superset would change the **sort order** of
any column carrying the legacy `{numerator, denominator}` shape. That is a
separate decision, not a side effect of adding colour.

## Normalisation

`normalize.ts` owns the statistics and nothing about colour.

```
popStats(values) -> { count, min, max, mean, sd }        // sd over N, not N-1
```

The population standard deviation (divisor `N`) is what all three existing
z-score stylers compute; keeping it is what keeps the output identical.

```
minmaxT(stats, v):
    stats.max <= stats.min  ->  null              // no spread, nothing to show
    t = (v - stats.min) / (stats.max - stats.min)         // in [0, 1]

zScore(stats, v):
    stats.sd === 0                     ->  null
    stats.mean !== 0
      and stats.sd / |stats.mean| < CV_FLOOR  ->  null    // column is effectively uniform
    z = (v - stats.mean) / stats.sd
    |z| < Z_DEAD                       ->  null           // dead zone around the mean

CV_FLOOR = 0.001      Z_DEAD = 0.5      Z_CAP = 3
```

Two details differ from the JavaScript being replaced, both deliberate:

- The uniformity gate uses `|mean|`. The existing code divides by the signed
  mean, so a column with a negative mean yields a negative coefficient of
  variation, which is always below `0.001`, and the column is **never**
  painted. This is unreachable today — all three z-score stylers reject values
  `<= 0`, so their means are positive — but it becomes reachable the moment
  `skip_non_positive=False` is paired with `mode="zscore"`.
- `mean === 0` skips the uniformity gate rather than dividing by zero. With
  `sd > 0` the column is not uniform and painting is correct; with `sd === 0`
  the earlier branch has already returned `null`.

## Schemes

`schemes.ts` owns colour and nothing about statistics. Each scheme is data plus
two pure functions.

| scheme | default `mode` | default `skip_non_positive` | family |
|---|---|---|---|
| `neutral` | `zscore` | `True` | sequential, `rgb(51, 120, 200)` |
| `positive` | `minmax` | `False` | sequential, `rgb(29, 158, 117)` |
| `diverging` | `zscore` | `True` | diverging, red below / green above |

### Intensity and sign

```
sequential:
    minmax:  u = t                          sign = +1
    zscore:  u = min(|z| / Z_CAP, 1)        sign = +1

diverging:
    minmax:  s = 2t - 1;  u = |s|           sign = sign(s)
    zscore:  u = min(|z| / Z_CAP, 1)        sign = sign(z)
```

### Colour

```
neutral    rgb(51, 120, 200)                                  — fixed
positive   rgb(29, 158, 117)                                  — fixed
diverging  sign < 0:  rgb(round(240 - 15u), 18, 15)
           sign >= 0: rgb(35, round(190 - 15u), 40)
```

### Alpha

```
mode === "zscore" and the scheme defines a z-ramp:  alpha = zRamp(|z|)
otherwise:                                          alpha = alphaMin + u · (alphaMax - alphaMin)
```

| scheme | `zRamp(|z|)` | `alphaMin` / `alphaMax` |
|---|---|---|
| `neutral` | `0.5 ≤ z < 1`: `0.08 + 0.12(z − 0.5)`<br>`1 ≤ z < 3`: `0.2 + 0.25·log₁₀ z`<br>`z ≥ 3`: `0.55` | `0.08` / `0.55` |
| `positive` | *(none — linear ramp in both modes)* | `0.06` / `0.55` |
| `diverging` | `0.5 ≤ z < 1`: `0.1 + 0.2(z − 0.5)`<br>`1 ≤ z < 3`: `0.2 + log₁₀ z`<br>`z ≥ 3`: `0.7` | `0.1` / `0.7` |

The `alphaMin`/`alphaMax` pairs are the endpoints of each scheme's own ramp, not
new numbers — so the three non-default `scheme × mode` pairings
(`neutral`+`minmax`, `positive`+`zscore`, `diverging`+`minmax`) are defined
without inventing a palette.

`positive` has a single `alphaMin` of `0.06` — the value
`js_column_gradient_styler` uses — and it applies in both modes. There is no
per-mode second constant for any scheme.

`Z_CAP` is exported from `normalize.ts` and imported by `schemes.ts`: it is a
property of the z-score normalisation, not of a palette, and both modules need
it.

### Two invariants

- The fill is **always** `rgba(...)` over the cell's own background, never an
  opaque colour interpolated toward white. `payers_intelligence/js_funcs.py`
  documents this as a bug that already shipped once: an opaque ramp paints a
  light cell under the dark theme's light text and the number disappears.
- `diverging`'s alpha reaches `0.7`, above the `0.55` that the same module
  documents as the legibility ceiling. Reproducing the cohort report exactly
  keeps `0.7`, but it is a named constant so that changing it later is one edit.

## Behaviour changes against the JavaScript being replaced

The defaults are chosen for a zero-diff migration. It is not quite zero. The
complete list:

1. **The same-level population rule repaints any grid that displays more than
   one group level.** Both the cohort pivot and the payers Product pivot set
   `groupDefaultExpanded: -1`, so several levels are on screen and today share a
   single min/max. Restricting the population to the painted cell's own level is
   the fix this design was asked for, and it will be visible.
2. `|mean|` in the uniformity gate (above). Unreachable with the default
   pairings; listed for completeness.
3. The cohort styler's `console.log(red, green, blue, alpha)` — one per painted
   cell — is gone.
4. Alpha is emitted rounded to three decimals, so the same cell always
   serialises to the same string. Sub-perceptual, and it makes the tests exact.
5. `neutral`'s ramp is discontinuous: alpha jumps `0.14 → 0.2` at `|z| = 1` and
   `0.319 → 0.55` at `|z| = 3`. Reproduced as-is. Smoothing it is a product
   decision, not part of this change.

## Frontend architecture

```
src/colorScales/
├── schemes.ts      the three schemes: colours, ramps, default mode and
│                   skip_non_positive. Pure; imports nothing from ag-grid.
├── normalize.ts    popStats, minmaxT, zScore and the three gate constants.
│                   Pure; imports nothing from ag-grid.
├── population.ts   extractValue, the population walk, the statistics cache
│                   and its invalidation. Knows ag-grid.
└── index.ts        ST_COLOR_SCALE, readColorScaleConfig, stColorScaleCellStyle,
                    registerColorScales, attachColorScaleInvalidation.
```

`schemes.ts` and `normalize.ts` hold every number in this document and depend on
nothing, which is what makes the arithmetic reviewable on its own.

### Attachment

`parseGridOptions` calls `registerColorScales(gridOptions, data.debug === true)`
immediately after the three `registerSt*` calls. That is the one site both the
mount path and the `updateGridOptions` effect share, so a runtime config change
never leaves a column unattached — the same reason the aggregator registrations
live there.

It walks `columnDefs` with the existing `eachColDef` from `aggFuncs/foldSums`,
not a second copy, and attaches by the same rule `registerAggFunc` uses for a
caller-supplied aggregator:

```ts
if (def.cellStyle) {
  if (debug) console.log(
    `[st_aggrid] cellStyle on "${colId}" was supplied by the caller and ` +
    `overrides the built-in colour scale.`)
} else {
  def.cellStyle = stColorScaleCellStyle
}
```

A column is a candidate when `colDef.context.stColorScale` is present and not
`false`. Resolution against the grid defaults happens later, per call.

The attached function does **not** close over the declaration; it re-reads it
from `params.colDef.context` and `params.context` on every call. Phase 2 then
only has to change a declaration and call `refreshCells` — nothing is
re-attached.

Pivot needs no special handling: AG-Grid copies `cellStyle` from the source
value colDef onto the pivot result column. The consumer's current code already
depends on this.

### Cell style

```ts
export function stColorScaleCellStyle(params: CellClassParams) {
  const node = params.node
  if (!node || node.footer || node.rowPinned != null) return null

  const config = readColorScaleConfig(params.colDef, params.context)
  if (!config) return null

  const value = extractValue(params.value)
  if (value === null) return null
  if (config.skipNonPositive && value <= 0) return null

  const stats = statsFor(params.api, params.column.getColId(), node.level, config)
  if (!stats) return null

  const raw = config.mode === "minmax" ? minmaxT(stats, value) : zScore(stats, value)
  if (raw === null) return null

  return { backgroundColor: colorFor(config.scheme, config.mode, raw) }
}
```

Returning `null` rather than `{}` leaves the theme to paint the cell normally.

`params.context` is AG-Grid's grid-level `context` as passed into callback
params, so no `api` call is needed to reach the grid defaults, and the value
stays correct across `updateGridOptions`.

### Statistics cache

```ts
const statsCache = new WeakMap<GridApi, Map<string, Stats | null>>()
```

Keyed by `` `${colId}:${level}` ``. Level is part of the key because the
population is level-scoped; `skipNonPositive` is not, because it is fixed per
column and therefore already implied by `colId`. `null` is memoised too (an
empty population is a stable answer for the generation), so the map is probed
with `has()`, not by truthiness.

`attachColorScaleInvalidation(api)` is called from `onGridReady`, which already
uses exactly this pattern — `addEventListener` plus a cleanup stored in a ref —
for `findChanged` and `columnRowGroupChanged`.

On `modelUpdated`:

1. Clear this api's map.
2. Schedule, via `requestAnimationFrame` and coalesced to one pending frame,
   `api.refreshCells({ force: true, columns: <painted column keys> })`.

Both steps are needed. Clearing alone would suffice if our listener were
guaranteed to run before AG-Grid's own row re-render, but listener ordering is
not ours to control; the refresh is the safety net that repaints anything drawn
from stale statistics. `refreshCells` does not raise `modelUpdated`, so this
cannot loop; a boolean guard around the call makes that explicit rather than
implicit.

The painted column keys are derived at invalidation time — from
`api.getPivotResultColumns()` when `api.isPivotMode()`, otherwise
`api.getColumns()` — filtered by `readColorScaleConfig`. Deriving them then,
rather than caching a set at attachment time, keeps them correct across
`updateGridOptions` and across pivot toggling. *Verify while implementing:* if
resolving pivot result column keys for `refreshCells` proves fiddly, an
unfiltered `refreshCells({ force: true })` is an acceptable fallback — it
touches only the rendered viewport either way.

`api.isDestroyed()` is checked before the refresh, since a Streamlit rerun can
unmount the grid between the event and the frame.

### Cost

`O(rows)` per painted column per model generation, against today's
`O(rows² × columns)` per repaint. The expensive part — the population walk over
every row — happens once; the repaint that follows touches only the rendered
viewport, which AG-Grid keeps to a few dozen rows.

## Edge cases

| Case | Behaviour |
|---|---|
| Empty population, or every value equal | `minmax`: `max <= min` → not painted. `zscore`: `sd === 0` → not painted |
| `mean === 0` under `zscore` | Uniformity gate skipped; painted when `sd > 0` |
| Negative mean under `zscore` | Gate uses `\|mean\|`, so the column paints (see *Behaviour changes* 2) |
| Cell is `null` / `''` / `NaN` / `±Infinity` | `cellStyle` returns `null`; theme paints normally |
| `footer` / `rowPinned` row | Never painted, never in the population |
| Column acquired `aggFunc` at runtime with no declaration | `readColorScaleConfig` → `null` → not painted. The same "degrade sanely" principle `stRatio.ts` documents for an undeclared ratio column |
| No `scheme` resolvable | Python validation raises before the browser sees it; the frontend still guards and logs under `debug` |
| Grid destroyed before the scheduled frame | `api.isDestroyed()` guard |
| Column already carries a `cellStyle` | Caller wins, built-in not attached, logged under `debug` |

## Testing

The frontend has no JavaScript test runner (`frontend/package.json` defines only
`dev`, `build` and `clean`), and adding one is outside this change. Tests follow
the pattern already established for the aggregators: pure-Python units in
`test/unit/`, plus a standalone Streamlit app driven by Playwright.

### Python units

- `test/unit/test_color_scale_validation.py`, modelled on
  `test_ratio_validation.py`: unknown `scheme`, unknown `mode`, unknown key,
  wrong types, `skip_non_positive=1` rejected as not a `bool`, `color_scale=True`
  with no grid-level default, `reverse` rejected, and the legal cases accepted.
- `test/unit/test_grid_options_builder.py`: `configure_color_scale` writes the
  grid context and omits unset keys; `configure_column(color_scale=…)` merges
  into `context` **without** clobbering a `stRatio` entry already there, and
  without clobbering a `context=` passed in the same call.
- `test/unit/test_public_exports.py`: the four new exports.

### End-to-end

`test/color_scale_fixture.py` owns the data and computes the expected `rgba` for
every cell from the formulas in this document — the convention CLAUDE.md states
for the ratio tests ("never hand-type an expected number"). The fixture is a
second, independently written copy of the arithmetic, which is what catches a
transcription error in a ramp.

`test/grid_color_scale.py` (the app) and `test/test_grid_color_scale.py` (the
test) cover:

1. Each of the three schemes at its default `mode`, on a flat grid.
2. Each of the three non-default `scheme × mode` pairings.
3. Pivot mode, painting group rows.
4. A grid with two displayed group levels — the level-scoped population.
5. Re-scaling after a filter narrows the rows.
6. `skip_non_positive` in both settings.
7. A column carrying its own `cellStyle` is not painted.
8. Footer / grand-total row not painted.

Cells are located by their `row-index` and `col-id` attributes, never by
document order: AG-Grid positions rows absolutely and DOM order does not track
display order.

Colours are read with `getComputedStyle(cell).backgroundColor`, parsed, and
compared channel-by-channel — the RGB channels exactly, alpha within `0.01`, as
browsers reserialise alpha at their own precision.

## Consumer migration (informative)

Not part of this change; recorded because it is what the API is designed
against.

| Today | Becomes |
|---|---|
| `funnel_saj.js_color_gradient_styler` | `scheme="neutral"` |
| `payers.js_column_gradient_styler` + `js_pivot_column_gradient_styler` | `scheme="positive"` — the flat/pivot split disappears |
| `cohort.js_color_gradient_styler` (and its `iap_dash` re-use) | `scheme="diverging"` |
| `show_color_scale` in `TableBlockSettings` | the same boolean, now driving `color_scale=True` instead of selecting a `JsCode` |

Roughly 250 lines of `JsCode` and three test modules that assert against
JavaScript source text go away.

## Deferred to phase 2

- **`reverse`** — a metric direction flag, so a "higher is better" green scale
  does not paint a high `cpi` as good. One more key in the same shallow merge.
  Auto-deriving it from the consumer's metric registry stays on the consumer's
  side; the fork exposes the flag and nothing more.
- **Activation from the columns tool panel** — requires bumping `ag-grid` to
  **36.1**. The fork pins `36.0.0` in both `frontend/package.json` and
  `yarn.lock`, and `getColumnMenuItems()` / `colDef.columnMenuItems` with
  `params.source === "columnsToolPanel"` do not exist in 36.0. The bump follows
  the "When updating AG-Grid" checklist in CLAUDE.md, including keeping
  `ag-charts-enterprise` aligned.
- **Open question for that spec:** a runtime toggle is not part of AG-Grid's
  column state and so does not survive a Streamlit rerun on its own. The two
  candidates are holding it in a React ref (survives a rerun, not a page reload)
  or surfacing it through `collect` so Python can persist it into the block's
  settings.

**Phase 1 needs no AG-Grid bump.**

## Packaging

`ratio-agg` merged into `main` on 2026-08-29 (PR #1), and both `pyproject.toml`
files currently read `2.3.0`. The fork carries no `2.x` tag — the consumer pins
it by branch, so the version is informational — but a feature addition still
takes a minor bump, so this lands as **2.4.0**, with `st_aggrid/pyproject.toml`
and the root `pyproject.toml` bumped together, as the packaging notes in
CLAUDE.md require.

README gains a "Declarative colour scales without JavaScript" section next to
the existing "Declarative aggregation without JavaScript".
