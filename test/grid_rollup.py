"""Streamlit app: the built-in `stRollup` aggregator over `rollup_fixture`.

Each grid exposes its API as `window.__rollupApis[name]`, so the suite reads
group values through `node.aggData` rather than the DOM and drives regrouping
with `setRowGroupColumns` (what a Row Groups panel drag does).

Run standalone with:  streamlit run test/grid_rollup.py
"""

import streamlit as st

from st_aggrid import AgGrid, JsCode

from rollup_fixture import DIMENSIONS, corrupt, cube_frame, leaves_frame

EXPOSE = (
    "function(p){ (window.__rollupApis = window.__rollupApis || {})['%s'] = p.api; }"
)


def grid_options(name: str, groups=DIMENSIONS, **extra) -> dict:
    def dimension(field: str) -> dict:
        column = {"field": field, "enableRowGroup": True, "filter": "agTextColumnFilter"}
        if field in groups:
            column.update(rowGroup=True, rowGroupIndex=groups.index(field), hide=True)
        return column

    options = {
        "columnDefs": [
            {"field": "row_no", "hide": True},
            dimension("event_date"),
            dimension("app_version"),
            {"field": "platform", "enableRowGroup": True},
            {
                "field": "dau",
                "aggFunc": "stRollup",
                "allowedAggFuncs": ["stRollup"],
                "filter": "agNumberColumnFilter",
            },
        ],
        "groupDefaultExpanded": -1,
        "grandTotalRow": "bottom",
        "suppressAggFuncInHeader": True,
        "suppressRowVirtualisation": True,
        "onGridReady": JsCode(EXPOSE % name),
    }
    options.update(extra)
    return options


def show(name, leaves, totals, use_json=False, **extra):
    st.subheader(name)
    AgGrid(
        leaves,
        grid_options=grid_options(name, **extra),
        rollup={"data": totals, "dimensions": list(DIMENSIONS)},
        allow_unsafe_jscode=True,
        enable_enterprise_modules=True,
        use_json_serialization=use_json,
        height=420,
        key=f"rollup_{name}",
    )


show("base", leaves_frame(), cube_frame())
show("datetime", leaves_frame("datetime64"), cube_frame("datetime64"), groups=("event_date",))
show("json", leaves_frame(), cube_frame(), use_json=True)
show("corrupt", leaves_frame(), corrupt(cube_frame()))
show("suppress", leaves_frame(), cube_frame(), suppressAggFilteredOnly=True)
show("pivot", leaves_frame(), cube_frame(), pivotMode=True)
bump = st.toggle("bump totals", key="bump")
# The JSON grid is the one that needs the refresh effect (equal rows keep the
# same array); the Arrow twin guards the path that re-aggregates on its own.
show("refresh", leaves_frame(), cube_frame(bump=1 if bump else 0), use_json=True)
show("refresh_arrow", leaves_frame(), cube_frame(bump=1 if bump else 0))
