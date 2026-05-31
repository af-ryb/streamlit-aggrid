"""Streamlit app: pivot-mode value-column visibility via columns_state merge.

Pivot mode (enterprise). One row-group column (`grp`) and three value columns
(`x`, `y`, `z`). Checkboxes include / exclude value columns; `visibility_state`
expresses that through `aggFunc` (shown -> "sum", hidden -> None) and the delta
is applied with `columns_state_mode="merge"`.

The key regression this guards: toggling a value column must NOT clear the row
group. The merge-mode apply only calls setRowGroupColumns when the delta carries
row-group entries, which a value-only delta does not.
"""

import pandas as pd
import streamlit as st

from st_aggrid import AgGrid, visibility_state

GOVERNED = ["x", "y", "z"]  # value columns

df = pd.DataFrame(
    {
        "grp": ["g1", "g1", "g2", "g2"],
        "x": [1, 2, 3, 4],
        "y": [5, 6, 7, 8],
        "z": [9, 10, 11, 12],
    }
)

included = [c for c in GOVERNED if st.checkbox(f"val_{c}", value=True, key=f"val_{c}")]

delta = visibility_state(
    governed_col_ids=GOVERNED,
    included_col_ids=included,
    pivot_mode=True,
    value_agg_func="sum",
)

grid_options = {
    "pivotMode": True,
    "groupDisplayType": "multipleColumns",
    "groupDefaultExpanded": -1,
    "autoGroupColumnDef": {"cellRendererParams": {"suppressCount": True}},
    "columnDefs": [
        {"field": "grp", "rowGroup": True, "enableRowGroup": True},
        {"field": "x", "aggFunc": "sum"},
        {"field": "y", "aggFunc": "sum"},
        {"field": "z", "aggFunc": "sum"},
    ],
}

AgGrid(
    df,
    grid_options=grid_options,
    columns_state=delta,
    columns_state_mode="merge",
    enable_enterprise_modules=True,
    collect=["getColumnState"],
    update_on=["columnValueChanged"],
    key="grid_pivot_vis",
)
