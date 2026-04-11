# streamlit-aggrid v2

Streamlit component for [AG-Grid](https://www.ag-grid.com/) built on Custom Components v2 (no iframe).

AG-Grid version: [35.2.1](https://www.ag-grid.com/archive/35.2.1/)

## Install

From git:

```bash
pip install git+https://github.com/af-ryb/streamlit-aggrid.git@v2_component
```

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