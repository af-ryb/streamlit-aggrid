"""Streamlit app: the reader's per-column colour-scale picker.

Grids over `color_scale_fixture.py`, which also owns the expected colours:

  0  flat, interactive — a declared column (`metric_a`), an undeclared numeric
     one (`metric_b`), a text column, a `fill` column, a column with its own
     `cellStyle`, and a column the page switched off with `False`. Its
     `update_on` does not name `stColorScaleChanged`, so a menu action must
     repaint without a rerun; `runs=` is the counter that proves it.
  1  pivot, interactive, Columns side bar open — one choice must reach every
     result column of a metric, from a header and from the panel.
  2  flat, NOT interactive — the same columns as the picker would touch. Must
     behave exactly as it did before the picker existed.
  3  interactive, with a caller-supplied `getMainMenuItems` — the built-in
     item is appended, the caller's is kept.
  4  interactive, state round trip — mounted with a saved choice, collects
     `stGetColorScaleState` on `stColorScaleChanged`, feeds the result back,
     can be remounted (`remount`) and config-updated (`flip option`).
  5  pivot, interactive, mounted with a saved choice — the override layer in
     pivot mode with no menu involved.

Grids keep their indices; a new grid is always appended.

Run standalone with:  streamlit run test/grid_color_scale_picker.py
"""

import json

import streamlit as st

from st_aggrid import AgGrid, JsCode

from color_scale_fixture import color_scale_dataframe

df = color_scale_dataframe()

COMMON_OPTIONS = {
    "suppressColumnVirtualisation": True,
    "suppressRowVirtualisation": True,
    "animateRows": False,
}
INTERACTIVE = {"stColorScale": {"interactive": True}}

#: Flat grey, nothing a scheme would ever produce.
OWN_STYLE = JsCode("function(params) { return {backgroundColor: 'rgb(1, 2, 3)'}; }")
FILL_COLOR = "rgb(9, 8, 7)"

CALLER_MENU = JsCode(
    """function(params) {
         return params.defaultItems.concat([{name: 'Caller item'}]);
       }"""
)

st.session_state.runs = st.session_state.get("runs", 0) + 1
st.text(f"runs={st.session_state.runs}")


def metric(field, color_scale=None, col_id=None, **extra):
    col = {"colId": col_id or field, "field": field, "width": 130, **extra}
    if color_scale is not None:
        col["context"] = {"stColorScale": color_scale}
    return col


def flat_columns():
    return [
        {"colId": "region", "field": "region"},
        {"colId": "country", "field": "country"},
        metric("metric_a", {"scheme": "neutral"}),
        metric("metric_b"),
    ]


def pivot_columns():
    return [
        {"colId": "country", "field": "country", "rowGroup": True},
        {"colId": "region", "field": "region", "pivot": True},
        metric("metric_a", {"scheme": "neutral"}, aggFunc="sum"),
        metric("metric_b", aggFunc="sum"),
    ]


st.subheader("0 flat, interactive")
AgGrid(
    df,
    grid_options={
        **COMMON_OPTIONS,
        "context": INTERACTIVE,
        "columnDefs": [
            *flat_columns(),
            metric("metric_c", {"scheme": "fill", "color": FILL_COLOR}),
            metric("ratio", col_id="ratio_own", cellStyle=OWN_STYLE),
            metric("ratio", False, col_id="ratio_off"),
        ],
    },
    height=300,
    allow_unsafe_jscode=True,
    enable_enterprise_modules=True,
    key="picker_flat",
)

st.subheader("1 pivot, interactive, Columns panel")
AgGrid(
    df,
    grid_options={
        **COMMON_OPTIONS,
        "context": INTERACTIVE,
        "pivotMode": True,
        "sideBar": {"toolPanels": ["columns"], "defaultToolPanel": "columns"},
        "columnDefs": pivot_columns(),
    },
    height=420,
    enable_enterprise_modules=True,
    key="picker_pivot",
)

st.subheader("2 flat, not interactive")
AgGrid(
    df,
    grid_options={**COMMON_OPTIONS, "columnDefs": flat_columns()},
    height=300,
    enable_enterprise_modules=True,
    key="picker_off",
)

st.subheader("3 interactive, caller getMainMenuItems")
AgGrid(
    df,
    grid_options={
        **COMMON_OPTIONS,
        "context": INTERACTIVE,
        "getMainMenuItems": CALLER_MENU,
        "columnDefs": flat_columns(),
    },
    height=300,
    allow_unsafe_jscode=True,
    enable_enterprise_modules=True,
    key="picker_caller",
)

st.subheader("4 interactive, state round trip")
if "picker_saved" not in st.session_state:
    st.session_state.picker_saved = {"metric_b": {"scheme": "diverging"}}
    st.session_state.picker_mount = 0


def _remount():
    st.session_state.picker_mount += 1


st.button("remount", on_click=_remount)
flip = st.checkbox("flip option")
state_result = AgGrid(
    df,
    grid_options={
        **COMMON_OPTIONS,
        "context": INTERACTIVE,
        # Unrelated to colour: only here to send a rerun down the
        # `updateGridOptions` path.
        "suppressMovableColumns": bool(flip),
        "columnDefs": flat_columns(),
    },
    height=300,
    color_scale_state=st.session_state.picker_saved,
    collect=["stGetColorScaleState"],
    update_on=["stColorScaleChanged"],
    enable_enterprise_modules=True,
    key=f"picker_state_{st.session_state.picker_mount}",
)
if state_result.color_scale_state is not None:
    st.session_state.picker_saved = state_result.color_scale_state
st.text("state=" + json.dumps(state_result.color_scale_state, sort_keys=True))

st.subheader("5 pivot, mounted with a saved choice")
AgGrid(
    df,
    grid_options={
        **COMMON_OPTIONS,
        "context": INTERACTIVE,
        "pivotMode": True,
        "columnDefs": pivot_columns(),
    },
    height=300,
    color_scale_state={"metric_a": {"scheme": "diverging"}, "metric_b": {"scheme": "positive"}},
    enable_enterprise_modules=True,
    key="picker_pivot_saved",
)
