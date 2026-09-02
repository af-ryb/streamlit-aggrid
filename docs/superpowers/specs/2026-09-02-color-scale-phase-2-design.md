# Declarative Colour Scales, Phase 2 — Design

**Status:** designed against the code, not yet implemented
**Branch:** `color-scale-phase-2` (off `main` at `946b752`)
**Date:** 2026-09-02
**Supersedes:** the *Deferred to phase 2* section of
`2026-08-29-grid-color-scale-design.md`, whose remaining items (`reverse`,
runtime activation) are either delivered here or re-scoped to a later release
(see *Out of scope*).

## Problem

2.4.0 shipped three population-based colour schemes, and eight grids in the
main consumer (`hitapps_analytics`) now declare one instead of shipping a
`JsCode` styler. Four hand-written stylers survive, each because the
mechanism cannot express what it computes:

| Consumer styler | Slot | Why 2.4.0 cannot express it | Task |
|---|---|---|---|
| `js_growth_color_gradient` (`cohort_growth`) | `cellStyle` | Centred on a fixed `1.0` with a ±`1.0` cap. Both 2.4.0 modes anchor on a statistic of the column's own values. | 9.2a |
| `js_best_in_metric_highlight` (`arpu_growth`) | `cellStyle` | Paints only the maximum within a group. There is no ramp; it is a predicate. Its group maximum is computed in pandas into hidden `__max__*` columns. | 9.2b |
| `js_installs_styler` (three identical copies, six call sites) | `cellStyle` | A flat theme-coloured fill. Trivial in itself — but because it sits in the `cellStyle` slot, the built-in can never attach to `installs`, `%_installs`, `ab_group_id`, and neither will the runtime picker planned for 9.3. | 9.2c |
| — (`ab_tests` main pivot) | — | Long-form grid with `metric_name` as the level-0 row group. The 2.4.0 population is scoped by depth, so every level pools retention with ARPU. The page hides its `show_color_scale` control for exactly this reason. | 9.2d |

Separately, 2.4.0 reserved `reverse` (a metric-direction flag) and rejected it
in validation so nobody could depend on it being ignored. Without it a
per-column choice of scheme is useless on the mixed-direction tables
(`marketing` sits on `neutral` only because `cpi` reads down and `roas_*`
reads up).

This release closes all four gaps and delivers `reverse`. Task numbers refer
to the consumer's task tracker (`dash-ai-TASKS.md`, stream 9).

## Scope

**In.** Two new schemes (`rank`, `fill`), one new mode (`anchor`), two new
declaration keys that generalise every scheme (`reverse`, `scope`), and the
keys the new kinds need (`anchor`, `span`, `color`). Python validation for all
of it. A parent-scoped population that leaves the existing level-scoped code
path untouched.

