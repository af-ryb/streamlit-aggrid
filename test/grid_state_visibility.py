"""Streamlit app: control-driven column visibility via columns_state merge mode.

Normal (non-pivot) mode. Checkboxes act as "inline controls" that include /
exclude governed columns. `visibility_state` turns the selection into a partial
ColumnState[] delta applied with `columns_state_mode="merge"`, so the structural
`id` column (and column order) is never disturbed by a visibility toggle.
"""

import pandas as pd
import streamlit as st

from st_aggrid import AgGrid, derive_user_hidden, visibility_state

GOVERNED = ["a", "b", "c", "d"]

df = pd.DataFrame(
    {
        "id": [1, 2, 3],
        "a": [10, 20, 30],
        "b": [11, 21, 31],
        "c": [12, 22, 32],
        "d": [13, 23, 33],
    }
)

# Inline controls: one checkbox per governed column ("show_<col>").
included = [c for c in GOVERNED if st.checkbox(f"show_{c}", value=True, key=f"inc_{c}")]

user_hidden = st.session_state.get("user_hidden", [])
delta = visibility_state(
    governed_col_ids=GOVERNED,
    included_col_ids=included,
    user_hidden_col_ids=user_hidden,
)

grid_options = {
    "columnDefs": [
        {"field": "id"},
        {"field": "a"},
        {"field": "b"},
        {"field": "c"},
        {"field": "d"},
    ],
}

res = AgGrid(
    df,
    grid_options=grid_options,
    columns_state=delta,
    columns_state_mode="merge",
    collect=["getColumnState"],
    update_on=["columnVisible"],
    key="grid_visibility",
)

if res.column_state is not None:
    st.session_state["user_hidden"] = derive_user_hidden(
        res.column_state,
        governed_col_ids=GOVERNED,
        control_included_at_capture=included,
    )
