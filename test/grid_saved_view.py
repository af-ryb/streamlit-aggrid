"""Streamlit app: full saved-view restore via the raw `initial_state` prop.

A radio picks one of two views, each a raw AG-Grid GridState (hidden columns +
sort). The grid `key` includes the view id, so switching views remounts the
component and AG-Grid re-reads `initialState`.
"""

import pandas as pd
import streamlit as st

from st_aggrid import AgGrid

df = pd.DataFrame(
    {
        "a": [3, 1, 2],
        "b": [4, 5, 6],
        "c": [7, 8, 9],
    }
)

VIEWS = {
    "view_hide_b": {
        "columnVisibility": {"hiddenColIds": ["b"]},
    },
    "view_hide_c_sort_a": {
        "columnVisibility": {"hiddenColIds": ["c"]},
        "sort": {"sortModel": [{"colId": "a", "sort": "desc"}]},
    },
}

view = st.radio("View", list(VIEWS), key="view")

AgGrid(
    df,
    grid_options={
        "columnDefs": [{"field": "a"}, {"field": "b"}, {"field": "c"}],
    },
    initial_state=VIEWS[view],
    key=f"grid_view_{view}",  # key change => remount => initialState re-read
)