**Out.** Runtime selection of a scheme from the grid's menus (9.3 — depends on
the `useAutoCollect` refactor from 9.1 and on a new state channel through
`collect`; a release of its own). A declarative `getRowStyle` (9.4 — a
different slot and a second declaration; next release, and it will reuse
`fill`'s colour form). Any AG-Grid version bump. The consumer-side migration
itself (informative section at the end). Changing any consumer page from
`neutral` to a directional scheme — 9.2c hands over the lever, pulling it is a
product decision.

**Design rule for the whole release: additive.** Every declaration that is
valid under 2.4.0 resolves to exactly the same colours under this release. A
grid that never writes a new key runs the same code it runs today — this is
literal for the population walk (see *Population*), not merely a promise
about the output.

## Public contract

### Declaration

Unchanged shape: `context["stColorScale"]` at the grid level (defaults only)
and at the column level (the opt-in), merged per key with the column winning.
The merge is what makes this release additive: each new capability is one
more key in the same dictionary, and a runtime picker (9.3) will later change
a declaration and refresh, exactly as 2.4.0 anticipated.

### Keys

| Key | Values | Read by | Default |
|---|---|---|---|
| `scheme` | `"neutral"` \| `"positive"` \| `"diverging"` \| **`"rank"`** \| **`"fill"`** | all | required at one of the two levels, except under `mode: "anchor"` (below) |
| `mode` | `"minmax"` \| `"zscore"` \| **`"anchor"`** | the three ramp schemes | the scheme's own |
| `scope` | **`"level"`** \| **`"parent"`** | `rank`, and ramps under `minmax` / `zscore` — the kinds that consult a population | `"level"` |
| `reverse` | `bool` | ramps and `rank` | `False` |
| `skip_non_positive` | `bool` | ramps and `rank` | the scheme's own |
| `anchor` | number | `mode: "anchor"` | required under that mode |
| `span` | number `> 0` | `mode: "anchor"` | required under that mode |
| `color` | non-empty CSS colour string, e.g. `"var(--secondary-background-color)"` | `fill` | required by that scheme |

**A key a scheme does not read is ignored, not rejected.** A grid-level
default of `mode: "minmax"` must not break a column that says
`scheme: "fill"`, and a grid-level `scope: "parent"` must not break a `fill`
column or an anchored one — `anchor` and `fill` read no population, so
`scope` means nothing to them. Validation still type-checks every key that is present, at
both levels, so a typo never survives.

### Resolution

Per column, in the frontend (`readColorScaleConfig`), with Python's validator
implementing the same rules and being the copy that raises:

```
raw = colDef.context?.stColorScale
raw is undefined | null | false            →  not painted
own    = raw === true ? {} : raw
merged = { ...gridContext.stColorScale, ...own }        // shallow; column keys win

schemeName = merged.scheme ?? (merged.mode === "anchor" ? "diverging" : undefined)
schemeName not a known scheme               →  not painted   (Python: raise)

fill:  color must be a non-empty string     →  { kind: "fill", color }
rank:  → { kind: "rank", scope, reverse, skipNonPositive }
ramp:  mode = merged.mode ?? scheme.defaultMode
       mode === "anchor": anchor finite, span finite and > 0   (else: not painted / raise)
                          → { kind: "anchor", scheme, reverse, skipNonPositive, anchor, span }
       mode minmax|zscore → { kind: "ramp", scheme, mode, scope, reverse, skipNonPositive }

scope           = merged.scope ?? "level"
reverse         = merged.reverse === true
skipNonPositive = merged.skip_non_positive ?? scheme.defaultSkipNonPositive
```

`mode: "anchor"` defaulting the scheme to `diverging` is the one asymmetry:
an anchored scale is almost always "above or below a reference", and the task
that asked for the mode specified this default. It applies only when no
scheme resolves at either level; an explicit `scheme` always wins.

`ResolvedColorScale` becomes a discriminated union on `kind` — `"ramp"`,
`"anchor"`, `"rank"`, `"fill"` — so the cell-style function dispatches on one
field and the TypeScript compiler, not a runtime check, guarantees a `fill`
never reaches `statsFor` and an `anchor` always carries its two numbers.
(`anchor` is a *mode* in the declaration and a *kind* once resolved: the
declaration keeps the user-facing shape the task asked for, the resolved
config keeps the type honest — a ramp kind with optional `anchor?`/`span?`
would let the compiler accept an anchored config missing both.)

### Schemes

| `scheme` | Kind | Default `mode` | Default `skip_non_positive` | Reads as |
|---|---|---|---|---|
| `neutral` | ramp | `zscore` | `True` | unchanged |
| `positive` | ramp | `minmax` | `False` | unchanged |
| `diverging` | ramp | `zscore` | `True` | unchanged |
| **`rank`** | predicate | — | `False` | the best value in the population, and nothing else |
| **`fill`** | constant | — | — | one colour on every cell of the column |

### Python API

`GridOptionsBuilder.configure_column(field, color_scale=...)` is unchanged;
a dict may now carry the new keys.

`GridOptionsBuilder.configure_color_scale` gains the new keys as optional
grid-level defaults and `scheme` becomes optional, because
`configure_color_scale(mode="anchor", anchor=1.0, span=1.0)` with no scheme
is now a complete, valid default set:

```python
def configure_color_scale(
    self,
    scheme: Optional[str] = None,
    mode: Optional[str] = None,
    skip_non_positive: Optional[bool] = None,
    *,
    scope: Optional[str] = None,
    reverse: Optional[bool] = None,
    anchor: Optional[float] = None,
    span: Optional[float] = None,
    color: Optional[str] = None,
) -> None
```

As today, an unset argument is omitted from the written declaration rather
than written as `None`, so a scheme's own default survives the merge.
`scheme` keeps its position, so every existing positional call still works.

Public constants (`st_aggrid/color_scale.py`, re-exported from the package
root and pinned by `test/unit/test_public_exports.py` against the frontend's
literals):

```python
COLOR_SCALE_SCHEMES = ("neutral", "positive", "diverging", "rank", "fill")
COLOR_SCALE_MODES   = ("minmax", "zscore", "anchor")
COLOR_SCALE_SCOPES  = ("level", "parent")          # new
```

### Validation

`validate_color_scale_columns` keeps its two-level structure. Per declaration
(grid level and column level alike):

- Unknown key → `ValueError` naming the key and the full known list. The
  known list is exactly the *Keys* table.
- `scheme` ∉ `COLOR_SCALE_SCHEMES`, `mode` ∉ `COLOR_SCALE_MODES`,
  `scope` ∉ `COLOR_SCALE_SCOPES` → `ValueError`.
- `reverse`, `skip_non_positive` not a `bool` → `ValueError`. Strict `bool`,
  as today: `1` is rejected.
- `anchor` not a finite number, `span` not a finite number or `<= 0` →
  `ValueError`. "Number" is `ratio.py`'s `_is_number` rule (an `int` or
  `float` that is not a `bool`) plus a finiteness check; the predicate is
  hoisted into `st_aggrid/_numbers.py` (`is_number`, `is_finite_number`) and
  `ratio.py` imports it from there rather than keeping its own copy.
