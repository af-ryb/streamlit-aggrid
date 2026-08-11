# Declarative Aggregation: Closing the JavaScript Gap

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every custom aggregation in `hitapps_analytics` expressible as a declaration, so a metric definition contains no JavaScript. Today `stRatio` covers `Σnum/Σden`; this plan adds the three shapes an exhaustive inventory of the consumer found it cannot express, plus the three small follow-ups the pilot raised.

**Architecture:** One shared folding core (`aggFuncs/foldSums.ts`) owns child folding, pivot column-id resolution, the sort comparator and registration. Three thin aggregators sit on it — `stRatio`, `stRatioOfRatios`, `stWeightedAvg` — each contributing only a per-leaf contribution function and a final arithmetic step. All three return the same `IAggFuncResult` shape, so any of them folds any child. Python's only role stays what it is today: reject a malformed or unresolvable declaration before it reaches the browser.

**Tech Stack:** TypeScript / React / Vite / AG-Grid 36.0.0 Enterprise · Python 3.13 · Streamlit · pytest + Playwright.

**Design specs:** `docs/superpowers/specs/2026-08-11-ratio-of-ratios-request.md` (P1) and `docs/superpowers/specs/2026-08-11-stratio-followups-small.md` (P2/P3/P4). Read the P1 spec's "Semantics a design must pin down" before Task 5. The predecessor plan is `docs/superpowers/plans/2026-08-10-declarative-ratio-aggregation.md`; its Task 2–4 texts are the model for how an aggregator is built and tested here.

## Global Constraints

- **Names.** Aggregator `stRatioOfRatios` ⇄ context key `colDef.context["stRatioOfRatios"]`; aggregator `stWeightedAvg` ⇄ `colDef.context["stWeightedAvg"]`. Aggregator name and context key are always the same string, as with `stRatio`.
- **Zero rule: `!== 0`, everywhere, in every aggregator.** Decided, not inherited. Both inner ratios of `stRatioOfRatios` gate on `denominator !== 0`, and the outer division gates on `from_ratio !== 0`. The JavaScript being replaced gated on `> 0` in all three places. **This is a deliberate behaviour change** — a group whose *from*-period ARPU is negative (network credits, refunds) now renders a negative growth ratio where today the cell is empty. It must be pinned by a fixture column and named in the README, not discovered in production.
- **`fill_null` defaults to `None`** (an empty cell) in every aggregator, same key, same semantics as `stRatio`.
- **Value objects expose `toNumber()`, never `valueOf()`.** `valueOf()` leaves a column containing a null completely unsorted — measured, not theorised.
- **Nulls sort last in both directions**, via the shared comparator. A caller-supplied `comparator` is always left alone.
- **Folding, never re-walking.** Every aggregator folds `params.aggregatedChildren` — leaf children off `child.data`, group children off their stored `sums` under `(params.pivotResultColumn ?? params.column).getColId()`. Re-walking `allLeafChildren` is quadratic in depth *and* pivot-blind; that blindness is the exact defect this plan exists to remove.
- **Field names are validated against the DataFrame, never against `columnDefs`** — an aggregation input does not need a column. The check only runs when `AgGrid` is called with a DataFrame; that caveat is documented per aggregator.
- **`test/ratio_fixture.py` is the single source of expected numbers.** Anything looping over columns or levels derives its expectation from the fixture's evaluators, never from a typed-out table. A small number of hand-typed literal anchors is deliberate and required — they are the only thing standing between the suite and a fixture that is itself wrong. Where a task gives a literal, keep it.
- **No new frontend dependencies and no JS test runner.** This repo has none by design. TypeScript is verified through the browser: `test/unit/` is pure Python, everything else is Playwright e2e driving a standalone Streamlit app of the same name (`test/conftest.py` auto-marks it `e2e`).
- **Read grid rows by `row-index`, never DOM order.** AG-Grid positions rows absolutely; a probe written against document order has already produced one false "sorting is broken" result in this repo. Use `test/grid_dom.py`.
- **Frontend rebuild after every TypeScript change:**
  ```bash
  cd st_aggrid/frontend && COREPACK_ENABLE_DOWNLOAD_PROMPT=0 corepack yarn build
  ```
  `yarn` is not on PATH — always `corepack yarn`. `build` wipes `build/` and emits content-hashed filenames, so `git status` shows a delete + an add, not a modify. `st_aggrid/frontend/build/` is committed on purpose. Each glob in `st_aggrid/component.py` must match exactly one file.
- **Fast Python loop:** `pytest -m "not e2e"` (seconds). **Browser loop:** `pytest test/test_<name>.py`.
- **`test/grid_ratio_builtin.py` and `test/test_grid_ratio_builtin.py` are frozen.** They are the regression baseline for Task 1's refactor. New aggregators get new apps. Touch them only if Task 2's fixture change forces a mechanical update, and say so in the report.

## Already in place

Committed before this plan — do not recreate:

| File | Role |
|---|---|
| `st_aggrid/frontend/src/aggFuncs/stRatio.ts` | The `stRatio` aggregator, comparator and registration |
| `st_aggrid/ratio.py` | Declaration validation, called once from `aggrid.py:353` |
| `test/ratio_fixture.py` | Row data, `RatioSpec`, `evaluate()`, `evaluate_legacy()`, `expected()`, `as_text()`, and the declared blind spots |
| `test/grid_dom.py` | `read_rows(page, grid_index)` and `grand_total_row(rows)` — row-index-keyed reading |
| `test/grid_ratio_builtin.py` / `test_grid_ratio_builtin.py` | The 5-grid `stRatio` app and its 18 tests |
| `test/unit/test_ratio_fixture.py` | Guards the fixture's arithmetic and its discriminating power |
| `test/unit/test_ratio_validation.py` | The `stRatio` validation rules |

