# Declarative Ratio Aggregation — Design

**Status:** approved design, not yet planned
**Branch:** `ratio-agg` (off `upstream-parity`)
**Date:** 2026-08-10

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
| `fill_null` | no | `0.0` | Value when `Σden == 0`; `None` renders an empty cell |

`num_signs`, when given, must have the same length as `num`.

### Semantics

```
value = ((Σ signᵢ · numᵢ) · multiplier / Σden) · scale       when Σden ≠ 0
value = fill_null                                            when Σden == 0
```

Every field name resolves to the **sum of that field over the node's subtree**.
`num` and `den` are lists, which is what lifts the `len(num) <= 2, all positive`
restriction the current JS carries.

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
{ value: number | null, sums: {field: number}, valueOf(), toString() }
```

- `valueOf()` returns `value`, or `NaN` when `value` is null.
- `toString()` renders the display string.
- `sums` carries the components upward; it is the mechanism, not public API.

`valueOf()` is honoured by AG-Grid's sorting — verified by sorting a group column
ascending and descending and reading rows by `row-index` (`0.10, 10.00` then
`10.00, 0.10`, with the grand-total row staying pinned).

The consumer's existing value formatters already branch on
`typeof v === 'object'`, so they keep working unchanged.

**Null ordering needs an explicit comparator.** With `fill_null: None` the value
is null and `valueOf()` yields `NaN`; every comparison against `NaN` is false,
which leaves the relative order of those rows undefined. The fork installs the
comparator itself, on every column whose `aggFunc` is `stRatio`, at the same
point it registers the aggregator — the app never writes one. It orders non-null
values numerically and places nulls last in both sort directions. A
caller-supplied `comparator` on the colDef is left untouched.

### Validation

Field names in `num`/`den` that do not appear in the grid's `columnDefs` are a
Python-side error raised while building the grid options. An unknown name would
otherwise contribute `0` to a sum and silently skew the ratio — a wrong number
with no error is the worst outcome this feature can produce.

Structural checks, also Python-side: `num` and `den` non-empty, `num_signs`
length matching `num`, and numeric `multiplier`/`scale`.

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

The rewrite also closes the `fill_null` divergence recorded in `MetricSpec`:
today the Python materialization path honours `fill_null` while the JS always
emits `0`. After this change both paths agree. Grids whose specs set
`fill_null=None` will start rendering empty cells where they previously rendered
`0` — intended, and worth a scan of those specs before rollout.

## Verification

Every ratio test must use data where `Σnum/Σden` differs from `avg(ratio)` at
**every** level under test. The reference fixture:

```
A/US 900/10   A/DE 100/90   B/US 10/100   B/DE 10/100

group A          = 1000/100 = 10.00
group B          =   20/200 =  0.10
grand total      = 1020/300 =  3.40   <- correct
avg group ratios =              5.05  <- multi-level trap
avg leaf ratios  =             22.83  <- single-level trap
```

Required coverage:

- ratio at one grouping level, two grouping levels, and the grand-total row
- leaf rows still show the per-row ratio
- `num_signs` with a negative term
- `multiplier` and `scale` non-default
- `Σden == 0` with `fill_null` at `0.0` and at `None`
- sort ascending and descending on the ratio column, read by `row-index`
- sort with nulls present, both directions
- unknown field name raises at build time
- pure-Python unit tests for the validation rules, in `test/unit/`

Browser assertions must read `.ag-row[row-index="N"]`. DOM order does not reflect
visual order — AG-Grid positions rows absolutely, and a probe written against DOM
order produced a false "sorting is broken" result during design.

## Blocking prerequisite

**Pivot behaviour is unverified.** The marketing dashboard is a pivot grid, so
pivot is a hard requirement, and the prototype only exercised row grouping.
`IAggFuncParams.aggregatedChildren` documents that "with pivot columns, only rows
matching the pivot keys are included", and `IAggFuncParams` carries a
`pivotResultColumn`, which suggests the mechanism holds — but it has not been
demonstrated.

The implementation plan must open with a spike that puts the prototype behind a
pivot configuration and confirms the ratio is correct in pivot cells, in pivot
row totals, and in pivot column totals. If it does not hold, the design needs a
pivot-specific path and this spec must be revised before building.

## Out of scope

`growthRatio`; `funnel_saj`; value formatters; `cellStyle`; a string expression
language; any change to `calculatedExpression` handling. Declarative formatting
(`"format": "currency" | "percent" | "number:2"`) is a plausible follow-up that
would remove the formatter family, but it is a separate feature with its own
design.
