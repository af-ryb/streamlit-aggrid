# streamlit-aggrid v2

Streamlit component for [AG-Grid](https://www.ag-grid.com/) built on Custom Components v2 (no iframe).

AG-Grid version: [36.0.0](https://www.ag-grid.com/archive/36.0.0/)

## Install

From git:

```bash
pip uninstall -y streamlit-aggrid  # only needed once, when upgrading from < 2.2.0
pip install git+https://github.com/af-ryb/streamlit-aggrid.git@v2_component
```

The distribution was renamed `streamlit-aggrid` → `st-aggrid` in 2.2.0. pip does
not uninstall the old distribution when installing the new one, and the old
dist-info's RECORD still claims `st_aggrid/*` — uninstalling it *after* the new
install would delete files the new install owns. Remove it first.

## Quick Start

```python
from st_aggrid import AgGrid
import pandas as pd

df = pd.DataFrame({
    "Name": ["Alice", "Bob", "Charlie"],
    "Age": [25, 30, 35],
    "Score": [88.5, 92.3, 76.1],
})

result = AgGrid(df, key="my_grid")
```

## Core Concepts

### No iframe

v2 uses Streamlit Custom Components v2 which renders directly in the DOM, eliminating the iframe overhead. Data is transferred via Arrow (PyArrow) for efficiency.

### Read-only grid

This fork removes all data editing functionality. The grid is for display, selection, filtering, sorting, and data export only.

### Auto-Collect

The `collect` parameter specifies which AG-Grid API methods to call automatically after each grid event. Results are available as properties on the returned `AgGridResult`:

```python
result = AgGrid(
    df,
    grid_options=grid_options,
    collect=["getSelectedRows", "getFilterModel", "getColumnState"],
    update_on=["selectionChanged", "filterChanged", "sortChanged",
               ("columnResized", 300), ("columnMoved", 500)],
    key="my_grid",
)

result.selected_rows   # DataFrame of selected rows (or None)
result.filter_model    # dict with active filters
result.column_state    # list of column state dicts
result.event_name      # name of the event that triggered the update
result.event_data      # serialized event payload
```

**Defaults:** `collect=["getSelectedRows"]`, `update_on=["selectionChanged", "filterChanged", "sortChanged"]`.

The `update_on` list accepts AG-Grid event names. Use a tuple `(event_name, debounce_ms)` for high-frequency events like `columnResized`.

Any AG-Grid API method that returns serializable data can be used in `collect`. The result key is derived from the method name: `getSelectedRows` -> `result.selected_rows`, `getFilterModel` -> `result.filter_model`, or via `result.get("selectedRows")`.

**`gridReady` and `firstDataRendered` do not work as zero-interaction `update_on` triggers** — measured, not assumed. The listener-attaching effect behind `collect`/`update_on` only runs once the `gridApi` state is set, and that state is itself set from inside `AgGridComponent`'s own `onGridReady` callback — so by the time a `gridReady` listener registered through `update_on` is actually attached, the grid's internal `gridReady` event has already fired once and will never fire again. `firstDataRendered` loses the same race for the same reason whenever there is no asynchronous data load to delay it. Put a real user-driven event in `update_on` (`sortChanged`, `selectionChanged`, ...) if you need the grid to auto-collect on load.

### Explicit API Calls

For one-off actions (export, getting state on demand) use `call_grid_api`. It writes a request to `session_state`; the grid executes it on the next rerun. Use `@st.fragment` to avoid full page rerun:

```python
from st_aggrid import AgGrid, call_grid_api

@st.fragment
def grid_section():
    result = AgGrid(df, grid_options=grid_options, key="my_grid")

    if st.button("Get Column State"):
        call_grid_api("my_grid", "getColumnState")
        st.rerun(scope="fragment")

    if result.api_response:
        st.json(result.api_response)

grid_section()
```

### GridOptionsBuilder

Configure grid options without writing raw dicts:

```python
from st_aggrid import GridOptionsBuilder

gb = GridOptionsBuilder.from_dataframe(df)
gb.configure_default_column(enableRowGroup=True, minWidth=100)
gb.configure_selection("multiple", use_checkbox=True)
gb.configure_side_bar(filters_panel=True, columns_panel=True)
gb.configure_pagination(enabled=True, auto_page_size=True)
grid_options = gb.build()

result = AgGrid(df, grid_options=grid_options, key="my_grid")
```

### Themes

```python
# Built-in themes
AgGrid(df, theme="streamlit")  # matches Streamlit light/dark (default)
AgGrid(df, theme="alpine")
AgGrid(df, theme="balham")
AgGrid(df, theme="material")

# Custom theme
from st_aggrid import StAggridTheme

theme = StAggridTheme("quartz")
theme.with_params(accentColor="#ff0000", headerFontSize=14)
theme.with_parts("colorSchemeDark", "iconSetAlpine")

AgGrid(df, theme=theme)
```

### Enterprise Features

AG-Grid Enterprise features (row grouping, pivoting, Excel export, etc.) require a license from [ag-grid.com](https://www.ag-grid.com/):

```python
AgGrid(
    df,
    grid_options=grid_options,
    enable_enterprise_modules=True,          # or "enterprise+AgCharts"
    license_key="your-license-key",
    key="my_grid",
)
```

### Custom JavaScript

Inject JS functions into gridOptions with `JsCode`:

```python
from st_aggrid import JsCode

cell_renderer = JsCode("""
    function(params) {
        return '<b>' + params.value + '</b>';
    }
""")

gb.configure_column("Name", cellRenderer=cell_renderer)
result = AgGrid(df, grid_options=gb.build(), allow_unsafe_jscode=True, key="my_grid")
```

### Declarative aggregation without JavaScript

A ratio cannot be rolled up by rolling up the ratio: a group's value is
`Σnumerator / Σdenominator`, never the average of its children's ratios — and
a growth rate or an install-weighted average have the same problem in their
own shape. Three built-in aggregators compute these from a declaration in
`colDef.context` instead of hand-written `JsCode`, and share one folding
core. Each is correct at every grouping level, in pivot cells, in pivot row
totals and in total rows: they fold `params.aggregatedChildren` bottom-up
rather than re-walking `allLeafChildren`, which would be both quadratic in
tree depth and blind to the current pivot key.

```python
from st_aggrid import RATIO_AGG_FUNC, RATIO_OF_RATIOS_AGG_FUNC, WEIGHTED_AVG_AGG_FUNC
# "stRatio", "stRatioOfRatios", "stWeightedAvg" — re-exported so a caller
# never has to hard-code the literal. `validate_ratio_columns` is
# re-exported too (see Validation, below). All are also importable from
# `st_aggrid.ratio` directly — the package root is a convenience for
# anything that already imports `st_aggrid`. A module that must stay
# import-time `streamlit`-free (e.g. one run during a data-source discovery
# walk) cannot import `st_aggrid` at all and has to hard-code the literal
# regardless — the re-export helps test code and grid-builder modules,
# which import `st_aggrid` anyway.
#
# `stRatio`'s constant is also exported under its original, unprefixed name
# (`AGG_FUNC_NAME`) for anything already using it — `RATIO_AGG_FUNC` is the
# same string, preferred for new code because it reads the same way its two
# siblings above already do.
```

Every aggregator here is a **default**, not a reservation: an
`aggFuncs["stRatio"]`, `aggFuncs["stRatioOfRatios"]` or
`aggFuncs["stWeightedAvg"]` entry in your own `grid_options` overrides the
matching built-in (run with `debug=True` to see the override logged). All
three are registered on every grid regardless of whether any column declares
one, so all three appear in the columns tool panel's aggregation picker on
any Enterprise grid with a `sideBar` — including next to a column that
carries no matching `context[...]` at all. What happens then is **not** the
same across the three, deliberately: `stRatio` falls back to summing the
column (see below); `stRatioOfRatios` and `stWeightedAvg` return an empty
cell instead, because there is no sum analogue for a ratio of ratios or a
weighted average.

None of the three are aware of `treeData` and should not be used with it —
they are for row grouping and pivot only.

#### `stRatio` — Σnum / Σden

```python
{
    "colId": "cpi",
    "aggFunc": "stRatio",
    "context": {"stRatio": {"num": ["cost"], "den": ["installs"]}},
}
```

| Key | Required | Default | Meaning |
|---|---|---|---|
| `num` | yes | — | Field names summed to form the numerator |
| `den` | yes\* | — | Field names summed to form the denominator |
| `num_signs` | no | all `1` | Per-term signs, e.g. `[1, -1]` for `(a − b)/c` |
| `multiplier` | no | `1.0` | Applied inside the numerator (CPM uses `1000`) |
| `scale` | no | `1.0` | Applied to the final value (sec→min uses `1/60`) |
| `den_const` | no | `0` | A window-wide constant added to the denominator once per node — not folded like a `den` field |
| `fill_null` | no | `None` | Value when the denominator is exactly `0`; `None` renders an empty cell |

\* `den` must always be present as a list — an **omitted** `den` key raises a
`ValueError`, even when `den_const` is set. To use `den_const` alone as the
whole denominator, pass an explicit empty list: `"den": []`. Both `den: []`
and no `den_const` at the same time is still an error — there would be
nothing left to divide by.

The value is `((Σ signᵢ·numᵢ) · multiplier / (den_const + Σden)) · scale`,
where each `num`/`den` field name resolves to the sum of that field over the
node's subtree, and `den_const` is added exactly once per node no matter how
many leaves it has. That last point is what `den_const` is *for*: a `den`
field naturally scales with subtree size, but a share of a window-wide total
— a number computed once, in Python, and repeated on every row — must not:
folding it through the same per-leaf sum a `den` field gets would multiply it
by the child count and shrink every group's share. Use `den_const` for that
shape (a `share` column dividing by a grand total) and `den` for anything
that should scale with the group; the two combine (`denominator = den_const +
Σden`) rather than one replacing the other, so a column can use both at once.

The zero rule: when `den_const + Σden` is exactly `0`, the value is
`fill_null` (default `None`, an empty cell) instead of a division by zero.
**This is a deliberate behaviour change from the retired hand-written
JavaScript**, which gated on `> 0` instead of `!= 0`: a group whose
denominator is negative — a net-negative `den` field, or a negative
`den_const` — now renders a real, negative ratio, where the old JavaScript
would have rendered an empty cell instead (only an exact `0` falls back to
`fill_null` here). The same divergence is documented again, with a concrete
ARPU example, under `stRatioOfRatios` below, where it applies three times
over (both legs and the outer division).

**A column that ends up with `aggFunc: "stRatio"` and no
`context["stRatio"]` degrades to a plain `Σvalues` (a sum), not a blank
column.** In practice this only happens through a runtime mutation —
the columns tool panel's aggregation picker, `initial_state`, or
`columns_state` — because `validate_ratio_columns` rejects `aggFunc:
"stRatio"` with no matching `context` anywhere in the *original*
`columnDefs`, so a column never reaches the browser this way through a
colDef that Python validated. One consequence worth knowing: the
null-ordering comparator described below is attached by walking
`columnDefs` at parse time, so a column that only acquires `stRatio` at
runtime never gets it. It sorts under AG-Grid's
own default comparator instead, which puts a null-valued cell **first**
ascending — the opposite of every column declared with `stRatio` from the
start. This is architecturally inherent — there is no `columnDefs` snapshot
left to walk once the mutation happens live — not a bug to be fixed here.

Field names are read from the **row data**, so a component needs no column of
its own — but it must be in the DataFrame. A name that is not raises a
`ValueError` when the grid is built, because a missing component would
otherwise contribute `0` and skew the ratio silently. That check only runs
when `AgGrid` is called with a DataFrame: a grid fed through
`grid_options["rowData"]` (`data=None`) has no column set to check field names
against, so a typo'd `num`/`den` entry is not caught — it reaches the browser
and contributes `0`, exactly the silent failure this check exists to prevent.

That is about a field name that resolves to nothing at all. A resolved
field's *values* get their own coercion: a `null` or `NaN` in a particular
row does not exclude that row from the sum — it is coerced to `0` and summed
like any other value (`asNumber`, `foldSums.ts`). This is the right
semantic for a sum (an unknown contribution counts as none, not as missing
data), and it applies to every `num`/`den` field in both `stRatio` and
`stRatioOfRatios` — contrast `stWeightedAvg` below, which is not
sum-based and skips a leaf entirely instead (see its own section for why).

A column declared with `stRatio` from the start sorts numerically, with empty
cells last in both directions. A `comparator` you set yourself is left alone.

#### `stRatioOfRatios` — a ratio of two `stRatio` legs

```python
{
    "colId": "growth",
    "aggFunc": "stRatioOfRatios",
    "context": {
        "stRatioOfRatios": {
            "from": {"num": ["ads_d0"], "den": ["inst_d0"]},
            "to": {"num": ["ads_d1"], "den": ["inst_d1"]},
        }
    },
}
```

Its `from` and `to` keys each carry the same shape as `stRatio`'s own
declaration above (`num`, `den`, and optionally `num_signs`, `multiplier`,
`scale`, `den_const`) — a `growth` column comparing the same ratio across two
time windows is the running example. An outer `fill_null` (default `None`)
is the only key that lives outside both legs; a leg has no `fill_null` of its
own.

The value is `to_ratio / from_ratio`, where each leg is computed with
`stRatio`'s own arithmetic, and both legs are re-derived independently at
*every* node from that node's own folded sums — never combined from a
child's already-computed outer ratio. That is what makes a pivot cell, a
pivot row total and the grand total each correct on their own, instead of a
pivot cell silently inheriting whatever its row (or the whole grid) computed:
`(A/B)/(C/D) = A·D/(B·C)` is a product of sums in both numerator and
denominator, which no single `stRatio` fraction can express — hence two legs
and an outer division here, not one.

The zero rule applies three times: both legs' own denominators, and the
outer division by `from_ratio`. Any one of the three landing on exactly `0`
falls back to `fill_null`. **This is a deliberate behaviour change from the
JavaScript this replaces**, which gated all three on `> 0` instead of `!= 0`:
a group whose *from*-period ARPU is negative — network credits, a refund —
now renders a real, negative growth ratio, where a `> 0`-gated aggregator
would have rendered an empty cell instead.

Same DataFrame-only field-existence validation as `stRatio`, run once over
the deduplicated union of both legs' `num`/`den` fields, so a field named in
both legs (or by both a leg's own `num` and `den`) is reported once, not once
per occurrence.

#### `stWeightedAvg` — an install-weighted average

```python
{
    "colId": "arpu_wavg",
    "aggFunc": "stWeightedAvg",
    "context": {"stWeightedAvg": {"value": "arpu", "weight": "installs"}},
}
```

| Key | Required | Default | Meaning |
|---|---|---|---|
| `value` | yes | — | Field carrying a precomputed per-row ratio (this leaf's own ARPU, CPI, ...) |
| `weight` | yes | — | Field carrying that row's weight (installs, sessions, ...) |
| `scale` | no | `1.0` | Applied to the final value |
| `fill_null` | no | `None` | Value when the surviving weight sums to exactly `0`; `None` renders an empty cell |

Unlike the other two, `value` is read straight off each leaf's own row —
never summed — because there is no numerator/denominator field pair to fold
here. The value is `(Σ(valueᵢ · weightᵢ) / Σweightᵢ) · scale` over leaves,
and a leaf is skipped — contributing to *neither* sum — when its `value` is
`null`, otherwise non-finite (`NaN`, `±Infinity`), **or** its `weight` is not
strictly positive (`weight > 0`). Those are one gate, not two independent
ones: a leaf can't count its weight while dropping its value, or the
reverse — and the `null` case is called out on its own because it does not
fail a plain finiteness check (more on that below). The zero rule applies to
what survives that gate: `Σweightᵢ != 0`, else `fill_null`.

This skip is `stWeightedAvg`-specific, not shared by the other two: `stRatio`
and `stRatioOfRatios` never skip a leaf for a missing component — a `null`/
`NaN` `num`/`den` value there is coerced to `0` and stays in the sum (see
`stRatio`, above). The difference follows from the shape: a sum tolerates a
missing addend as `0`, but `value` here is not summed, it is one term in a
per-leaf product (`value · weight`) — treating a missing `value` as `0`
would silently zero out that leaf's contribution to the numerator while its
weight still counted in the denominator, dragging the average toward zero
instead of just excluding the leaf.

Worth knowing if you write your own `valueGetter` over the same data rather
than relying on `value`/`weight` here: **a `NaN` in a DataFrame arrives in
the browser as `null`**, not `NaN` — the Arrow→JSON round-trip has no `NaN`
literal, so a missing value serializes to `null`. `Number(null)` is `0`,
which *is* finite, so a naive `Number.isFinite(value)` check alone would
count that row as a real zero instead of a missing one. `stWeightedAvg`
guards against this explicitly; code written independently over the same
columns should guard the same way.

Same DataFrame-only validation as the other two, checking `value` and
`weight` — a flat pair, not a `num`/`den` leg shape, so it does not share
`stRatio`'s leg validator.

#### Validation

`validate_ratio_columns` (re-exported, above) is the one entry point and the
one `columnDefs` walk for every aggregator's declaration; `AgGrid()` calls it
automatically. The structural rules — shape, numeric options, `num_signs`
length — always run. The field-existence check that catches a typo'd
component name only runs when `AgGrid` is called with a DataFrame, for the
same reason on every aggregator: a grid built entirely from
`grid_options["rowData"]` (`data=None`) has no column set to check names
against, so an unresolvable name reaches the browser uncaught there instead,
silently contributing `0`.

Working examples: `test/grid_ratio_builtin.py` (`stRatio`'s frozen baseline,
against the JavaScript approach it replaces in `test/grid_ratio_js.py`) and
`test/grid_agg_builtin.py` (`den_const`, the `sum` fallback, and both
`stRatioOfRatios` and `stWeightedAvg`), all over the same fixture in
`test/ratio_fixture.py`.

### Export and clipboard

A group row's aggregated cell — for `stRatio`, `stRatioOfRatios` and
`stWeightedAvg` alike — is not a plain number but an `IAggFuncResult` object
carrying `toNumber()` and `toString()`. A leaf row's cell is a plain number
straight off the DataFrame. This fork installs no `defaultCsvExportParams`
and no `processCellForClipboard`; the toolbar's download button calls
`exportDataAsCsv()` with no parameters. So what lands in a CSV depends
entirely on each column's own
[`useValueFormatterForExport`](https://www.ag-grid.com/javascript-data-grid/column-properties-export/)
(an AG-Grid colDef property, default `true`) — measured below and pinned by
`test/test_grid_agg_export.py`.

| `useValueFormatterForExport` | Group cell (measured) | Leaf cell (measured) | `fill_null` cell |
|---|---|---|---|
| `true` (default), **with** a `valueFormatter` | The formatter's own return value — it receives the raw `IAggFuncResult` as `params.value` and must call `.toNumber()` itself before formatting | The same formatter, receiving the raw number as `params.value` | Whatever the formatter renders for `null` |
| `true`, **no** `valueFormatter` configured | Same as `false` below — nothing suppresses `toString()` if there was never anything to format | Same as `false` below | `""` (empty field) |
| `false` | `toString()` — full JavaScript float precision, e.g. `"1.1818181818181819"` | The raw number's own JS string form, e.g. `"400"` | `""` (empty field) |

Traced in the installed `ag-grid-community@36.0.0` package, not assumed:
`CsvCreator` writes each cell as
`this.putInQuotes(rowCellValue.valueFormatted ?? rowCellValue.value)`, and for
a group cell `rowCellValue.value` is the raw `IAggFuncResult` straight out of
`rowNode.aggData` — never unwrapped. `putInQuotes` then does
`typeof value.toString === "function" ? value.toString() : ...`. So the raw
(`useValueFormatterForExport=false`) path calls the value's **`toString()`**,
never `toNumber()` — and every built-in aggregator's `toString()`
(`foldSums.ts`) is `String(value)`, JavaScript's own default number-to-string,
full precision.

**Migrating off a hand-written JavaScript aggregator: this is a precision
change, not just a format change.** The retired JavaScript's value object had
`toString → value.toFixed(4)` — four decimals, always. The built-in
aggregators' `toString()` is `String(value)` — as many digits as the float
needs. A dashboard that exports with `useValueFormatterForExport=False` on
purpose (to get compute-ready raw values, e.g. for a `getDataAsCsv()` round
trip into Google Sheets) will see `"1.1818"` become `"1.1818181818181819"`
after switching to a built-in aggregator, with no code change on its own
side. Two ways to keep the old four-decimal text: leave
`useValueFormatterForExport` at its default (`true`) and attach a
`valueFormatter` that unwraps `toNumber()` and calls `.toFixed(4)`, or
post-process the raw string after export.

A `fill_null` blank cell renders as an empty CSV field either way — the
setting only changes a *present* value's text, never whether `None` renders
blank. All three aggregators behave identically for CSV export — none of
them special-case `useValueFormatterForExport` or `getDataAsCsv()` — which
is what `test/test_grid_agg_export.py` actually measures and pins.

**Clipboard copy (Ctrl+C; this is a read-only grid, so there is no paste)
reaches the same value-resolution logic, but this fork has not measured its
output directly.** `ag-grid-enterprise@36.0.0`'s
`ClipboardService.buildExportParams` ends by calling
`csvCreator.getDataAsCsv(exportParams, true)`, so a clipboard copy runs
through the same `getValueForDisplay`/`useValueFormatterForExport`
value-resolution code the table above describes — for a group cell, the
same raw `IAggFuncResult`. But the `exportParams` it passes differ from a
plain CSV export in ways that change the serialization, not just the
value: `suppressQuotes: true` (so `putInQuotes` returns the value
unmodified instead of explicitly calling `.toString()` — stringification
then happens implicitly, through `+=` string concatenation), a tab
`columnSeparator` instead of a comma, and a `processRowGroupCallback` CSV
export never installs. The resulting cell *text* is likely identical
regardless — `StAggValue` defines no `valueOf`, so JS's `ToPrimitive`
coercion falls through to `toString()` either way — but that is reasoning
about the mechanism, not a measurement of clipboard output, and this repo
has neither a `test/test_grid_agg_export.py` assertion nor any other test
covering it.

Working example: `test/grid_agg_export.py`, over the same fixture, with
`test/test_grid_agg_export.py` pinning the exact CSV text for both settings.

### Toolbar

```python
AgGrid(
    df,
    show_toolbar=True,           # overlay toolbar on hover
    show_search=True,            # quick search filter
    show_download_button=True,   # CSV export button
    key="my_grid",
)
```

## API Reference

### `AgGrid()`

| Parameter | Type | Default | Description |
|---|---|---|---|
| `data` | DataFrame / str | None | Data to display |
| `grid_options` | dict | None | AG-Grid options (auto-generated from data if None) |
| `height` | int | 400 | Grid height in px (None for auto-height) |
| `collect` | list[str] | `["getSelectedRows"]` | AG-Grid API methods to auto-collect |
| `update_on` | list | `["selectionChanged", "filterChanged", "sortChanged"]` | Events triggering auto-collect |
| `allow_unsafe_jscode` | bool | False | Allow JsCode in grid_options |
| `enable_enterprise_modules` | bool/str | False | Enable enterprise features |
| `license_key` | str | None | AG-Grid license key |
| `columns_state` | dict | None | Initial column state |
| `theme` | str/StAggridTheme | "streamlit" | Grid theme |
| `custom_css` | dict | None | Custom CSS rules |
| `key` | str | None | Streamlit widget key |
| `show_toolbar` | bool | False | Show toolbar |
| `show_search` | bool | True | Show search in toolbar |
| `show_download_button` | bool | True | Show CSV download |
| `on_grid_state_change` | callable | None | Callback on state change |
| `on_api_response_change` | callable | None | Callback on API response |

### `AgGridResult`

| Property | Type | Description |
|---|---|---|
| `.selected_rows` | DataFrame / None | Selected rows |
| `.column_state` | list[dict] / None | Column state |
| `.filter_model` | dict / None | Active filters |
| `.sort_model` | list[dict] / None | Active sorts |
| `.grid_state` | dict / None | Full grid state |
| `.event_name` | str / None | Triggering event name |
| `.event_data` | dict / None | Serialized event data |
| `.api_response` | dict / None | Explicit API call response |
| `.data` | DataFrame / None | Original input data |
| `.get(key, default)` | Any | Access any collected value |

### `call_grid_api(key, method, params=None)`

Queue an explicit AG-Grid API call. Use inside `@st.fragment` with `st.rerun(scope="fragment")`.

## Full Example

```python
import streamlit as st
import pandas as pd
from st_aggrid import AgGrid, GridOptionsBuilder, call_grid_api

st.set_page_config(layout="wide")

df = pd.DataFrame({
    "Name": ["Alice", "Bob", "Charlie", "Diana", "Eve"],
    "Department": ["Eng", "Eng", "Sales", "Sales", "Eng"],
    "Salary": [95000, 88000, 72000, 81000, 99000],
})

gb = GridOptionsBuilder.from_dataframe(df)
gb.configure_selection("multiple", use_checkbox=True)
gb.configure_column("Salary", type="numericColumn")
grid_options = gb.build()

@st.fragment
def grid_section():
    result = AgGrid(
        df,
        grid_options=grid_options,
        collect=["getSelectedRows", "getColumnState"],
        update_on=["selectionChanged", ("columnResized", 300)],
        show_toolbar=True,
        key="demo",
    )

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Selected Rows")
        if result.selected_rows is not None:
            st.dataframe(result.selected_rows)

    with col2:
        if st.button("Show Column State"):
            call_grid_api("demo", "getColumnState")
            st.rerun(scope="fragment")

        if result.api_response:
            st.json(result.api_response)

grid_section()
```