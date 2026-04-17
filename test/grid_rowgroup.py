"""Streamlit app exercising runtime rowGroup toggling.

Separate from ``grid_data_render.py`` because AG-Grid modules are registered
once per page load (see ``registerModules`` in ``AgGridComponent.tsx``) —
the first grid on the page decides whether enterprise features are available,
and row grouping requires enterprise.
"""

import pandas as pd
import streamlit as st
from st_aggrid import AgGrid

TESTS = [1]

if 1 in TESTS:
    """Toggle rowGroup after initial render with rowGroupIndex=None.

    Mirrors the hitapps_analytics-funnel shape: pivot mode, one
    always-grouped column (``level_order``) and one dynamically-grouped
    column (``groupby``) whose ``rowGroupIndex`` is ``None`` when the widget
    is off and ``1`` when it's on. ``initialRowGroupIndex`` is always set.
    """
    if "toggle_rowgroup_enabled" not in st.session_state:
        st.session_state.toggle_rowgroup_enabled = False
    st.button(
        "Toggle rowGroup",
        on_click=lambda: st.session_state.update(
            toggle_rowgroup_enabled=not st.session_state.toggle_rowgroup_enabled
        ),
    )

    toggle_df = pd.DataFrame(
        {
            "level_order": [1, 1, 2, 2, 3, 3],
            "groupby": ["a", "b", "a", "b", "a", "b"],
            "value": [10, 20, 30, 40, 50, 60],
        }
    )
    toggle_grid_options = {
        "pivotMode": True,
        "groupDisplayType": "multipleColumns",
        "autoGroupColumnDef": {"cellRendererParams": {"suppressCount": True}},
        "groupDefaultExpanded": -1,
        "columnDefs": [
            {
                "field": "level_order",
                "enableRowGroup": True,
                "initialRowGroupIndex": 0,
            },
            {
                "field": "groupby",
                "enableRowGroup": True,
                "rowGroupIndex": 1
                if st.session_state.toggle_rowgroup_enabled
                else None,
                "initialRowGroupIndex": 1,
            },
            {"field": "value", "aggFunc": "sum"},
        ],
    }
    AgGrid(
        toggle_df,
        grid_options=toggle_grid_options,
        enable_enterprise_modules=True,
        key="grid_toggle_rowgroup",
    )
