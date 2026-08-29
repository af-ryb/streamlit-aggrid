"""Two grids on one page, community rendered BEFORE enterprise.

Guards two regressions:

1. Module registration. A single module-level "already registered" latch lets
   the first grid decide which AG-Grid bundle every later grid gets, so the
   enterprise grid's sidebar would never render.
2. Streamlit hotkey containment. `run_count` increments on every script run,
   so a rerun accidentally triggered by pressing "r" over a grid cell is
   visible in the DOM.
"""

import pandas as pd
import streamlit as st

from st_aggrid import AgGrid

st.session_state["run_count"] = st.session_state.get("run_count", 0) + 1

# A keyed container so the test can locate the counter as `.st-key-run_count`,
# the same addressing every other e2e test uses. `st.write` alone would need a
# text locator, which matches nested elements and trips Playwright's strict mode.
with st.container(key="run_count"):
    st.write(st.session_state["run_count"])

df = pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})

st.subheader("community")
AgGrid(df, key="community_grid", height=150)

st.subheader("enterprise")
AgGrid(
    df,
    key="enterprise_grid",
    height=150,
    enable_enterprise_modules=True,
    grid_options={
        "columnDefs": [{"field": "a"}, {"field": "b"}],
        "sideBar": {"toolPanels": ["columns"]},
    },
)
