# Declarative Ratio Aggregation — Design

**Status:** validated against a running grid; ready to plan
**Branch:** `ratio-agg` (off `upstream-parity`)
**Date:** 2026-08-10 (validated 2026-08-10)

> **Validation log.** Every claim below marked *(measured)* was checked against
> a live grid running AG-Grid 36.0.0, not reasoned about. The apparatus is
> committed: `test/grid_ratio_js.py` runs the consumer's JavaScript verbatim
> over the reference fixture, `test/ratio_fixture.py` owns the fixture and the
> reference arithmetic, and `test/test_grid_ratio_js.py` pins the result. Four
> sections changed as a result — the `fill_null` default, the value contract,
> the migration's behaviour-change list, and the blocking prerequisite.

## Problem

Ratio metrics (CPI, ARPU, CPM, conversion rates) cannot be aggregated by
aggregating the ratio. A group's ratio is `Σnumerator / Σdenominator`, never the
average of its children's ratios. AG-Grid has no built-in aggregation with that
property, so every consumer writes JavaScript.

The main consumer of this fork (`hitapps_analytics`) does exactly that: a
`ratioSum` aggFunc injected as `JsCode`, driven by a `MetricSpec` dataclass that
already carries the formula declaratively (`num`, `den`, `num_signs`,
`multiplier`, `scale`, `fill_null`). The JavaScript is only an executor for data
the application already has in structured form. It forces
`allow_unsafe_jscode=True` on every grid that shows a ratio.

That JS also has a documented capability gap. `MetricSpec.to_agg_context()`
states that its `{num, num2, den}` shape cannot express signed multi-term
numerators, so callers "should restrict specs to `len(num) <= 2` and
`num_signs` all positive" — and `funnel_saj` maintains a second, different
mechanism because of it.

## What AG-Grid 36 does not solve

AG-Grid 36 added `calculatedExpression` (ColDef) plus the `calculatedColumns`
grid option, implemented by the Enterprise `CalculatedColumnsModule`. It looks
like the answer and is not. Measured on a real grid:

| Setup | Group row value | |
|---|---|---|
| `calculatedExpression`, components aggregated with `sum` | *(empty)* | not evaluated on group rows |
| `calculatedExpression` + `aggFunc: "avg"` | `5.25` | average of leaf ratios — **wrong** |
| custom JS aggFunc over leaves | `2.40` | correct `120/50` |

`calculatedExpression` is a declarative per-row valueGetter. It evaluates on leaf
rows only (verified: leaves showed `10` and `0.5` while the group cell stayed
empty) and has no notion of re-aggregation. Pairing it with a built-in `aggFunc`
silently produces the statistically wrong number.

A second finding shaped the test requirements below: with the data used above,
group B returned `2.50` from both the correct and the incorrect method. Data
where `Σnum/Σden` coincides with `avg(ratio)` cannot discriminate, and a test
built on it passes against a broken implementation.

## Scope

**In:** the `ratioSum` family — `(Σ(signᵢ·numᵢ)·multiplier / Σden)·scale`.
That is ~35 specs in `data_sources/entities/marketing/grid_metrics.py` and 1 in
`ad_placements`.

**Out:** `growthRatio` (a ratio of two ratios — not expressible as `Σnum/Σden`);
the `funnel_saj` pivot-safe valueGetter machinery; all value formatters and
`cellStyle` functions. Those stay on `JsCode`. This feature removes the
aggregation family only.

**Explicitly not built:** a string expression language with a parser. The chosen
scope is fully expressible structurally, and the structured form maps 1:1 onto
the `MetricSpec` fields the consumer already has. A parser would add a grammar,
a syntax-error surface, and a compile step to buy generality nothing in scope
needs. If `growthRatio` is ever brought in scope, revisit — a ratio of ratios is
the case that would justify it.

## Design

### Registration

`AgGridComponent.tsx` registers one named aggregator into the grid's `aggFuncs`
option at mount, merged with whatever the caller supplies. Callers reference it
by name. No `JsCode` crosses the boundary, so grids that only needed unsafe JS
for ratios can drop `allow_unsafe_jscode`.

Aggregator name: `stRatio`. A caller-supplied `aggFuncs` entry of the same name
wins — the built-in is a default, not a reservation — and the override is logged
when `debug` is on, since shadowing it silently would be baffling to debug.

### colDef contract

```python
{
    "colId": "cpi",
    "aggFunc": "stRatio",
    "context": {"stRatio": {"num": ["cost"], "den": ["installs"]}},
}
```

