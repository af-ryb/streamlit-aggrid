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

### Ratio aggregation without JavaScript

A ratio cannot be rolled up by rolling up the ratio: a group's value is
`Σnumerator / Σdenominator`, never the average of its children's ratios. The
built-in `stRatio` aggregator computes that from a declaration, so a grid that
needed `allow_unsafe_jscode` only for its ratio columns no longer needs it.

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
| `den` | yes | — | Field names summed to form the denominator |
| `num_signs` | no | all `1` | Per-term signs, e.g. `[1, -1]` for `(a − b)/c` |
| `multiplier` | no | `1.0` | Applied inside the numerator (CPM uses `1000`) |
| `scale` | no | `1.0` | Applied to the final value (sec→min uses `1/60`) |
| `fill_null` | no | `None` | Value when `Σden == 0`; `None` renders an empty cell |

The value is `((Σ signᵢ·numᵢ) · multiplier / Σden) · scale`, where each field
name resolves to the sum of that field over the node's subtree. It is correct at
every grouping level, in pivot cells, in pivot row totals and in total rows.

Field names are read from the **row data**, so a component needs no column of
its own — but it must be in the DataFrame. A name that is not raises a
`ValueError` when the grid is built, because a missing component would
otherwise contribute `0` and skew the ratio silently. That check only runs
when `AgGrid` is called with a DataFrame: a grid fed through
`grid_options["rowData"]` (`data=None`) has no column set to check field names
against, so a typo'd `num`/`den` entry is not caught — it reaches the browser
and contributes `0`, exactly the silent failure this check exists to prevent.

Ratio columns sort numerically, with empty cells last in both directions. A
`comparator` you set yourself is left alone. Supplying your own
`aggFuncs["stRatio"]` overrides the built-in; run with `debug=True` to see that
logged.

The aggregator is for row grouping and pivot; it is not aware of `treeData`
and should not be used with it.

Working examples: `test/grid_ratio_builtin.py` (built-in) and
`test/grid_ratio_js.py` (the JavaScript approach it replaces), both over the
same fixture in `test/ratio_fixture.py`.

### Export and clipboard

A group row's aggregated cell — for `stRatio`, `stRatioOfRatios` and
`stWeightedAvg` alike — is not a plain number but an `IAggFuncResult` object
carrying `toNumber()` and `toString()`. A leaf row's cell is a plain number
straight off the DataFrame. This fork installs no `defaultCsvExportParams`
and no `processCellForClipboard`; the toolbar's download button calls
`exportDataAsCsv()` with no parameters. So what lands in a CSV — or a
clipboard copy (Ctrl+C; this is a read-only grid, so there is no paste),
which goes through the exact same code path in AG-Grid 36
(`ClipboardService.buildExportParams` calls `csvCreator.getDataAsCsv()`
internally) — depends entirely on each column's own
[`useValueFormatterForExport`](https://www.ag-grid.com/javascript-data-grid/column-properties-export/)
(an AG-Grid colDef property, default `true`):

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
blank. All three aggregators behave identically for export and clipboard;
none of them special-case `useValueFormatterForExport`, `getDataAsCsv()`, or
clipboard copy.

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