"""Streamlit app: gridReady / firstDataRendered as zero-interaction triggers.

One grid at a time, chosen by a radio, so every `[useAutoCollect]` console line
on the page belongs to exactly one grid and the test can count collector
invocations directly. Case "none" renders no grid and is where every test lands
before clicking its own case — otherwise a default case's fires would already
be in the console log.

Fires are also accumulated on the Python side through `on_grid_state_change`,
which is what proves the value reached the host with the right event name and
post-restore content. The count itself is read from the console: Streamlit
invokes the callback only when the component's state value changes, so a
second, byte-identical collect would leave no trace here.

Run standalone with:  streamlit run test/grid_lifecycle_collect.py
"""

import json

import pandas as pd
import streamlit as st

from st_aggrid import AgGrid, JsCode

DF = pd.DataFrame(
    {
        "region": ["DE", "FR", "IT", "CA"],
        "channel": ["web", "web", "app", "app"],
        "metric": [10, 20, 30, 40],
    }
)
#: Same columns, no rows. AG-Grid dispatches `firstDataRendered` from the first
#: rendered body row, so this grid must never fire it.
EMPTY = DF.iloc[0:0]

COMMON = {
    "columnDefs": [
        {"colId": "region", "field": "region"},
        {"colId": "channel", "field": "channel"},
        {"colId": "metric", "field": "metric", "type": "numericColumn"},
    ],
    "animateRows": False,
}

#: Neither the row group nor the hidden column is declared in `columnDefs`, so a
#: pre-restore snapshot would look nothing like this.
RESTORE_STATE = [
    {"colId": "region", "rowGroup": True, "rowGroupIndex": 0},
    {"colId": "channel", "hide": True},
    {"colId": "metric"},
]

#: Writes to `window` rather than to the DOM: the collect triggers a Streamlit
#: rerun, and a counter rendered by the app would be reset by it.
USER_HANDLER = JsCode(
    "function(event) {"
    " window.__userFirstDataRendered = (window.__userFirstDataRendered || 0) + 1;"
    " }"
)


def recorder(key):
    """A callback that appends each collected event name to a per-grid list."""
    fires = st.session_state.setdefault("fires", {})

    def _record(result):
        fires.setdefault(key, []).append(result.event_name)

    return _record


def show_fires(key):
    fires = st.session_state.get("fires", {}).get(key, [])
    st.html(f"<pre data-testid='fires-{key}'>{','.join(fires)}</pre>")


CASE = st.radio(
    "Case",
    options=[
        "none",
        "gridReady",
        "firstDataRendered",
        "both",
        "restore",
        "empty",
        "chain",
    ],
)

if CASE == "gridReady":
    AgGrid(
        DF,
        grid_options=COMMON,
        collect=["getColumnState"],
        update_on=["gridReady"],
        debug=True,
        on_grid_state_change=recorder("lc_ready"),
        key="lc_ready",
    )
    show_fires("lc_ready")

elif CASE == "firstDataRendered":
    AgGrid(
        DF,
        grid_options=COMMON,
        collect=["getColumnState"],
        update_on=["firstDataRendered"],
        debug=True,
        on_grid_state_change=recorder("lc_first"),
        key="lc_first",
    )
    show_fires("lc_first")

elif CASE == "both":
    AgGrid(
        DF,
        grid_options=COMMON,
        collect=["getColumnState"],
        update_on=["gridReady", "firstDataRendered"],
        debug=True,
        on_grid_state_change=recorder("lc_both"),
        key="lc_both",
    )
    show_fires("lc_both")

elif CASE == "restore":
    # `columns_state_mode="merge"` is the point of this case, not an
    # incidental setting: in the default `replace` mode, `columns_state` is
    # restored through the `initialState` prop at grid creation, before
    # `onGridReady` runs at all — so a collect hoisted to the first statement
    # of `onGridReady` would still see the restored layout and this case
    # would pin nothing. Merge mode restores nothing pre-paint (the
    # `initialState` memo returns `undefined`), so `applyColumnState` and
    # `setRowGroupColumns` run inside `onGridReady`, where the ordering
    # against the `gridReady` collect is real.
    result = AgGrid(
        DF,
        grid_options=COMMON,
        collect=["getColumnState"],
        update_on=["gridReady"],
        columns_state=RESTORE_STATE,
        columns_state_mode="merge",
        enable_enterprise_modules=True,
        debug=True,
        on_grid_state_change=recorder("lc_restore"),
        key="lc_restore",
    )
    show_fires("lc_restore")
    st.html(
        "<pre data-testid='state-lc_restore'>"
        f"{json.dumps(result.column_state or [])}</pre>"
    )

elif CASE == "empty":
    AgGrid(
        EMPTY,
        grid_options=COMMON,
        collect=["getColumnState"],
        update_on=["firstDataRendered"],
        debug=True,
        on_grid_state_change=recorder("lc_empty"),
        key="lc_empty",
    )
    show_fires("lc_empty")

elif CASE == "chain":
    AgGrid(
        DF,
        grid_options={**COMMON, "onFirstDataRendered": USER_HANDLER},
        collect=["getColumnState"],
        update_on=["firstDataRendered"],
        allow_unsafe_jscode=True,
        debug=True,
        on_grid_state_change=recorder("lc_chain"),
        key="lc_chain",
    )
    show_fires("lc_chain")
