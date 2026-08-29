"""Streamlit app: interactive Row Groups reorder keeps the multipleColumns
auto-group columns in sync.

Exposes the grid API via a JsCode ``onGridReady`` so the e2e test can drive
``setRowGroupColumns([...])`` — the same internal effect as dragging to reorder
the Row Groups panel (which AG-Grid's drag service does not reliably expose to
Playwright). Guards the ``columnRowGroupChanged -> reorderAutoGroupColumns``
listener in ``AgGridComponent.tsx``: an interactive reorder never passes through
the data-update effects, so the listener is the only thing that re-syncs the
displayed group columns.
"""

import pandas as pd
import streamlit as st

from st_aggrid import AgGrid, JsCode

DIMS = {"day": "Day", "network": "Network", "ad_unit": "Ad Unit Name"}
df = pd.DataFrame(
    {
        "day": ["2026-06-21"] * 4,
        "network": ["APPLOVIN", "APPLOVIN", "UNITY", "UNITY"],
        "ad_unit": ["A_inter", "A_rew", "B_inter", "B_rew"],
        "installs": [100, 200, 300, 400],
    }
)
row_defs = [
    {
        "field": f,
        "headerName": DIMS[f],
        "enableRowGroup": True,
        "initialRowGroupIndex": i,
        "initialRowGroup": True,
    }
    for i, f in enumerate(["day", "network", "ad_unit"])
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
    "onGridReady": JsCode("function(p){ window.__gridApi = p.api; }"),
}

AgGrid(
    df,
    grid_options=grid_options,
    allow_unsafe_jscode=True,
    enable_enterprise_modules=True,
    key="grid_rowgroup_interactive",
)