Parameters are nested under a `stRatio` key inside `context` so they cannot
collide with other uses of `colDef.context`.

| Key | Required | Default | Meaning |
|---|---|---|---|
| `num` | yes | — | Field names summed to form the numerator |
| `den` | yes | — | Field names summed to form the denominator |
| `num_signs` | no | all `1` | Per-term signs, e.g. `[1, -1]` for `(a − b)/c` |
| `multiplier` | no | `1.0` | Applied inside the numerator (CPM uses `1000`) |
| `scale` | no | `1.0` | Applied to the final value (sec→min uses `1/60`) |
| `fill_null` | no | `None` | Value when `Σden == 0`; `None` renders an empty cell |

**`fill_null` defaults to `None`, not `0.0`** *(revised after measurement)*.
The JavaScript being replaced returns `null` when `Σden == 0` — its group and
pivot cells are already blank *(measured: campaign B renders an empty ARPP cell
at both grouping levels and in every pivot cell)*. Defaulting to `0.0` would
have flipped those cells to `0.0000` across the consumer's dashboards, which is
a visible data change smuggled in by a refactor. `0.0` remains available per
column for specs that want it.

Note this is deliberately *not* `MetricSpec.fill_null`'s default of `0.0`. The
consumer's two paths disagree today — its Python materialization honours
`fill_null` while its JS aggregation ignores it — so `to_agg_context()` must
pass `fill_null` through explicitly rather than let either default decide.

`num_signs`, when given, must have the same length as `num`.

### Semantics

```
value = ((Σ signᵢ · numᵢ) · multiplier / Σden) · scale       when Σden ≠ 0
value = fill_null                                            when Σden == 0
```

Every field name resolves to the **sum of that field over the node's subtree**.
`num` and `den` are lists, which is what lifts the `len(num) <= 2, all positive`
restriction the current JS carries.

A name may appear in both `num` and `den` — `part / (part + rest)` is how
retention, conversion rate and share-of-total are written, and it is only
expressible once `den` is a list. Each distinct name is therefore summed
**once**, and the two lists then read that shared total. Summing per
occurrence instead would double the shared field and, because the sums are
folded upward, compound the error by `2^depth`.

### Aggregation mechanism

The aggregation value carries its own component sums, and each level folds its
children's sums rather than rescanning leaves:

- leaf group — `params.aggregatedChildren` are data rows; read `row.data[field]`
- higher group — `params.aggregatedChildren` are child groups; read each child's
  stored component sums

Each node is visited once: **O(n)**. The JS being replaced walks
`rowNode.allLeafChildren` at every level, which is O(n × depth).

Two alternatives were rejected. Reading sibling aggregates via
`rowNode.aggData[field]` requires the component columns to exist in the grid with
`aggFunc: "sum"` and depends on column evaluation order, which AG-Grid does not
guarantee. Re-walking leaves at each level is correct but needlessly quadratic in
depth.

### Value contract

The aggregator returns an object:

```
{ value: number | null, sums: {field: number}, toNumber(), toString() }
```

- `toNumber()` returns `value` — the number, or `null`.
- `toString()` renders the display string.
- `sums` carries the components upward; it is the mechanism, not public API.

**`toNumber()`, not `valueOf()`** *(revised after measurement)*. AG-Grid 36
declares this shape as `IAggFuncResult` and documents `toNumber()` as
"the numeric representation of the aggregated value. Used also for sorting";
`ag-stack`'s `_defaultComparator` calls it before comparing, and
`RowNode.getValue` unwraps through it too, so exports, filters and charts see a
number rather than an object. `valueOf()` is not part of any of those paths — it
only takes effect incidentally, when `_defaultComparator` falls through to `<`
and `>`.

That incidental path breaks on nulls, which is the case this feature has to
handle. *(Measured, sorting a group column with one null value in both
directions and reading rows by `row-index`:)*

| Hook | Column without nulls | Column with a null |
|---|---|---|
| `valueOf()` | sorts correctly | **does not reorder at all** |
| `toNumber()` | sorts correctly | orders deterministically |

With `valueOf()`, the null becomes `NaN`, every `NaN` comparison is false, the
comparator returns `0`, and the rows keep their original order in both
directions. With `toNumber()` returning `null`, AG-Grid's own null branch
(`valueA == null → -1`) takes over.

The consumer's existing value formatters already branch on
`typeof v === 'object'`, so they keep working unchanged.