- `color` not a `str`, or empty after `strip()` → `ValueError`. No attempt to
  parse CSS: the browser is the only authority on what a colour string means,
  and `var(--x)` cannot be checked from Python anyway.

Per column, on the **merged** declaration:

- No scheme resolves (after the `anchor → diverging` default) → the existing
  "resolves to no valid 'scheme'" error, with its hint extended to mention
  the anchor default.
- Resolved scheme is `fill` and `color` is absent → `ValueError`.
- Resolved scheme is a ramp, resolved mode is `anchor`, and `anchor` or
  `span` is absent → `ValueError`.

Nothing else is a resolution error. In particular `rank` with an explicit
`mode`, or `fill` with `scope`/`reverse`/`skip_non_positive`, validate and are
ignored by the frontend, per *Keys*.

## Normalisation

### `anchor` mode

```
d = (value − anchor) / span
d = clamp(d, −1, 1)
if reverse: d = −d
d == 0            →  not painted
u = |d|           →  intensity in (0, 1]
sign = d < 0 ? −1 : +1
alpha = alphaMin + u · (alphaMax − alphaMin)      // the scheme's linear ramp
rgb   = scheme.rgb(sign, u)
```

No population, no `statsFor`, no cache — the anchor and span are the whole
reference frame. The exact anchor is left unpainted rather than painted at
`alphaMin`: for a growth ratio, `1.0` means "no change", and a faint green
there would assert a direction the number does not have. This matches what
the styler being replaced draws (its alpha is `0` at the centre).

The arithmetic is a new pure function `anchorD(anchor, span, value)` in
`normalize.ts`, returning the clamped signed `d` (before `reverse`), so the
`node` check covers it. `Normalized` gains `mode: "anchor"` with `raw = d`
and `intensity = |d|`; `colorFor` takes `u` from `intensity` and the sign
from `raw`, and never consults `zRamp` under this mode — the piecewise
z-ramps are z-score shapes and have no meaning on a linear deviation.