`test/conftest.py` puts `test/` on `sys.path`, so `from ratio_fixture import ...` works from `test/`, from `test/unit/`, and from a Streamlit app launched as a subprocess.

## Coverage this plan delivers

| JS aggregator in `hitapps_analytics` | Grids | Replaced by |
|---|---|---|
| `ratioSum` (217 cols) | marketing | `stRatio` — already shipped |
| `ratioAgg` (58 cols) | funnel, funnel_saj, ad_placements, payers | `stRatio` |
| `valuePerInstall`, `installShare`, ab_tests inline | cohort, cohort_comparison, iap_dash, cohort_conversion, ab_tests | `stRatio` |
| `growthRatio` (45 cols) | marketing | **`stRatioOfRatios`** — Task 5 |
| `shareAgg` (1 col) | payers_intelligence | **`stRatio.den_const`** — Task 3 |
| `installWeightedAvg` | cohort_growth, ab_tests·arpu_growth | **`stWeightedAvg`** — Task 6 |
| `installsAgg` / `usersAgg` (4 cols) | funnel, funnel_saj | AG-Grid built-in `max` — consumer-side, no fork work |
| `cpiCalc` ×2 | dead code | delete, consumer-side |

`allow_unsafe_jscode` is a **separate** question and this plan does not close it: it stays required on 11 consumer grids for `valueFormatter` / `cellRenderer` / `cellStyle` / `getRowStyle` / `onStateUpdated` JsCode. Only the marketing grid (formatters only) can evaluate dropping it after Task 5 reaches the consumer.

---

### Task 1: Extract the shared aggregation core, no behaviour change

Pure refactor. It exists so Tasks 3–6 add aggregators by writing ~40 lines each instead of copying `stRatio.ts` twice, and so the three stay consistent on pivot folding, null sorting and registration by construction rather than by review. **Nothing about observable behaviour may change.** The 18 existing e2e tests are the proof.

**Files:**
- Create: `st_aggrid/frontend/src/aggFuncs/foldSums.ts`
- Modify: `st_aggrid/frontend/src/aggFuncs/stRatio.ts`
- Do **not** modify: `st_aggrid/frontend/src/utils/parsers.ts`, any Python, any test.

**Interfaces produced** (all exported from `foldSums.ts`):

```ts
/** The IAggFuncResult shape every built-in aggregator returns. `sums` is the
 * node's folded component totals — mechanism, not API — and is what a parent
 * folds instead of rescanning leaves. */
export interface StAggValue {
  value: number | null
  sums: Record<string, number>
  toNumber(): number | null
  toString(): string
}

/** Non-finite (including a dataframe NaN) becomes 0. */
export function asNumber(raw: unknown): number

/** In pivot mode a child stores its aggregation under the *pivot result*
 * column's id; folding through the source column's id finds nothing. */
export function resolveColId(params: IAggFuncParams): string

/** Fold this node's children into per-key totals. Leaf children (`child.data`
 * present) contribute `leafContribution(child.data)`; group children
 * contribute their stored `sums`. Every key in `keys` is initialised to 0. */
export function foldChildren(
  params: IAggFuncParams,
  keys: string[],
  leafContribution: (data: any) => Record<string, number>,
): Record<string, number>

/** Build the returned value object. */
export function makeAggValue(value: number | null, sums: Record<string, number>): StAggValue

/** Numeric order, empty cells last in BOTH directions. */
export function stAggComparator(a, b, nodeA, nodeB, isDescending: boolean): number

/** Visit every leaf colDef, descending into column groups. */
export function eachColDef(defs, visit: (def: ColDef) => void): void

/** Merge `fn` into `gridOptions.aggFuncs` under `name` unless the caller
 * supplied that key (theirs wins; log under `debug`), then attach
 * `stAggComparator` to every colDef using `name` that has no comparator. */
export function registerAggFunc(
  gridOptions: GridOptions, name: string, fn: (p: IAggFuncParams) => unknown, debug: boolean,
): GridOptions
```

**Steps:**

- [ ] **Step 1: Create `foldSums.ts`** by moving, unchanged, from `stRatio.ts`: `asNumber` (line 39), the `colId` resolution and child loop (lines 75–91), `sortValue` + `stRatioComparator` (lines 123–156) renamed `stAggComparator`, `eachColDef` (lines 161–170), and the body of `registerStRatio` (lines 179–207) parameterized by `name` and `fn`. Carry every explanatory comment across verbatim — they record measured findings, not opinions.

- [ ] **Step 2: Rewrite `stRatio.ts` on top of it.** It keeps `ST_RATIO`, `StRatioConfig`, `readStRatioConfig`, `stRatioAggFunc`, `registerStRatio`. `stRatioAggFunc` becomes:
  - `const fields = Array.from(new Set([...config.num, ...config.den]))` — keep the dedup and its comment (a name in both `num` and `den` would otherwise compound as 2^depth).
  - `const sums = foldChildren(params, fields, (data) => Object.fromEntries(fields.map(f => [f, asNumber(data[f])])))`
  - The arithmetic (lines 93–110) unchanged.
  - `return makeAggValue(value, sums)`
  - `registerStRatio(go, debug)` becomes `registerAggFunc(go, ST_RATIO, stRatioAggFunc, debug)`.
  - Re-export `stRatioComparator` as an alias of `stAggComparator` so existing imports and any consumer reference keep resolving. Keep `StRatioValue` as a type alias of `StAggValue`.

- [ ] **Step 3: Rebuild and prove nothing moved.**
  ```bash
  cd st_aggrid/frontend && COREPACK_ENABLE_DOWNLOAD_PROMPT=0 corepack yarn build
  cd ../.. && pytest -m "not e2e" && pytest test/test_grid_ratio_builtin.py test/test_grid_ratio_js.py
  ```
  All 18 built-in tests and both JavaScript-baseline tests must pass **unchanged**. If a test needs editing to pass, the refactor changed behaviour — revert and find out why. Report the pass counts.

