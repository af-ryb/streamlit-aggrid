# Request: declarative ratio-of-ratios (`stRatio` follow-up P1)

**Date:** 2026-08-11
**Raised by:** the `hitapps_analytics` marketing pilot (branch `aggrid-36`), which
migrated 217 ratio columns to `stRatio` and validated them in the browser.
**Status:** request — not designed, not scheduled.
**Related:** `2026-08-10-declarative-ratio-aggregation-design.md` (the `stRatio`
feature this extends), its plan's "Follow-up: consumer migration".

## Why this exists

The pilot worked. 217 of the marketing pivot's 292 metric columns now compute
`Σnum/Σden` from a declaration and are correct at every level — leaf, group,
pivot cell, pivot row total, grand total — verified against the deployed
dashboard: no rendering, value or sorting differences, and saved views restore
intact.

The remaining **45 columns cannot be expressed** and stayed on hand-written
JavaScript. They are the marketing `growth` family (`GROWTH_<from>_<to>_{ADS,IAP,TOTAL}`,
15 cohort-day pairs × 3 revenue splits), and they still carry the exact bug
`stRatio` was built to fix: their aggregator sums over
`params.rowNode.allLeafChildren`, which under `pivotMode` is the whole row's leaf
set, so **every pivot cell shows its row's total instead of the cell's own
value**.

That is now the worse failure mode. Before the pilot, every ratio pivot cell in
that grid was uniformly wrong, and a user could distrust the pivot as a whole.
After it, 217 columns are right and 45 sit beside them in the same grid, wrong,
with nothing in the UI distinguishing the two groups.

A second consequence: the consumer cannot drop `allow_unsafe_jscode` while these
45 columns exist, so the "no JavaScript for ratios" property the feature
advertises is not reachable for its largest consumer.

## What the columns compute

`growthRatio` is an **install-weighted ARPU ratio between two cohort days** — a
ratio of two ratios:

```
value = (Σ num_to / Σ den_to) / (Σ num_from / Σ den_from)
```

The current JavaScript reads four field names from `colDef.context` and sums
each over the node's leaves:

```python
# consumer side, per column
extra_agg_context = (
    ("num_from", "ads_for_0"), ("den_from", "installs_for_0"),
    ("num_to",   "ads_for_1"), ("den_to",   "installs_for_1"),
)
```

Null rules the current implementation uses, which any replacement must preserve
or deliberately change:

- `arpu_from = Σden_from > 0 ? Σnum_from / Σden_from : null`
- `arpu_to` likewise
- `value = (arpu_from != null && arpu_to != null && arpu_from > 0) ? arpu_to / arpu_from : null`

Note the asymmetry: a zero-or-negative *from* denominator **and** a
non-positive `arpu_from` both yield an empty cell. Averaging the children's
growth ratios is not an option — it over-weights small cohorts with noisy leaf
ratios, which is why this is install-weighted rather than a mean.

## Why `stRatio` cannot express it

`stRatio` computes `((Σ signᵢ·numᵢ) · multiplier / Σden) · scale`: sums of
fields over the node's subtree, in a single fraction. A ratio of ratios reduces
to

```
(A/B) / (C/D) = (A·D) / (B·C)
```

— a **product of sums** in both numerator and denominator. There is no
assignment of field names to `num`/`den` that produces it, with or without
`num_signs`, `multiplier` and `scale`. This is a genuine expressiveness gap, not
a missing convenience.

## Two candidate shapes

### A — a dedicated `stRatioOfRatios` aggregator

```python
{
    "colId": "GROWTH_0_1_ADS",
    "aggFunc": "stRatioOfRatios",
    "context": {"stRatioOfRatios": {
        "from": {"num": ["ads_for_0"], "den": ["installs_for_0"]},
        "to":   {"num": ["ads_for_1"], "den": ["installs_for_1"]},
    }},
}
```

