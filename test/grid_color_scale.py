"""Streamlit app: the built-in declarative colour scales.

Five grids over one fixture (`color_scale_fixture.py`, which also owns the
expected colours):

  0  flat — every scheme at its default mode, every non-default `scheme x mode`
     pairing, both `skip_non_positive` settings, a uniform column, and a column
     whose own `cellStyle` must win over the built-in. A floating text filter on
     `region` is what the re-scaling test drives.
  1  row-grouped by region with a grand total — the level-scoped population and
     the unpainted footer.
  2  row-grouped by country, pivoted on region — group rows painted per pivot
     result column.
  3  built through `GridOptionsBuilder` — `configure_color_scale` for the
     grid-level default and `configure_column(..., color_scale=True)` for a
     column that inherits it, rather than a fully-specified per-column dict.
     This is the consumer's actual migration shape and, before this grid, had
     no coverage in either language.
  4  a grid-wide `defaultColDef.cellStyle`, with a column that carries an
     otherwise-valid colour-scale declaration — the branch that can silently
     turn the feature off for an entire grid.

Grids 0-2 keep their indices so no existing assertion moves when 3 and 4 are
added.

Run standalone with:  streamlit run test/grid_color_scale.py
"""

import streamlit as st

from st_aggrid import AgGrid, GridOptionsBuilder, JsCode

from color_scale_fixture import LEAF_DIM, ROW_DIM, color_scale_dataframe

df = color_scale_dataframe()

#: Virtualisation off so `cell_backgrounds` sees every row rather than the
#: window, matching what the ratio apps do.
COMMON_OPTIONS = {
    "suppressColumnVirtualisation": True,
    "suppressRowVirtualisation": True,
    "animateRows": False,
}

#: A styler the built-in must not displace. Flat grey, nothing a scheme would
#: ever produce, so the assertion cannot pass by coincidence.
OWN_STYLE = JsCode("function(params) { return {backgroundColor: 'rgb(1, 2, 3)'}; }")


def metric_column(col_id, field, header, color_scale, **extra):
    return {
        "colId": col_id,
        "field": field,
        "headerName": header,
        "type": "numericColumn",
        "context": {"stColorScale": color_scale},
        "width": 130,
        **extra,
    }


st.subheader("Flat — every scheme, every mode, both skip settings")
AgGrid(
    df,
    grid_options={
        **COMMON_OPTIONS,
        "columnDefs": [
            {
                "colId": ROW_DIM,
                "field": ROW_DIM,
                "filter": "agTextColumnFilter",
                "floatingFilter": True,
            },
            {"colId": LEAF_DIM, "field": LEAF_DIM},
            metric_column("pos_minmax", "metric_a", "positive", {"scheme": "positive"}),
            metric_column("neu_zscore", "metric_a", "neutral", {"scheme": "neutral"}),
            metric_column("div_zscore", "metric_a", "diverging", {"scheme": "diverging"}),
            metric_column(
                "neu_minmax", "metric_a", "neutral/minmax",
                {"scheme": "neutral", "mode": "minmax"},
            ),
            metric_column(
                "pos_zscore", "metric_a", "positive/zscore",
                {"scheme": "positive", "mode": "zscore"},
            ),
            metric_column(
                "div_minmax", "metric_a", "diverging/minmax",
                {"scheme": "diverging", "mode": "minmax"},
            ),
            metric_column(
                "skip_on", "metric_b", "skip on",
                {"scheme": "positive", "skip_non_positive": True},
            ),
            metric_column(
                "skip_off", "metric_b", "skip off",
                {"scheme": "neutral", "skip_non_positive": False},
            ),
            metric_column("uniform", "metric_c", "uniform", {"scheme": "positive"}),
            metric_column(
                "own_style", "metric_a", "own cellStyle",
                {"scheme": "positive"}, cellStyle=OWN_STYLE,
            ),
        ],
    },
    allow_unsafe_jscode=True,
    enable_enterprise_modules=True,
    height=320,
    key="color_scale_flat",
)

st.subheader("Row grouping — level-scoped population, unpainted grand total")
AgGrid(
    df,
    grid_options={
        **COMMON_OPTIONS,
        "groupDefaultExpanded": -1,
        "grandTotalRow": "bottom",
        "columnDefs": [
            {"colId": ROW_DIM, "field": ROW_DIM, "rowGroup": True, "rowGroupIndex": 0},
            {"colId": LEAF_DIM, "field": LEAF_DIM},
            metric_column(
                "grouped", "metric_a", "positive", {"scheme": "positive"},
                aggFunc="sum",
            ),
        ],
    },
    enable_enterprise_modules=True,
    height=320,
    key="color_scale_grouped",
)

st.subheader("Pivot — group rows painted per pivot result column")
AgGrid(
    df,
    grid_options={
        **COMMON_OPTIONS,
        "pivotMode": True,
        "groupDefaultExpanded": -1,
        "pivotDefaultExpanded": -1,
        "suppressAggFuncInHeader": True,
        "columnDefs": [
            {"colId": LEAF_DIM, "field": LEAF_DIM, "rowGroup": True, "rowGroupIndex": 0},
            {"colId": ROW_DIM, "field": ROW_DIM, "pivot": True},
            metric_column(
                "pivoted", "metric_a", "positive", {"scheme": "positive"},
                aggFunc="sum",
            ),
        ],
    },
    enable_enterprise_modules=True,
    height=320,
    key="color_scale_pivot",
)

st.subheader("GridOptionsBuilder — grid-level default inherited via color_scale=True")
# The consumer's actual migration shape: `configure_color_scale` once per grid,
# then a bare `color_scale=True` per metric column, rather than a
# fully-specified per-column dict. `metric_a` here is the same field as the
# flat grid's `pos_minmax` column, over the same fixture, so the two must
# paint identically.
gb = GridOptionsBuilder.from_dataframe(df)
gb.configure_grid_options(**COMMON_OPTIONS)
gb.configure_color_scale(scheme="positive")
gb.configure_column("metric_a", color_scale=True)
AgGrid(
    df,
    grid_options=gb.build(),
    enable_enterprise_modules=True,
    height=320,
    key="color_scale_builder",
)

st.subheader("A grid-wide defaultColDef.cellStyle disables the colour scale")
# The branch that can silently turn the feature off for every column in a
# grid: `metric_a` below carries an otherwise-valid `stColorScale`
# declaration, but `defaultColDef.cellStyle` outranks it and the built-in is
# never attached.
BLOCKING_CELL_STYLE = JsCode("function(params) { return {fontWeight: 'bold'}; }")
AgGrid(
    df,
    grid_options={
        **COMMON_OPTIONS,
        "defaultColDef": {"cellStyle": BLOCKING_CELL_STYLE},
        "columnDefs": [
            {"colId": ROW_DIM, "field": ROW_DIM},
            {"colId": LEAF_DIM, "field": LEAF_DIM},
            metric_column("blocked", "metric_a", "positive", {"scheme": "positive"}),
        ],
    },
    allow_unsafe_jscode=True,
    enable_enterprise_modules=True,
    height=320,
    key="color_scale_default_cellstyle",
)