**Verification:** `pytest -m "not e2e"` green; `pytest test/test_grid_ratio_builtin.py test/test_grid_ratio_js.py` green with zero test-file edits.

---

### Task 2: Extend the fixture with growth, weighted-average and share data

Pure Python. No frontend, no browser. The fixture owns the data *and* the arithmetic, so every number Tasks 3–6 assert against exists and is self-checked before any aggregator does. Follow the existing module's structure exactly — read `test/ratio_fixture.py` and `test/unit/test_ratio_fixture.py` first.

**Files:**
- Modify: `test/ratio_fixture.py`
- Modify: `test/unit/test_ratio_fixture.py`

**New component columns.** Add these keys to every row of `RATIO_ROWS`, in this order, and extend `COMPONENT_FIELDS` to match:

| row | campaign/country | ads_d0 | inst_d0 | ads_d1 | inst_d1 | credits_d0 | wa_value | wa_weight |
|---|---|---|---|---|---|---|---|---|
| 0 | A/US | 80 | 2 | 70 | 2 | 80 | 10 | 2 |
| 1 | A/US | 20 | 8 | 20 | 8 | 20 | 1 | 8 |
| 2 | A/DE | 9 | 10 | 35 | 10 | 9 | `None` | 10 |
| 3 | A/DE | 1 | 90 | 5 | 90 | 1 | 2 | 90 |
| 4 | B/US | 6 | 10 | 9 | 10 | −6 | 5 | 0 |
| 5 | B/US | 4 | 90 | 1 | 90 | −4 | 3 | 100 |
| 6 | B/DE | 15 | 20 | 30 | 20 | −15 | 4 | 50 |
| 7 | B/DE | 5 | 80 | 10 | 80 | −5 | 6 | 50 |

`wa_value` row 2 is `None` so it becomes NaN in the DataFrame — a leaf the weighted average must skip. `wa_weight` row 4 is `0` — a leaf it must also skip. `credits_d0` mirrors `ads_d0` with campaign B's sign flipped, which is what makes campaign B's *from*-ARPU negative.

**New evaluators**, beside the existing `evaluate` / `evaluate_legacy`:

- `evaluate_ratio_of_ratios(rows, spec) -> float | None` — `to_ratio / from_ratio` where each leg is the existing `evaluate` semantics, every gate `!= 0`.
- `evaluate_ratio_of_ratios_legacy(rows, spec) -> float | None` — the retired JavaScript: each leg gated `den > 0`, the outer division additionally gated `from_ratio > 0`. Exists so the `> 0` → `!= 0` behaviour change is a pinned number, not a surprise.
- `evaluate_weighted_avg(rows, spec) -> float | None` — `Σ(vᵢ·wᵢ)/Σwᵢ` over rows where `vᵢ` is finite **and** `wᵢ > 0`; `None` (→ `fill_null`) when the surviving weight sums to 0.

**New spec dataclasses**, mirroring `RatioSpec`'s shape (`col_id`, `header`, `fill_null`, a `to_context()` emitting optional keys only when non-default):

- `RatioOfRatiosSpec` — `col_id, header, from_leg, to_leg, fill_null`, where each leg is a `RatioSpec`-shaped mapping carrying `num`, `den`, and optionally `num_signs`, `multiplier`, `scale`, `den_const`. `to_context()` emits `{"from": {...}, "to": {...}}` plus `fill_null`.
- `WeightedAvgSpec` — `col_id, header, value, weight, scale, fill_null`. `to_context()` emits `{"value": ..., "weight": ...}` plus non-default `scale` / `fill_null`.

**New spec instances** and their reference values. These literals are the hand-typed anchors the Global Constraints require — write them into `test/unit/test_ratio_fixture.py` as direct assertions:

`GROWTH_SPECS: tuple[RatioOfRatiosSpec, ...]`

| col_id | declaration | A/US | A/DE | A | B/US | B/DE | B | grand |
|---|---|---|---|---|---|---|---|---|
| `growth` | from `ads_d0`/`inst_d0`, to `ads_d1`/`inst_d1` | 0.9 | 4.0 | 1.181818… | 1.0 | 2.0 | 1.666666… | **1.285714…** (= 9/7) |
| `growth_neg` | from `credits_d0`/`inst_d0`, to `ads_d1`/`inst_d1` | 0.9 | 4.0 | 1.181818… | −1.0 | −2.0 | −1.666666… | 2.25 |

`growth` is the **direction-discriminating** column the P1 spec asks for and the existing fixture lacks: `A/US = 0.9 < 1` while its row total `A = 1.1818 > 1`. A test that accidentally reads the row total fails on sign, not just magnitude. Assert that property explicitly in the fixture's own test.

`growth_neg` is the `> 0` → `!= 0` delta: `evaluate_ratio_of_ratios` gives campaign B `−1.0 / −2.0 / −1.6667`, `evaluate_ratio_of_ratios_legacy` gives `None` for all three. Assert both, so the behaviour change is a number in the repo.

`WEIGHTED_SPECS: tuple[WeightedAvgSpec, ...]`

| col_id | value / weight | fill_null | A/US | A/DE | A | B/US | B/DE | B | grand |
|---|---|---|---|---|---|---|---|---|---|
| `wavg` | `wa_value` / `wa_weight` | `None` | 2.8 | 2.0 | **2.08** | 3.0 | 5.0 | 4.0 | **3.36** |
| `wavg_blank` | `wa_value` / `payers` | `None` | 5.5 | 2.0 | 61/13 = 4.692307… | — | — | — (blank) | 4.692307… |
| `wavg_zero` | `wa_value` / `payers` | `0.0` | 5.5 | 2.0 | 4.692307… | 0.0 | 0.0 | 0.0 | 4.692307… |

