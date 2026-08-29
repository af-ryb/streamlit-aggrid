"""Streamlit app: multipleColumns row-group column ordering across a
row-dimension change.

Three row-group dimensions (row_1=day, row_2=<cycled>, row_3=ad_unit) configured
with ``initialRowGroupIndex`` (initial-only), ``groupDisplayType:
'multipleColumns'`` and auto-group columns pinned left — mirroring the marketing
pivot. Cycling row_2 rebuilds columnDefs with a different dimension at group
level 1.

Regression guard: from AG-Grid v36 a newly-created dimension's auto-group column
is inserted at the FRONT of the column order; the component must re-order the
auto-group columns back to row-group order (see ``reorderAutoGroupColumns`` in
``AgGridComponent.tsx``) so the swapped dimension stays at its assigned level
instead of jumping to the leftmost group column.
"""

import pandas as pd
import streamlit as st

from st_aggrid import AgGrid

DIMS = {
    "day": "Day",
    "network": "Network",
    "ad_unit": "Ad Unit Name",
    "campaign": "Campaign",
}
ROW2_CYCLE = ["network", "campaign"]

if "r2" not in st.session_state:
    st.session_state.r2 = 0
st.button(
    "Cycle row_2",
    on_click=lambda: st.session_state.update(
        r2=(st.session_state.r2 + 1) % len(ROW2_CYCLE)
    ),
)
row2 = ROW2_CYCLE[st.session_state.r2]

df = pd.DataFrame(
    {
        "day": ["2026-06-21"] * 4,
        "network": ["APPLOVIN", "APPLOVIN", "UNITY", "UNITY"],
        "ad_unit": ["A_inter", "A_rew", "B_inter", "B_rew"],
        "campaign": ["c1", "c1", "c2", "c2"],
        "installs": [100, 200, 300, 400],
    }
)

row_values = ["day", row2, "ad_unit"]  # row_1, row_2, row_3
row_defs = [
    {
        "field": f,
        "headerName": DIMS[f],
        "enableRowGroup": True,
        "initialRowGroupIndex": i,
        "initialRowGroup": True,
    }
    for i, f in enumerate(row_values)
]

grid_options = {
    "pivotMode": True,
    "groupDisplayType": "multipleColumns",
    "groupDefaultExpanded": -1,
    "autoGroupColumnDef": {
        "cellRendererParams": {"suppressCount": True},
        "pinned": "left",
    },
    "columnDefs": row_defs
    + [{"field": "installs", "headerName": "INSTALLS", "aggFunc": "sum"}],
}

AgGrid(
    df,
    grid_options=grid_options,
    enable_enterprise_modules=True,
    key="grid_rowgroup_order",
)
