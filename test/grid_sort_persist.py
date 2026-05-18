"""Streamlit app exercising interactive sort persistence across reruns.

Regression target: a default sort declared on a column via the AG-Grid
``initialSort`` / ``initialSortIndex`` colDef properties must apply only on
first render. A sort the user applies by clicking a header has to survive
later reruns — even when those reruns change ``rowData`` and ``columnDefs``
(e.g. a date-range filter that also rewrites a header label).

Before the fix, ``updateGridOptions`` re-processed ``columnDefs`` and let the
sort fall back to the ``initialSort`` default, dropping the user's sort.
"""

import pandas as pd
import streamlit as st
from st_aggrid import AgGrid

# Two "date ranges" — switching between them changes rowData AND the value
# column's headerName, so columnDefs differ between reruns and the
# updateGridOptions code path runs (the path that used to reset the sort).
RANGES = {
    "2024": pd.DataFrame(
        {"id": [3, 1, 2], "name": ["cherry", "apple", "banana"]}
    ),
    "2025": pd.DataFrame(
        {"id": [6, 4, 5], "name": ["fig", "date", "elderberry"]}
    ),
}

if "sort_persist_range" not in st.session_state:
    st.session_state.sort_persist_range = "2024"

st.button(
    "Switch date range",
    on_click=lambda: st.session_state.update(
        sort_persist_range="2025"
        if st.session_state.sort_persist_range == "2024"
        else "2024"
    ),
)

selected = st.session_state.sort_persist_range
df = RANGES[selected]

grid_options = {
    "columnDefs": [
        # Default sort: id descending. `initial*` means first render only —
        # an interactive sort on another column must not be overridden.
        {"field": "id", "initialSort": "desc", "initialSortIndex": 0},
        {"field": "name", "headerName": f"name ({selected})"},
    ],
}

AgGrid(
    df,
    grid_options=grid_options,
    debug=True,
    key="grid_sort_persist",
)