`wavg` proves the skip rules: A/DE ignores the NaN leaf (else `2.0` would not be `2.0`), B/US ignores the zero-weight leaf (else it would be `3.1̄`). `wavg_blank`/`wavg_zero` are the `fill_null` pair — campaign B has zero payers throughout, so the weight sum collapses.

`SHARE_SPEC: RatioSpec` — `col_id="share"`, `num=("cost",)`, `den=()`, `den_const=1020.0`, `scale=100.0`. `RatioSpec` gains an optional `den_const` field and `to_context()` emits it when set; `evaluate` adds it to the denominator. Values: A/US 88.235294…, A/DE 9.803922…, A 98.039216…, B/US 0.980392…, B/DE 0.980392…, B 1.960784…, **grand total exactly 100.0** — `Σcost = 1020`, which is the anchor that proves the constant is not being summed across leaves.

**Blind-spot declarations.** Extend `DEGENERATE_NODES` and `PIVOT_BLIND_CELLS` and keep `test/unit/test_ratio_fixture.py`'s two-directional measurement green — it asserts both that the declared nodes really are blind *and* that nothing else is. Worked out from the table above, the new columns add only:

- `DEGENERATE_NODES`: `("wavg_blank", "B")` and `("wavg_zero", "B")` — campaign B collapses to `fill_null` in both countries.
- `PIVOT_BLIND_CELLS`: `("wavg_blank", "B", "US")`, `("wavg_blank", "B", "DE")`, `("wavg_zero", "B", "US")`, `("wavg_zero", "B", "DE")`.
- `growth`, `growth_neg`, `wavg` and `share` add **nothing** — every cell differs from its row total and every group differs from the average of its children. Assert that, rather than leaving it implied.

**Steps:**

- [ ] **Step 1:** Extend `RATIO_ROWS`, `COMPONENT_FIELDS` and `ratio_dataframe()`. `ratio_dataframe()` already carries a precomputed scalar per ratio so leaves render a real number while only group rows run the aggregator — do the same for the new columns.
- [ ] **Step 2:** Add `den_const` to `RatioSpec`, `to_context()` and `evaluate`.
- [ ] **Step 3:** Add the two new spec classes, the three new evaluators, and `expected_ratio_of_ratios()` / `expected_weighted_avg()` helpers matching the existing `expected(col_id, **dims)` signature.
- [ ] **Step 4:** Extend the blind-spot frozensets.
- [ ] **Step 5:** Extend `test/unit/test_ratio_fixture.py` with the literal anchors above, the direction-discrimination assertion, the legacy-divergence pins for `growth_neg`, and the skip-rule assertions for `wavg`. Keep the existing two-directional degeneracy tests green.
- [ ] **Step 6:** Run `pytest -m "not e2e"`. If the added DataFrame columns broke an existing assertion about the frame's shape or column list, fix that assertion mechanically and say so in the report.

**Verification:** `pytest -m "not e2e"` green, including the pre-existing fixture tests. `pytest test/test_grid_ratio_builtin.py` still green — the new columns are additional data, and the row-index maps are unchanged.

---

### Task 3: `stRatio` gains `den_const`

Covers the consumer's `shareAgg`: a share of a window-wide total. `payers_intelligence` computes that total in Python (`product_grid.py:265`, `float(df["purchases"].sum())`) and repeats it on every leaf, so summing it across a group's children would shrink every share by the child count. A constant in the declaration divides by it once, at every level.

**Files:**
- Modify: `st_aggrid/frontend/src/aggFuncs/stRatio.ts`
- Modify: `st_aggrid/ratio.py`
- Modify: `test/unit/test_ratio_validation.py`
- Create: `test/grid_agg_builtin.py`, `test/test_grid_agg_builtin.py`

**Interfaces:**
- Consumes: `foldSums.ts` (Task 1), `ratio_fixture.SHARE_SPEC` (Task 2).
- Produces: `StRatioConfig.den_const?: number`.

**Semantics:** `denominator = (config.den_const ?? 0) + Σ (sums[f] for f in config.den)`. Everything else — `!== 0` gate, `multiplier`, `scale`, `fill_null` — unchanged. `den` may be an empty list **iff** `den_const` is a number; both empty is still an error.

**Steps:**

- [ ] **Step 1: Validation first** (`st_aggrid/ratio.py`, pure Python, no build). Relax `den` to allow empty when `den_const` is a number, add `den_const` to the numeric-key check beside `multiplier`/`scale`, and keep the "unknown field" check over `num` + `den` unchanged. New unit tests in `test/unit/test_ratio_validation.py`, in the existing style — one test per rule, `pytest.raises(ValueError, match=...)`:
  - `{"num": ["cost"], "den": [], "den_const": 1020}` passes
  - `{"num": ["cost"], "den": ["installs"], "den_const": 100}` passes (mixed form)
  - `{"num": ["cost"], "den": []}` still raises
  - `{"num": ["cost"], "den": [], "den_const": "1020"}` raises, message naming `den_const`
  - `{"num": ["cost"], "den": [], "den_const": True}` raises — `bool` is an `int` subclass and a `True` constant is a mistake, matching `_is_number`'s existing rule
  Run `pytest -m "not e2e"`.

- [ ] **Step 2: The aggregator** — one line in `stRatioAggFunc`'s denominator, plus the `den_const?: number` field on `StRatioConfig` with a comment saying why it is not just another `den` entry.