Under `neutral` or `positive` the sign is ignored (single hue) and `u` is the
intensity — the same non-default pairing rule 2.4.0 applies to `minmax`.
`skip_non_positive` applies as for any ramp, so under `diverging`'s default a
ratio of exactly `0` is unpainted; a consumer that needs it painted sets
`skip_non_positive: False`.

### `reverse`

Applied to the normalised value, after the gates and before colour:

| Kind / mode | Effect of `reverse: True` |
|---|---|
| ramp, `minmax` | `t → 1 − t` |
| ramp, `zscore` | `z → −z` (the dead zone and uniformity gate are symmetric, so applying them first is equivalent) |
| ramp, `anchor` | `d → −d` |
| `rank` | best = minimum instead of maximum |
| `fill` | none |

On a single-hue scheme (`neutral`, `positive`) it is visible only under
`minmax`: under `zscore` and `anchor` those schemes take their intensity from
the magnitude of the deviation alone, so the flag changes nothing. Documented
in README; not an error, because a grid-level `reverse` default must be
allowed to coexist with a `neutral` column.

### Where each piece of the arithmetic lives

`normalize.ts` and `schemes.ts` stay import-free and are exercised by
`__checks__/*.check.ts` under plain `node`. `reverse` is applied in
`index.ts` between normalisation and `colorFor` — it is a one-line sign or
complement flip, and keeping it out of the pure modules keeps their existing
checks untouched.

## Schemes

### `rank`

A predicate over the same population the ramps use (same `scope`, same
`skip_non_positive`, same cache entry):

```
value = extractValue(params.value);   null → not painted
skipNonPositive && value <= 0         → not painted
stats = statsFor(...);  !stats || stats.count < 2   → not painted
best  = reverse ? stats.min : stats.max
value === best                        → RANK_STYLE, else not painted
```

`RANK_STYLE` is `{ backgroundColor: "rgba(35, 175, 40, 0.35)", fontWeight: 600 }`,
where the RGB is `SCHEMES.diverging.rgb(+1, 1)` — the saturated end of the
diverging green — computed from the scheme rather than typed, so the two
cannot drift. `fontWeight` reproduces the styler being replaced; it is the
first built-in style with a second CSS property, and AG-Grid's `CellStyle`
type is an arbitrary CSS dictionary, so nothing widens.

Equality is exact. Both sides come from the same `api.getCellValue` walk, so
the maximum *is* one of the values; the `1e-9` tolerance in the retired
styler existed because it compared a pandas-computed maximum with a
JavaScript value. Ties are all painted, as before.

A population of one is unpainted: "best of one" carries no information, and
this is the same rule the ramps already apply through their spread gates
(`max > min`, `sd > 0`). The retired styler painted it; see *Behaviour
changes*.

### `fill`

Returns `{ backgroundColor: color }` for **every** cell of the column,
including group rows, footers, pinned rows and empty cells. This is the one
kind that bypasses the footer/pinned guard the others share: a fill marks a
column as structural, and a stripe that stopped at the grand total would be
a visible regression against the styler it replaces, which painted
everything.