Narrow, obvious to read, and a near-mechanical port for the existing consumer.
Costs a second aggregator, a second validator and a second comparator wiring —
or a shared one, if the two are factored together.

### B — let `stRatio`'s `num`/`den` accept a nested declaration

```python
{
    "colId": "GROWTH_0_1_ADS",
    "aggFunc": "stRatio",
    "context": {"stRatio": {
        "num": [{"num": ["ads_for_1"], "den": ["installs_for_1"]}],
        "den": [{"num": ["ads_for_0"], "den": ["installs_for_0"]}],
    }},
}
```

One aggregator, one validator, one comparator, and it composes further (a ratio
whose numerator mixes a plain field and a sub-ratio). The cost is that `num`
becomes a heterogeneous list and the null rules multiply: what does a null
sub-ratio contribute to a sum of terms?

**Recommendation: A.** The pilot's evidence is that this shape has exactly one
consumer pattern with no sign of a third level, and B pays for generality that
nothing has asked for — while making the common single-fraction case harder to
read and validate. If B is chosen anyway, restrict nesting to one level and say
so in the docs.

## Semantics a design must pin down

The `stRatio` work established these; a sibling aggregator must match rather
than reinvent:

- **Pivot folding.** `stRatio` resolves its column id through
  `params.pivotResultColumn ?? params.column` so a pivot cell aggregates its own
  leaves. The whole point of this request is that the current JS does not.
- **Zero denominators.** `stRatio` gates on `denominator !== 0`, the retired
  marketing JS gated on `den > 0`. The pilot recorded that difference as a real
  behaviour change for negative denominators (network credits/refunds). Decide
  the rule here explicitly for both the inner ratios and the outer division, and
  state it — do not inherit it by accident.
- **`fill_null`.** `stRatio` renders an empty cell when the result is undefined
  unless `fill_null` says otherwise. Same key, same default.
- **The value object.** AG-Grid 36's `IAggFuncResult` with `toNumber` (not
  `valueOf` — the `stRatio` work found that `valueOf` leaves a column containing
  a null unsorted).
- **Sorting.** The same numeric comparator with empty cells last in both
  directions, and the same "a `comparator` the caller set is left alone" rule.
- **Validation.** The Python-side field-existence check, now over four field
  lists instead of two, with the same "only when `AgGrid` is called with a
  DataFrame" caveat.
- **Totals.** Correct in pivot row totals and grand total rows, which for a
  ratio of ratios means re-deriving both inner ratios at that node — not
  combining the children's outer values.
- **`treeData`.** Out of scope, as for `stRatio`.

## Tests

Follow the convention the `stRatio` work established: the fixture owns the data
*and* the arithmetic, and declares the nodes it cannot discriminate — no
hand-typed expected numbers. `test/ratio_fixture.py`, `test/grid_ratio_builtin.py`
and `test/grid_ratio_js.py` are the models.

The discriminating case this feature needs and `stRatio`'s fixture does not
have: a pivot where a row's overall growth and one cell's growth differ in
*direction*, so a test cannot pass by accidentally reading the row total.

## Consumer-side work this unblocks

In `hitapps_analytics`:

1. `MetricSpec` gains a way to express the four-field shape (today it is
   `agg_func_override="growthRatio"` plus `extra_agg_context`, which exists
   precisely because the declaration had nowhere else to live).
2. `web/dashboards/marketing/js_funcs.py` loses `js_growth_ratio`; the marketing
   grid's `aggFuncs` registration becomes empty.
3. With no `JsCode` aggregator left, `allow_unsafe_jscode` can finally be
   evaluated for that grid — the value formatters are the only remaining
   `JsCode`, and they are replaceable with `valueFormatter` strings or a
   built-in.
4. The 45 columns stop disagreeing with the 217 beside them.

## Out of scope

Value formatters; `cellStyle`; a general expression language over sums;
`treeData`; anything about the other four `hitapps_analytics` grids, which are
on `ratioAgg` and read the valueGetter's structured object rather than any
declaration.