- [ ] **Step 3: The e2e app** `test/grid_agg_builtin.py`. This is the new home for every aggregator this plan adds; Tasks 4–6 extend it. Model it on `test/grid_ratio_builtin.py`: `COMMON_OPTIONS` with `suppressColumnVirtualisation`, `suppressRowVirtualisation`, `groupDefaultExpanded: -1`, `grandTotalRow: "bottom"`, one keyed grid per scenario in a fixed order. For this task, two grids:
  - index 0, key `agg_builtin_rowgroup` — row-grouped by campaign then country, carrying the component columns with `aggFunc: "sum"` and the `share` column.
  - index 1, key `agg_builtin_pivot` — `pivotMode: True`, `pivotRowTotals: "after"`, pivoted on country, grouped by campaign.
  Column shape, same as the existing app:
  ```python
  {"colId": spec.col_id, "field": spec.col_id, "headerName": spec.header,
   "type": "numericColumn", "aggFunc": "stRatio",
   "context": {"stRatio": spec.to_context()}, "width": 130}
  ```

- [ ] **Step 4: The e2e test** `test/test_grid_agg_builtin.py`. Module-scoped `StreamlitRunner`, function-scoped `go_to_app` waiting for the grid count and the last row-index, reading through `test/grid_dom.py`. Assert for `share`: each group level, each pivot cell, the pivot row total, and — the anchor — **the grand total is exactly `100.0000`**. Derive every other expectation from the fixture.

- [ ] **Step 5:** Rebuild, then `pytest -m "not e2e" && pytest test/test_grid_agg_builtin.py test/test_grid_ratio_builtin.py`.

**Verification:** the share column's grand total reads `100.0000`; group and pivot values match `expected("share", ...)`; the frozen `stRatio` suite is still green.

---

### Task 4: `stRatio` degrades to `sum` when a column carries no declaration (P2)

`stRatio` is registered from `parseGridOptions`, which every grid passes through, so AG-Grid offers it in the columns tool panel's aggregation picker on **every** Enterprise grid with a `sideBar` and a value column. Picking it on a column with no `context["stRatio"]` blanks that column's group values today — measured, and recorded as "Known issue, undecided" in `docs/superpowers/specs/2026-08-10-declarative-ratio-aggregation-design.md`. Falling back to `sum` turns a blanked column into a degraded-but-sane one and needs no consumer change.

The register-only-when-declared alternative was considered and rejected in that same document, because a column can acquire `aggFunc: "stRatio"` at runtime through grid state — which is precisely the path this task must test.

**Files:**
- Modify: `st_aggrid/frontend/src/aggFuncs/stRatio.ts`
- Modify: `test/grid_agg_builtin.py`, `test/test_grid_agg_builtin.py`

**Semantics:** when `readStRatioConfig(params.colDef)` returns `null`, sum `params.values` — unwrapping `toNumber()` where a value carries it, coercing non-finite to skip — and return a **plain number**, not an `StAggValue`. Return `null` only when there were no numeric values at all.

Returning a plain number is load-bearing in two ways, and both belong in the code comment:
1. A `valueFormatter` written for a number keeps working; an `StAggValue` with an all-zero `sums` would not be meaningfully better than the blank it replaces.
2. `registerAggFunc` attaches the comparator by walking `columnDefs`, so a column that acquires `stRatio` **at runtime** never gets one. A plain number sorts correctly under AG-Grid's default comparator; an object would not.

**Steps:**

- [ ] **Step 1:** Implement the fallback branch in `stRatioAggFunc`.
- [ ] **Step 2:** Add grid index 2, key `agg_builtin_fallback`, to `test/grid_agg_builtin.py`. It has **no** ratio columns. Two probes:
  - `cost` declared with `aggFunc: "stRatio"` and **no** `context` — the parse-time path.
  - `installs` declared with `aggFunc: "sum"` but overridden at runtime through `initialState` so it aggregates with `stRatio` — the runtime path `registerAggFunc` cannot see. In AG-Grid 36 that is `initialState: {"aggregation": {"aggregationModel": [{"colId": "installs", "aggFunc": "stRatio"}]}}`. **Confirm the exact state shape against the AG-Grid 36 docs before relying on it**; if it differs, use `call_grid_api` to set the aggregation after mount instead, and record which route you used in the report.
- [ ] **Step 3:** Tests: campaign A's `cost` group cell reads `1000`, campaign B `20`, grand total `1020` — the plain sums, derived from the fixture, not blanks. Same for `installs` on the runtime-acquired column (`100` / `200` / `300`). Then click the `cost` header and assert the campaign order sorts numerically in both directions — this is the assertion that proves the missing comparator no longer matters.
- [ ] **Step 4:** Rebuild, then `pytest test/test_grid_agg_builtin.py test/test_grid_ratio_builtin.py`.

**Verification:** both probes show sums rather than blanks; the runtime-acquired column sorts numerically ascending and descending; the declared-`stRatio` suite is untouched and green.

---

### Task 5: The `stRatioOfRatios` aggregator

The P1 request. Replaces the consumer's 45 marketing `growth` columns — an install-weighted ARPU ratio between two cohort days, `(Σnum_to/Σden_to)/(Σnum_from/Σden_from)`. `stRatio` cannot express it: `(A/B)/(C/D) = A·D/(B·C)` is a *product of sums* in both numerator and denominator, and no assignment of field names to `num`/`den` produces that. Cross-multiplying would also collapse three independent null gates into one.

Read `docs/superpowers/specs/2026-08-11-ratio-of-ratios-request.md` before starting — its "Semantics a design must pin down" section is the acceptance list.

**Files:**
- Create: `st_aggrid/frontend/src/aggFuncs/stRatioOfRatios.ts`
- Modify: `st_aggrid/frontend/src/aggFuncs/stRatio.ts` (export the leg evaluator), `st_aggrid/frontend/src/utils/parsers.ts`, `st_aggrid/ratio.py`
- Modify: `test/unit/test_ratio_validation.py`, `test/grid_agg_builtin.py`, `test/test_grid_agg_builtin.py`