**Null placement uses an explicit comparator.** AG-Grid's native handling puts
nulls first ascending and last descending. This feature places them **last in
both directions**, so scanning for the smallest ratio never wades through empty
cells first. That needs a comparator, which the fork installs itself on every
column whose `aggFunc` is `stRatio`, at the same point it registers the
aggregator — the app never writes one. It orders non-null values numerically
via `toNumber()`. A caller-supplied `comparator` on the colDef is left
untouched.

Because a descending sort negates the comparator's result, "last in both
directions" cannot be expressed by the return value alone; the comparator reads
the `isDescending` argument AG-Grid passes it and flips the null branch to
match.

### Validation

Field names in `num`/`den` that do not appear in **the data** are a Python-side
error raised while building the grid options. An unknown name would otherwise
contribute `0` to a sum and silently skew the ratio — a wrong number with no
error is the worst outcome this feature can produce.

**Against the data, not against `columnDefs`** *(revised — the original rule was
wrong and would have broken the consumer)*. The aggregator reads
`rowNode.data[field]`, so a component only has to be present in the row data; it
does not need a column of its own. Requiring a `columnDef` would reject valid
configurations: of the 12 distinct `num`/`den` fields the consumer's marketing
specs reference, only 5 (`installs`, `cost`, `impressions`, `clicks`,
`conversions`) are declared as columns. The other 7 — `revenue_total`,
`iap_total`, `pu_total`, `ads_total`, `purch_total`, `cost_incent_cohort`,
`cost_incent_predict`, `campaign_target_revenue` — ride in the dataframe as
aggregation inputs only. The `columnDefs` rule would have raised on every grid
that shows an ARPU or ROAS column.

Validation therefore runs where the DataFrame is already in hand, and is skipped
when there is none to check against (`data=None`, or a grid fed entirely through
`grid_options["rowData"]`) rather than guessing.

Structural checks, also Python-side: `num` and `den` non-empty lists of strings,
`num_signs` length matching `num`, numeric `multiplier`/`scale`, and `fill_null`
numeric-or-`None`. A colDef declaring `aggFunc: "stRatio"` with no
`context["stRatio"]` is an error too.

### Boundaries

`aggrid.py` validates and passes `context` through untouched. All arithmetic
lives in the fork's TypeScript. The Python layer gains no knowledge of ratio
semantics beyond the shape of the dict it validates.

## Migration for the consumer

`MetricSpec.to_agg_context()` is rewritten once to emit the new shape — lists
instead of `num`/`num2`, `num_signs` and `fill_null` passed through. The ~36
specs themselves do not change; they already declare these fields. Then
`js_ratio_sum`, its `aggFuncs` registration, and `allow_unsafe_jscode` on the
affected grids are deleted.

### What actually changes on screen

*(Measured against the JavaScript baseline, level by level.)* Three changes, and
no others:

1. **Pivot cells become correct.** Today every pivot cell in a row shows that
   row's total, because `ratioSum` reads `rowNode.allLeafChildren`, which is not
   pivot-aware. On the reference fixture, campaign A shows `10.0000` in both the
   US and DE columns where the correct values are `90.0000` and `1.1111`; the
   pivot grid's total row shows `3.4000` in both country columns instead of
   `8.2727` and `0.5789`. The component columns beside them are right, because
   AG-Grid's built-in `sum` *is* pivot-aware — the ratio is the only thing wrong.
   This is a live defect in the consumer's marketing dashboard whenever a pivot
   column is active, not a regression risk introduced by this work.

2. **Signed numerators become correct.** `ratioSum` adds every numerator term,
   so a `num_signs=(1, -1)` spec rolls up as `(a + b)/c`. On the fixture,
   campaign A's net CPI reads `11.2000` where the signed value is `8.8000` — and
   the leaf rows directly beneath already show the signed value, because leaves
   render the dataframe's precomputed scalar. The group row and its own children
   disagree today.

3. **Pivot row totals and every row-grouping value stay identical.** Verified
   cell by cell on all six fixture columns at both grouping levels and at the
   grand-total row.

The `fill_null` divergence recorded in `MetricSpec` is *not* closed by this
change, and deliberately so. Its Python materialization path honours
`fill_null`, its JS aggregation ignores it and always emits null; picking
`None` as the aggregator's default keeps every existing group and pivot cell
rendering exactly what it renders today. Making the two paths agree is a
separate decision with its own visible consequences — it is a change to what
numbers users see, and it should not ride along inside a refactor.

## Verification

Every ratio test must use data where `Σnum/Σden` differs from `avg(ratio)` at
**every** level under test. That fixture, its reference arithmetic, and the
record of exactly which nodes it *cannot* discriminate now live in
`test/ratio_fixture.py`, guarded by `test/unit/test_ratio_fixture.py`:

```
A/US 900/10   A/DE 100/90   B/US 10/100   B/DE 10/100

campaign A       = 1000/100 = 10.00
campaign B       =   20/200 =  0.10
grand total      = 1020/300 =  3.40   <- correct
avg group ratios =              5.05  <- multi-level trap
avg leaf ratios  =             52.87  <- single-level trap
```

Each cell is split into two rows so pivot cells aggregate too, and so a pivot
cell's value differs from its row's total — without that, an aggregator that
ignores the pivot key still looks right.

The fixture has blind spots and they are declared rather than discovered:
campaign B is fixed at `10/100` in both countries by the spec's own numbers, so
every column denominated by `installs` is degenerate there (`avg == Σ/Σ`), as is
every column whose denominator collapses to zero. `DEGENERATE_NODES` and
`PIVOT_BLIND_CELLS` list them, and a test asserts the measured set equals the
declared set in both directions, so neither the list nor the data can drift
without failing.

Required coverage:

- ratio at one grouping level, two grouping levels, and the grand-total row
- pivot cells, pivot row totals, and the pivot grid's grand-total row
- leaf rows still show the per-row ratio
- `num_signs` with a negative term
- `multiplier` and `scale` non-default
- `Σden == 0` with `fill_null` at `0.0` and at its `None` default
- sort ascending and descending on the ratio column, read by `row-index`
- sort with nulls present, both directions, asserting nulls last in each
- unknown field name raises at build time
- pure-Python unit tests for the validation rules, in `test/unit/`

Browser assertions must read `.ag-row[row-index="N"]`. DOM order does not reflect
visual order — AG-Grid positions rows absolutely, and a probe written against DOM
order produced a false "sorting is broken" result during design.

## Prerequisite: pivot — resolved

**The mechanism holds in pivot.** *(Measured.)* A prototype implementing exactly
the design above — `aggregatedChildren`, with child groups folded through
`child.aggData[pivotResultColumn.getColId()]` — was put behind a pivot
configuration and produced the correct value in every position:

| Position | Prototype | Reference |
|---|---|---|
| pivot cell A/US | `90.0000` | `900/10` |
| pivot cell A/DE | `1.1111` | `100/90` |
| pivot row total, campaign A | `10.0000` | `1000/100` |
| pivot total row, US column | `8.2727` | `910/110` |
| pivot total row, DE column | `0.5789` | `110/190` |
| pivot total row, row total | `3.4000` | `1020/300` |

A debug column exposing `aggregatedChildren.length` and how many carried `data`
confirmed the intended shape at each level: leaf groups receive data rows
(`2:2`), higher groups and the grand-total row receive child groups (`2:0`) and
fold their stored sums, and a pivot row-total column receives all four leaves
(`4:4`) — which is exactly what a row total needs. `IAggFuncParams`'
documentation that "with pivot columns, only rows matching the pivot keys are
included" holds in practice.

No pivot-specific path is needed and no revision to the design follows. The
plan therefore opens with the aggregator itself rather than a spike.

## Known issue, undecided

**`stRatio` shows up in the columns tool panel's aggregation picker on every
grid** *(measured after implementation)*. Registration happens in
`parseGridOptions`, which every grid in this repo passes through, and AG-Grid
builds that picker's option list from `gridOptions.aggFuncs`. So any Enterprise
grid with a `sideBar` columns panel and a value column now offers eight options
instead of seven — and choosing `stRatio` on a column that carries no
`context["stRatio"]` blanks its group values, because the aggregator returns
`null` (verified: the header became `stRatio(X)` and the cell went `3` → empty).

Nothing breaks and no existing grid changes unless a user picks the new entry,
which is why this did not block the feature. The remedies each have a cost and
the choice has not been made:

- Register only when some colDef declares `stRatio`. Cheapest, but a column
  that acquires `aggFunc: "stRatio"` at runtime through `columns_state` would
  find nothing registered.
- Have the aggregator fall back to `sum` (or return the AG-Grid default) when
  no config is present, so a stray selection degrades instead of blanking.
- Leave it, and let grids that care constrain their columns with
  `allowedAggFuncs`.

## Out of scope

`growthRatio`; `funnel_saj`; value formatters; `cellStyle`; a string expression
language; any change to `calculatedExpression` handling. Declarative formatting
(`"format": "currency" | "percent" | "number:2"`) is a plausible follow-up that
would remove the formatter family, but it is a separate feature with its own
design.