The colour string is passed through verbatim. A theme variable is written as
`var(--secondary-background-color)` and resolved by the browser against the
grid's ancestors, which under CCv2's no-iframe delivery includes Streamlit's
own `:root` — no `getComputedStyle`, no colour parsing. (Inside an iframe the
variable would not be visible and the fill would be transparent; not this
component's situation, noted so nobody debugs it later.)

## Population

### `scope: "level"` — unchanged

The 2.4.0 rule, on the 2.4.0 code: the same column, the same `node.level`,
after filter and sort; grand total and pinned rows neither painted nor
counted. Cache key `${colId}:${level}:${skipNonPositive}`. The walk that
fills it is not edited.

### `scope: "parent"`

The population is the rows with the same `node.parent` — the row's siblings.
Level 0's parent is the root node (`level === -1`), and rows whose parent is
the root are **not painted and not counted** under this scope by the kinds
that consult a population (`anchor` and `fill` ignore `scope`): they are the
groups themselves, and comparing them across is precisely what a consumer
choosing this scope is declining to do (in the long-form `ab_tests` grid the
level-0 rows are unlike metrics; in `arpu_growth` the retired styler skipped
them explicitly with `if (!params.data) return null`). A flat grid under
`scope: "parent"` therefore paints nothing — the README says so, next to the
"nothing to compare against" paragraph.

Membership is tested by object identity (`row.parent === node.parent`)
during the walk. The **cache key** needs a string, and it is the chain of
group keys upward from the parent, `JSON.stringify([parent.key,
grandparent.key, …])` stopping at the root — not `node.id`, which is not
guaranteed to survive every model rebuild, and not a positional index. Group
keys are unique among siblings and each level groups on one field, so the
chain identifies a parent unambiguously; `JSON.stringify` makes a key that
contains a separator unambiguous too.

**One walk fills every parent.** A miss for `(colId, parent-scope, skip)`
runs `forEachNodeAfterFilterAndSort` once, bucketing each qualifying row's
value by its parent (a `Map<IRowNode, number[]>`), then writes one `Stats` — or
`null` for a parent with no qualifying values — per parent into the cache
under that parent's chain key, and the requested key as `null` if its parent
was never seen by the walk. The cost of a generation
is therefore one pass per painted column, the same as level scoping — not
one pass per group. A naive "walk on every miss" would be `O(groups × rows)`
and would show on the long-form pivot this exists for.

Everything else is shared with level scoping: `clearStats` on `modelUpdated`
and ahead of both `redrawRows` sites, the animation-frame `refreshCells`, the
`WeakMap` per grid, `extractValue`, and `api.getCellValue`.

`statsFor`'s signature changes from `(api, column, level, skipNonPositive)`
to `(api, column, node, scope, skipNonPositive)`; the node is needed for the
parent and the level is read from it.

## Frontend architecture

| File | Change |
|---|---|
| `colorScales/schemes.ts` | `SchemeName` widens to five; `RampSchemeName` is the old three and `SCHEMES` stays keyed by it. `ColorScaleMode` gains `"anchor"`; new `PopulationScope`. `SCHEME_NAMES`, `MODE_NAMES`, new `SCOPE_NAMES` — the literals Python pins. `RANK_STYLE`. `colorFor` gains the `anchor` branch. |
| `colorScales/normalize.ts` | `anchorD`. |
| `colorScales/population.ts` | New `statsFor` signature; `parentPath`; the bucketed parent walk alongside the untouched level walk; `isTopLevel(node)`. |
| `colorScales/index.ts` | `readColorScaleConfig` returns the `kind` union and implements *Resolution*. `stColorScaleCellStyle` reads the config first, returns the fill immediately, then applies the footer/pinned guard and dispatches on `kind`. `reverse` applied between normalisation and colour. `registerColorScales`, `attachColorScaleInvalidation`, `paintedColumnIds`, `callerCellStyleSource`: unchanged. |
| `colorScales/__checks__/normalize.check.ts` | `anchorD`: both clamps, the exact anchor, both signs, a span that does not divide evenly. |
| `colorScales/__checks__/schemes.check.ts` | `colorFor` under `anchor` for all three ramp schemes at `u = 1` both signs and at a mid `u`; `zRamp` provably not consulted (`diverging` at `d = 0.5` equals its linear alpha, not its z-ramp alpha); `RANK_STYLE` equals `diverging.rgb(+1, 1)` at alpha `0.35`. |

### Attachment

Unchanged. `registerColorScales` still attaches on `readColorScaleConfig(def)
!== null` and still yields to a caller-supplied `cellStyle` from any of the
three sources, with the same logging. A `fill` column therefore *also* loses
to a caller `cellStyle` — which is the whole point of 9.2c: once the consumer
expresses its fills as declarations, the slot is free for everything else.

### Cell style

```
config = readColorScaleConfig(params.colDef, params.context);  null → null
config.kind === "fill"                                  → { backgroundColor }
node.footer || node.rowPinned != null                   → UNPAINTED
value = extractValue(params.value);  null → UNPAINTED
config.skipNonPositive && value <= 0                    → UNPAINTED
config.kind === "anchor"                                → raw = anchorD(...)   (no population)
else:
    config.scope === "parent" && isTopLevel(node)       → UNPAINTED
    stats = statsFor(api, column, node, config.scope, config.skipNonPositive);  null → UNPAINTED
    config.kind === "rank"                              → (see Schemes / rank)
    raw = minmaxT | zScore;  null → UNPAINTED
raw = reverse ? flip(raw) : raw;   anchor && raw === 0  → UNPAINTED
→ { backgroundColor: colorFor(scheme, normalized) }
```

`UNPAINTED` is `{backgroundColor: "", fontWeight: ""}` — ag-grid-react keeps
a cell's previous inline style when the callback returns `null`, so an
unpainted outcome must clear explicitly; only "no declaration resolves"
returns `null`.

## Behaviour changes against the JavaScript being replaced

Stated here so the consumer's golden runs are read correctly.

- **`cohort_growth` colours change.** The retired gradient painted
  `rgb(0,160,0)` / `rgb(200,30,30)` with alpha `0 → 0.45`; the anchored
  `diverging` scale paints `rgb(35,190−15u,40)` / `rgb(240−15u,18,15)` with
  alpha `0.1 → 0.7`. Same sign, same clamp, same unpainted centre; visibly
  stronger colour. Chosen deliberately (owner decision, 2026-09-02): one
  palette across the cohort family, rather than a fourth palette kept alive
  for one page.
- **`arpu_growth` highlight colour changes** from `rgba(0,160,0,0.35)` to the
  diverging green at the same alpha; `fontWeight: 600` is kept. A metric with
  a single A/B group no longer highlights it.
- **`installs` fills are pixel-identical**: the same variable, now resolved by
  the browser instead of read through `getComputedStyle`.
- **`rank` recomputes after filtering and sorting**, like every population
  here; the retired styler compared against a maximum precomputed in pandas,
  which never moved.
- **The eight 2.4.0 grids are unchanged**, by construction: they write none
  of the new keys and run the unedited level-scoped walk.

## Edge cases

- **`span` far larger than the data's spread** paints everything faint;
  **far smaller** clamps everything to full intensity. Both are the
  declaration's meaning, not gates.
- **`anchor` outside the data's range** gives a one-sided ramp. Fine.
- **`−0`.** `reverse` on `d = 0` yields `−0`; `−0 === 0`, so the exact anchor
  stays unpainted.
- **`rank` on aggregated group rows.** `extractValue` unwraps
  `IAggFuncResult` through `toNumber()` on both sides of the comparison, so
  equality holds for the winning group row.
- **`scope: "parent"` under pivot mode.** Pivot columns change what a cell
  *contains*; the row tree, and therefore the parent, is the same.
- **`scope: "parent"` with `groupHideParentOfSingleChild`.** The population
  is model-based, not display-based: a hidden single-child parent still
  scopes its one child, which then has a population of one and is unpainted
  under every kind. Consistent with "nothing to compare against".
- **Tree data.** The parent chain works the same way; not tested in this
  release.
- **A `fill` column with a `valueFormatter` or cell renderer.** Irrelevant
  to a background; painted like any other cell.
- **`reverse` on a grid-level default with a `neutral` column.** Validates,
  no visible effect on that column, documented.

## Testing

### Python units (`test/unit/`)

`test_color_scale_validation.py` gains one test per rule in *Validation*:
each new key accepted with a legal value and rejected with each illegal shape
(`reverse=1`, `span=0`, `span=-1`, `anchor=float("nan")`, `anchor=True`,
`color=""`, `color=None`, `scope="depth"`, `mode="anchor"` without
`anchor`/`span`, `scheme="fill"` without `color`); the anchor-defaults-to-
diverging resolution; the ignored-keys rule (a `fill` column under a grid
default carrying `mode`, `scope` and `skip_non_positive` validates); the
builder writing each new key and omitting each unset one; and
`configure_color_scale()` with no scheme producing a defaults-only entry
that a bare `color_scale=True` column still cannot resolve (the existing
error, unchanged).

`test_public_exports.py` pins the widened tuples and the new
`COLOR_SCALE_SCOPES`, and its `__all__` check gains the new name.

### Node checks

As listed under *Frontend architecture*. Run with
`node <path>.check.ts`, as today.

### End-to-end

`test/color_scale_fixture.py` stays the single owner of the arithmetic:

- `COLOR_SCALE_ROWS` gains a `ratio` column — `0.5, 0.9, 1.0, 1.1, 1.5, 2.5`
  — so an anchor of `1.0` with a span of `1.0` exercises both signs, the exact
  anchor, and the clamp (`2.5 → +1`), in one column. Existing columns are
  untouched, so no existing assertion moves.
- `expected_rgba` gains `anchor`, `span`, `reverse` keyword arguments and
  implements *Normalisation* independently. Scope is not a parameter: the
  caller passes the population, and a new `region_values(region, field)`
  helper gives it the parent-scoped one.
- New `expected_rank(values, value, *, reverse=False, skip_non_positive=False)
  -> bool` and `RANK_RGBA = (35, 175, 40, 0.35)`, derived in the fixture the
  same way the frontend derives it.
- `is_scheme_color` learns `rank`, so `assert_unpainted` works for it.

`test/grid_color_scale.py` gains two grids; grids 0–4 keep their indices and
the `go_to_app` wait moves from five root wrappers to seven.

**Grid 5 — flat, the new kinds.** Over the fixture, one column per case:

| `colId` | Declaration | Asserts |
|---|---|---|
| `anchor_div` | `{scheme: diverging, mode: anchor, anchor: 1.0, span: 1.0}` on `ratio` | DE, FR red at their `d`; IT unpainted; CA, NY green; TX clamped to full |
| `anchor_default` | `{mode: anchor, anchor: 1.0, span: 1.0}` on `ratio`, no scheme at either level | identical to `anchor_div` |
| `anchor_rev` | `anchor_div` + `reverse: true` | the mirror image |
| `anchor_pos` | `{scheme: positive, mode: anchor, anchor: 1.0, span: 1.0}` | single hue, intensity `|d|`, IT unpainted |
| `rev_minmax` | `{scheme: positive, reverse: true}` on `metric_a` | DE darkest, TX palest |
| `rev_zscore` | `{scheme: diverging, reverse: true}` on `metric_a` | DE green, TX red, the dead zone unchanged |
| `rank_max` | `{scheme: rank}` on `metric_a` | TX painted `RANK_RGBA` with `font-weight: 600`; every other row unpainted |
| `rank_min` | `{scheme: rank, reverse: true}` on `metric_a` | DE only |
| `fill_lit` | `{scheme: fill, color: "rgb(4, 5, 6)"}` on `metric_a` | every row `rgb(4, 5, 6)` |
| `fill_var` | `{scheme: fill, color: "var(--st-aggrid-test-fill)"}` with the variable set to `rgb(7, 8, 9)` on `:root` by an `st.markdown(<style>)` in the app | every row `rgb(7, 8, 9)` — the variable resolves through the no-iframe host |

**Grid 6 — row-grouped by region, grand total at the bottom, the scopes.**

| `colId` | Declaration | Asserts |
|---|---|---|
| `level_pos` | `{scheme: positive}` on `metric_a`, `aggFunc: sum` | the 2.4.0 picture (control column) |
| `parent_pos` | `{scheme: positive, scope: parent}` | EU leaves scaled `100..300`, US leaves `400..600` — DE and CA both palest, IT and TX both darkest; the two group rows **unpainted** (parent is root) |
| `parent_rank` | `{scheme: rank, scope: parent}` | IT and TX painted; group rows unpainted |
| `level_rank` | `{scheme: rank}` | TX only among leaves; US among group rows |
| `fill_grouped` | `{scheme: fill, color: "rgb(4, 5, 6)"}` | both group rows, all six leaves **and the grand total** painted |

Plus one interaction test. The grouped `region` column is hidden, so the
filter goes through a visible one: `metric_b` carries a floating
`agNumberColumnFilter` with `filterParams: {defaultOption: "lessThan"}`,
and typing `15` keeps DE, FR, IT (`-5, 0, 10`) and drops every US row.
Keeping EU rather than US is deliberate: the surviving leaves keep their
row indices (`1..3`), so FR's `level_pos` cell changing colour in place is a
usable repaint signal, the same one `test_filtering_rescales_the_column`
already relies on. After that, `parent_pos`'s EU leaves keep exactly the
colours they had — their population did not change — where `level_pos`'s
re-scale to `100..300` (the 2.4.0 behaviour grid 0 already pins, now
observed side by side). This is the one property of parent scoping that a
static grid cannot show.

And one transition test: a cell that is `level_rank`'s winner while the grid
is filtered must lose the highlight when the filter is cleared and another
row becomes the winner — the case where returning `null` from `cellStyle`
would leave a stale second winner on screen.

Every expected colour comes through `expected_rgba` / `expected_rank` / the
fixture's constants, never a literal in the test; comparison stays on the
8-bit alpha grid via the existing `assert_painted`.

## Consumer migration (informative)

Not part of this release; recorded so the fork's README and the consumer's
`web_app/docs/grid/color-scales.md` say the same thing.

- **`cohort_growth`** — `color_scale={"mode": "anchor", "anchor": 1.0,
  "span": 1.0}` when `ctx.color_scale`; delete `js_growth_color_gradient`;
  rewrite `test_grid_declarations.py` from "styler present" to "declaration
  present".
- **`arpu_growth`** — `color_scale={"scheme": "rank", "scope": "parent"}`
  when `ctx.color_scale`; delete `js_best_in_metric_highlight` and all three
  `__max__*` sites (the pandas `transform("max")`, the hidden colDefs, the
  read from `params.data`).
- **`installs` / `%_installs` / `ab_group_id`** (six call sites) —
  `color_scale={"scheme": "fill", "color": "var(--secondary-background-color)"}`,
  unconditionally: a structural fill is not a colour *scale* and should not
  follow `show_color_scale`. Delete the three copies of `js_installs_styler`.
  Both consumer helper paths (`cell_style=` on `configure_metric_column` and
  on `add_metric_columns`) need a `color_scale=` dict at those sites.
- **`ab_tests`** — `gb.configure_color_scale(scheme=..., scope="parent")`;
  remove `json_schema_extra={"popover": False}` and its docstring from
  `TableBlockSettingsAbTests`; the pick of scheme is the page's.
- **Golden run** of all eight 2.4.0 pages after upgrading, even though
  nothing in their path changed — the doc's own rule for anything that
  touches `population.ts`.

## Packaging

Both `pyproject.toml` files and `uv.lock` move to **2.4.1**, tagged through
`scripts/release.sh` per the release procedure. Strictly, new schemes and
keys are a minor bump; `2.4.x` is the owner's numbering for the colour-scale
line and is followed here.

README's "Declarative colour scales without JavaScript" section gains the
new schemes, modes and keys in its two tables, a "Reverse" paragraph, a
"`scope: parent`" paragraph next to "What a column is compared against"
(including "a flat grid paints nothing under it"), and a "`fill`" paragraph
under "Interaction with `cellStyle`". CLAUDE.md's *Key Design Decisions*
bullet on colour schemes is updated to five schemes, three modes, two scopes.

The frontend is rebuilt (`corepack yarn build`; the content-hashed bundle
shows as a delete plus an add), and the full e2e suite runs, not only the
colour-scale file: `population.ts` is on the path of every painted grid.