**Declaration:**
```python
{"colId": "GROWTH_0_1_ADS",
 "aggFunc": "stRatioOfRatios",
 "context": {"stRatioOfRatios": {
     "from": {"num": ["ads_for_0"], "den": ["installs_for_0"]},
     "to":   {"num": ["ads_for_1"], "den": ["installs_for_1"]},
     "fill_null": None,
 }}}
```

Each leg accepts the **full** `stRatio` leg shape — `num`, `den`, and optionally `num_signs`, `multiplier`, `scale`, `den_const`. That is free once the leg evaluator is factored out of `stRatio`, and signed numerators already exist elsewhere in the consumer. Factor `evaluateLeg(sums, leg): number | null` out of `stRatioAggFunc`'s arithmetic and call it from both aggregators, so the two can never drift.

**Arithmetic** (Global Constraints: `!== 0` throughout):
```
from_ratio = evaluateLeg(sums, config.from)     // null when its denominator is 0
to_ratio   = evaluateLeg(sums, config.to)
value      = (from_ratio != null && to_ratio != null && from_ratio !== 0)
               ? to_ratio / from_ratio
               : (config.fill_null ?? null)
```

**Folding:** `sums` is keyed by field name over the deduplicated union of all four field lists, folded by `foldChildren` exactly as `stRatio` does. This is what makes pivot cells, pivot row totals and the grand total each re-derive *both* inner ratios at their own node rather than combining their children's outer values — the defect the consumer's JavaScript has and this feature exists to remove.

**Steps:**

- [ ] **Step 1: Validation first** (`st_aggrid/ratio.py`). Add `RATIO_OF_RATIOS_AGG_FUNC = RATIO_OF_RATIOS_CONTEXT_KEY = "stRatioOfRatios"`. Turn `validate_ratio_columns`'s per-column body into a dispatch over context keys — it stays the single entry point and the single colDef walk, still called once from `aggrid.py:353`. Factor the existing `_validate_config` body into a reusable `_validate_leg` and call it for `from` and `to`. New rules, messages in the existing style:
  - `from`/`to` both present and both dicts
  - each leg validated by `_validate_leg` (so `num`/`den`/`num_signs`/`multiplier`/`scale`/`den_const` rules are shared, not duplicated)
  - `fill_null` number-or-`None`
  - field-existence over all four lists, with the same "contributes 0 and silently skews the ratio" wording and the same DataFrame-only caveat
  - `aggFunc: "stRatioOfRatios"` with no `context["stRatioOfRatios"]` raises, mirroring the existing `stRatio` rule
  Extend `test/unit/test_ratio_validation.py` and run `pytest -m "not e2e"`.

- [ ] **Step 2: `evaluateLeg`** — extract from `stRatioAggFunc` (`stRatio.ts` lines 93–110) and export. `stRatio` must now call it, so Task 3's `den_const` and the `!== 0` gate live in exactly one place. Rebuild and re-run `test/test_grid_ratio_builtin.py`: extracting it must not move any existing number.

- [ ] **Step 3: `stRatioOfRatios.ts`** — `ST_RATIO_OF_RATIOS`, `StRatioOfRatiosConfig`, `readStRatioOfRatiosConfig` (returns `null` unless `from` and `to` are both objects with array `num`/`den`), `stRatioOfRatiosAggFunc`, `registerStRatioOfRatios` delegating to `registerAggFunc`.

- [ ] **Step 4: Register** — add the call in `parsers.ts` beside `registerStRatio`, so both the mount path (`AgGridComponent.tsx:387`) and the live-update path (`:481`) get it from the one site.

- [ ] **Step 5: e2e** — add `growth` and `growth_neg` to grids 0 (row-group) and 1 (pivot) in `test/grid_agg_builtin.py`, and add grid index 3, key `agg_builtin_grouped_cols`, nesting them under `children` so `eachColDef`'s descent is under test rather than under inspection. Tests, all deriving from the fixture except the named anchors:
  - both group levels, all four pivot cells, both pivot row totals, the grand total
  - **the direction test**: `growth` at pivot cell A/US is `< 1` while the A row total is `> 1`. Assert the inequality on both sides, not just the numbers — this is the assertion that cannot pass while the aggregator reads the row's whole leaf set, and every other pivot assertion can.
  - **the `> 0` → `!== 0` delta**: `growth_neg` renders `-1.0000` at B/US and `-2.0000` at B/DE, where the retired JavaScript rendered empty cells. Reference `evaluate_ratio_of_ratios_legacy` in the test's docstring so the change is legible.
  - sorting ascending and descending with empty cells last in both, and a caller-supplied `comparator` left alone.

- [ ] **Step 6:** Rebuild, then `pytest -m "not e2e" && pytest -m e2e`.

**Verification:** every level correct including both totals; the direction test passes; the negative-`from` delta is pinned; sorting puts blanks last both ways; the frozen `stRatio` suite is green.

---

### Task 6: The `stWeightedAvg` aggregator

Replaces the consumer's `installWeightedAvg` (`cohort_growth/grid_builder.py:13`, also used by `ab_tests/arpu_growth.py`): an install-weighted average of a per-row precomputed ratio, `Σ(vᵢ·wᵢ)/Σwᵢ`. Neither `stRatio` nor `stRatioOfRatios` can express it — the numerator is a **sum of products** evaluated per leaf, not a sum of fields nor a product of sums.

**Files:**
- Create: `st_aggrid/frontend/src/aggFuncs/stWeightedAvg.ts`
- Modify: `st_aggrid/frontend/src/utils/parsers.ts`, `st_aggrid/ratio.py`
- Modify: `test/unit/test_ratio_validation.py`, `test/grid_agg_builtin.py`, `test/test_grid_agg_builtin.py`

