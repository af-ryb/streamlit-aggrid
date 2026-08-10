"""Streamlit app: ratio aggregation via the built-in `stRatio` aggregator.

The counterpart to `grid_ratio_js.py`. Same fixture, same grouping, same
columns — the only difference is that no JavaScript crosses the boundary: the
ratio is declared as data in `colDef.context["stRatio"]` and computed by the
aggregator the fork registers.

Grid 0 runs with `allow_unsafe_jscode` off entirely, which is the point of the
feature: a grid that needed unsafe JavaScript only for its ratios no longer
needs it at all. Its cells render the value object's own `toString()`.

Grid 1 is the same grid plus the consumer's existing `JsCode` valueFormatter,
which branches on `typeof v === 'object'`. It proves formatters keep working
untouched, and it renders four-decimal text directly comparable to
`grid_ratio_js.py`.

Run standalone with:  streamlit run test/grid_ratio_builtin.py
"""

import streamlit as st

from st_aggrid import AgGrid, JsCode

from ratio_fixture import (
    COMPONENT_FIELDS,
    PIVOT_DIM,
    RATIO_SPECS,
    ROW_DIM,
    ratio_dataframe,
)

# Copied verbatim from the consumer (marketing/js_funcs.py). Unchanged on
# purpose: the claim under test is that existing formatters need no edit.
js_ratio_value_formatter = JsCode("""
function(params) {
    const v = params.value;
    if (v == null) { return ''; }
    if (typeof v === 'object') {
        return (v.value != null && !isNaN(v.value)) ? v.value.toFixed(4) : '';
    }
    return isNaN(v) ? '' : Number(v).toFixed(4);
}
""")


# A deliberately backwards comparator, only on the formatted grid's `cpi`. It
# exists so a test can prove the fork leaves a caller-supplied comparator
# alone; the fork's own comparator would sort the other way.
js_reversed_comparator = JsCode("""
function(a, b) {
    const x = (a && typeof a.toNumber === 'function') ? a.toNumber() : a;
    const y = (b && typeof b.toNumber === 'function') ? b.toNumber() : b;
    if (x == null || y == null) { return 0; }
    return x > y ? -1 : (x < y ? 1 : 0);
}
""")


def ratio_column_defs(formatted: bool) -> list[dict]:
    """One colDef per spec. The ratio is declared, never scripted."""
    columns = []
    for spec in RATIO_SPECS:
        column = {
            "colId": spec.col_id,
            "field": spec.col_id,
            "headerName": spec.header,
            "type": "numericColumn",
            "aggFunc": "stRatio",
            "context": {"stRatio": spec.to_context()},
            "width": 130,
        }
        if formatted:
            column["valueFormatter"] = js_ratio_value_formatter
        if formatted and spec.col_id == "cpi":
            column["comparator"] = js_reversed_comparator
        columns.append(column)
    return columns


def component_column_defs() -> list[dict]:
    return [
        {"colId": name, "field": name, "aggFunc": "sum", "width": 110,
         "type": "numericColumn"}
        for name in COMPONENT_FIELDS
    ]


COMMON_OPTIONS = {
    "groupDefaultExpanded": -1,
    "suppressAggFuncInHeader": True,
    "grandTotalRow": "bottom",
    "autoGroupColumnDef": {
        "cellRendererParams": {"suppressCount": True},
        "minWidth": 140,
    },
    # Every cell in the DOM, so an assertion can read an off-screen column.
    "suppressColumnVirtualisation": True,
    "suppressRowVirtualisation": True,
}


def rowgroup_grid_options(formatted: bool) -> dict:
    return {
        **COMMON_OPTIONS,
        "groupDisplayType": "multipleColumns",
        "columnDefs": [
            {"colId": ROW_DIM, "field": ROW_DIM, "rowGroup": True, "rowGroupIndex": 0},
            {"colId": PIVOT_DIM, "field": PIVOT_DIM, "rowGroup": True, "rowGroupIndex": 1},
            *ratio_column_defs(formatted),
            *component_column_defs(),
        ],
    }


st.set_page_config(layout="wide")

df = ratio_dataframe()

st.subheader("Row grouping — no unsafe JavaScript at all")
AgGrid(
    df,
    grid_options=rowgroup_grid_options(formatted=False),
    enable_enterprise_modules=True,
    height=520,
    key="ratio_builtin_rowgroup",
)

st.subheader("Row grouping — with the consumer's existing valueFormatter")
AgGrid(
    df,
    grid_options=rowgroup_grid_options(formatted=True),
    allow_unsafe_jscode=True,
    enable_enterprise_modules=True,
    height=520,
    key="ratio_builtin_formatted",
)

# The built-in is a default, not a reservation: a caller who supplies their own
# `stRatio` keeps it. This grid returns a constant so the override is
# unmistakable on screen and in a test.
js_constant_ratio = JsCode("""
function ConstantRatio(params) {
    return 42;
}
""")

st.subheader("Row grouping — caller-supplied stRatio overrides the built-in")
AgGrid(
    df,
    grid_options={
        **rowgroup_grid_options(formatted=False),
        "aggFuncs": {"stRatio": js_constant_ratio},
    },
    allow_unsafe_jscode=True,
    enable_enterprise_modules=True,
    height=260,
    debug=True,
    key="ratio_builtin_override",
)


def pivot_grid_options() -> dict:
    """Campaign down the rows, country across the columns, with pivot row
    totals and a grand-total row — the shape the consumer's marketing
    dashboard runs."""
    return {
        **COMMON_OPTIONS,
        "pivotMode": True,
        "groupDisplayType": "multipleColumns",
        "pivotRowTotals": "after",
        "columnDefs": [
            {"colId": ROW_DIM, "field": ROW_DIM, "rowGroup": True, "rowGroupIndex": 0},
            {"colId": PIVOT_DIM, "field": PIVOT_DIM, "pivot": True, "pivotIndex": 0},
            *ratio_column_defs(formatted=False),
            *component_column_defs(),
        ],
    }


st.subheader("Pivot — campaign down, country across")
AgGrid(
    df,
    grid_options=pivot_grid_options(),
    enable_enterprise_modules=True,
    height=320,
    key="ratio_builtin_pivot",
)


# `registerStRatio` installs the null-ordering comparator by walking
# `columnDefs`, and the consumer this feature exists for wraps every metric
# column in a column group. Nesting the ratio columns under `children` puts
# that descent under test instead of under inspection.
st.subheader("Row grouping — ratio columns nested in a column group")
AgGrid(
    df,
    grid_options={
        **COMMON_OPTIONS,
        "groupDisplayType": "multipleColumns",
        "columnDefs": [
            {"colId": ROW_DIM, "field": ROW_DIM, "rowGroup": True, "rowGroupIndex": 0},
            {
                "headerName": "Ratios",
                "groupId": "ratios",
                "children": ratio_column_defs(formatted=False),
            },
            *component_column_defs(),
        ],
    },
    enable_enterprise_modules=True,
    height=260,
    key="ratio_builtin_grouped_cols",
)