**Declaration:**
```python
{"colId": "arpu_growth_d0_d3",
 "aggFunc": "stWeightedAvg",
 "context": {"stWeightedAvg": {"value": "arpu__d0_d3", "weight": "installs"}}}
```
Optional: `scale` (number), `fill_null` (number or `None`, default `None`).

**Leaf contribution** — reproduce the JavaScript's skip rule exactly:
```ts
Number.isFinite(v) && w > 0 ? { wnum: v * w, wden: w } : { wnum: 0, wden: 0 }
```
A leaf with a null/NaN value, or a non-positive weight, contributes to neither side. Dropping it from the numerator alone would leave its weight in the denominator and pull every group toward zero.

**Final step:** `value = wden !== 0 ? (wnum / wden) * scale : fill_null`. Stored under the synthetic `sums` keys `wnum` / `wden`, so `foldChildren` applies unchanged and a parent folds a child's two accumulators rather than rescanning leaves.

Note in the code comment: because weights only accumulate when `w > 0`, `wden` is never negative, so `!== 0` and the JavaScript's `> 0` coincide here. **Unlike the other two aggregators, this port has no behaviour delta** — worth stating so a reader does not go looking for one.

**Steps:**

- [ ] **Step 1: Validation first.** Add `WEIGHTED_AVG_AGG_FUNC = WEIGHTED_AVG_CONTEXT_KEY = "stWeightedAvg"` and a third dispatch branch in `validate_ratio_columns`. Rules: `value` and `weight` are non-empty strings and both present; `scale` numeric when present; `fill_null` number-or-`None`; both names checked for existence against the DataFrame with the same wording and the same caveat; `aggFunc` named without context raises. Extend `test/unit/test_ratio_validation.py`, run `pytest -m "not e2e"`.
- [ ] **Step 2:** `stWeightedAvg.ts` plus its `registerAggFunc` call in `parsers.ts`.
- [ ] **Step 3: e2e** — add `wavg`, `wavg_blank` and `wavg_zero` to grids 0, 1 and 3 in `test/grid_agg_builtin.py`. Tests deriving from the fixture, plus these explicit ones:
  - **the NaN skip**: A/DE reads `2.0000`. If the null leaf were counted with weight 10, it would read `1.8000`. Say so in the test's docstring.
  - **the zero-weight skip**: B/US reads `3.0000`. Counting the zero-weight leaf as a plain average would give `4.0000`.
  - **not the average of children**: campaign A reads `2.0800`, not `2.4000` (the mean of `2.8` and `2.0`).
  - `fill_null` both ways: `wavg_blank` at campaign B is an empty cell; `wavg_zero` at campaign B is `0.0000`.
  - the grand total reads `3.3600`.
  - sorting with `wavg_blank`'s empty cells last in both directions.
- [ ] **Step 4:** Rebuild, then `pytest -m "not e2e" && pytest -m e2e`.

**Verification:** both skip rules demonstrated by a number that would differ if the rule were missing; both `fill_null` branches; the not-the-average anchor; nulls sort last both ways.

---

### Task 7: Export and clipboard semantics (P3)

The value an aggregated group cell holds is an `IAggFuncResult` object, not a number, and the fork installs **no** export or clipboard hook of any kind — no `processCellForClipboard`, no `defaultCsvExportParams`; `AgGridComponent.tsx:940` calls `exportDataAsCsv()` with no params. What lands in a CSV therefore depends on `useValueFormatterForExport`, and nothing in the fork says what to expect either way.

This is not merely undocumented. The retired JavaScript returned an object carrying `toString → toFixed(4)`; `stRatio` returns one carrying `toString → String(value)` (`stRatio.ts:116`). **A consumer exporting raw values silently moved from 4-decimal strings to full float precision.** The pilot's grid sets `useValueFormatterForExport=False` deliberately and feeds a Google-Sheets round-trip built on `getDataAsCsv`, so this is a live change with no documented basis.

**Measure first, then write down what you measured.** Do not assume which of `toNumber` / `toString` AG-Grid 36 calls on either path.

**Files:**
- Create: `test/grid_agg_export.py`, `test/test_grid_agg_export.py`
- Modify: `README.md`

**Steps:**

- [ ] **Step 1: Build the probe.** `test/grid_agg_export.py` — two grids over the fixture, one ratio column each, identical but for `useValueFormatterForExport` (`True` on grid 0, `False` on grid 1). Read the CSV back into Python with `collect=["getDataAsCsv"]`: `useAutoCollect.ts:99-113` calls any zero-argument grid-API method and returns its value into `AgGridResult`, so the CSV arrives as a string and no download interception is needed. Render it with `st.text` under a stable test id. Give grid 0 a `valueFormatter` so the two settings actually diverge.
- [ ] **Step 2: Measure.** Run the app and record, for both settings, exactly what a group row's ratio cell contains: the formatter's string, the full-precision number, `""` for a `fill_null` cell, or something else. Also record it for `stRatioOfRatios` and `stWeightedAvg` — confirm all three behave alike, and report it if they do not.
- [ ] **Step 3: Pin it.** `test/test_grid_agg_export.py` asserts the exact CSV strings for both settings, including a `fill_null` empty cell and a leaf row (which holds a plain number, not an object) so the group/leaf difference is pinned too.
- [ ] **Step 4: Document it.** Add an "Export and clipboard" subsection under `README.md`'s "Ratio aggregation without JavaScript" stating the behaviour for both settings, and naming the `toFixed(4)` → full-precision change for anyone migrating off a hand-written aggregator.
- [ ] **Step 5:** `pytest test/test_grid_agg_export.py`.

**Verification:** the CSV assertions are exact strings, not shapes; the README states both settings; the precision change is named.

---

### Task 8: Re-exports, documentation, version bump, regression sweep

**Files:**
- Modify: `st_aggrid/__init__.py`, `README.md`, `CLAUDE.md`, `pyproject.toml`, `st_aggrid/pyproject.toml`
- Create: `test/unit/test_public_exports.py`

**Steps:**

- [ ] **Step 1: P4 — re-export the helpers.** `validate_ratio_columns` and the six name constants (`AGG_FUNC_NAME`, `CONTEXT_KEY`, `RATIO_OF_RATIOS_AGG_FUNC`, `RATIO_OF_RATIOS_CONTEXT_KEY`, `WEIGHTED_AVG_AGG_FUNC`, `WEIGHTED_AVG_CONTEXT_KEY`) join the imports and `__all__` in `st_aggrid/__init__.py`, keeping the existing alphabetical order. Today a consumer that wants to validate its own grid options, or to avoid hard-coding `"stRatio"`, must import from what reads like a private module path.
  Record the caveat from `2026-08-11-stratio-followups-small.md` in the docstring: this does **not** help every consumer. A module that sits on an import-time-`streamlit`-free path cannot import `st_aggrid` at all and must hard-code the literal regardless — the re-export helps test code and grid-builder modules, which import `st_aggrid` anyway.
  `test/unit/test_public_exports.py` asserts each name is importable from `st_aggrid` and that the constants equal their expected literals.

- [ ] **Step 2: README.** Rename `### Ratio aggregation without JavaScript` to cover all three aggregators, or add two sibling subsections. Each needs: the declaration, the arithmetic, the `!== 0` rule, `fill_null`, what validation does and its DataFrame-only caveat, and that the built-in is a default a caller's `aggFuncs` entry overrides. Document `den_const` on `stRatio`, and the Task 4 fallback (`aggFunc: "stRatio"` without a declaration aggregates as `sum`). Name the behaviour change from the Global Constraints explicitly: **a negative *from*-period ARPU now yields a negative growth ratio where a `> 0`-gated aggregator rendered an empty cell.**

- [ ] **Step 3: CLAUDE.md.** Update the "Built-in `stRatio` aggregator" bullet under Key Design Decisions to name all three and the shared `foldSums.ts` core, and add `aggFuncs/` entries to the architecture tree. Keep it to a few lines — it is a map, not documentation.

- [ ] **Step 4: Version.** Bump the version in **both** `pyproject.toml` and `st_aggrid/pyproject.toml`. They must match: `st_aggrid/pyproject.toml` is the in-wheel component manifest and a mismatch breaks asset discovery.

- [ ] **Step 5: Full sweep.**
  ```bash
  cd st_aggrid/frontend && COREPACK_ENABLE_DOWNLOAD_PROMPT=0 corepack yarn build
  cd ../.. && pytest -m "not e2e" && pytest
  ```
  Confirm each glob in `st_aggrid/component.py` matches exactly one file after the rebuild, and that `git status` shows the expected delete + add under `st_aggrid/frontend/build/` rather than a stale bundle.

**Verification:** `pytest` green (everything except the slow 1M-row suite); both `pyproject.toml` versions match; the committed bundle is the one the final source produced.

---

## Follow-up: consumer migration (separate repository)

Not part of this plan's tasks. Ordered by what each unblocks. Items 1–3 are the ones that were blocked on fork work.

1. **marketing** — `growthRatio` → `stRatioOfRatios`. Delete `js_growth_ratio`; `aggFuncs` becomes `{}`. `MetricSpec` grows a `to_st_ratio_of_ratios()` beside `to_st_ratio()` (`metric_spec.py:343`), retiring `extra_agg_context`, whose only producer in the whole repo is `marketing/grid_metrics.py:783`. Then evaluate `allow_unsafe_jscode` — verified: after this, the grid's only remaining `JsCode` is six `valueFormatter`s.
2. **payers_intelligence** — `shareAgg` → `stRatio` with `den_const`, sourced from the value `with_purchase_total` already computes.
3. **cohort_growth + ab_tests·arpu_growth** — `installWeightedAvg` → `stWeightedAvg`, a faithful port with no number changes.
   ⚠ Separate product decision worth raising afterwards: `compute_growth_frame` computes the growth ratio in pandas as `arpu_to/arpu_from`, so the grid is taking an install-weighted *mean of ratios* — the very approximation the P1 spec argues against for marketing. Keeping the four components on the frame and declaring `stRatioOfRatios` would be more correct, but changes displayed numbers. Port first, decide correctness separately.
4. **funnel / funnel_saj / ad_placements / payers** — `ratioAgg` → `stRatio`; drop `_ratio_value_getter` and `js_ratio_comparator`. ⚠ `ratioAgg` renders `0` on a collapsed denominator while `ad_placements`' `eCPM` declares `fill_null=None` and would go blank. Decide per column.
5. **cohort / cohort_comparison / iap_dash** — `valuePerInstall` → `stRatio`, with `<metric>_numerator` / `<metric>_denominator` written in Python instead of derived from `colDef.headerName` in JavaScript; drop `js_value_getter` and `js_value_comparator`; set `field` so leaves render the scalar.
6. **funnel / funnel_saj** — `installsAgg` / `usersAgg` → AG-Grid's built-in `max`. ⚠ negative values are no longer clamped to `0`.
7. **ab_tests** — the inline aggregator at `grid_builder.py:95` → `stRatio`. Easy to miss: it is passed by value, so there is no `aggFuncs` entry to grep for.
8. Delete both dead `cpiCalc` implementations (`cohort/js_funcs.py:126`, `cohort_growth/grid_builder.py:42` — the latter behind a literal `if False:`).
