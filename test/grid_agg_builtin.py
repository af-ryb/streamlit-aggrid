"""Streamlit app: the growing set of built-in declarative aggregators.

The new home for every aggregator this coverage plan adds — `stRatio`'s base
semantics already have their regression baseline in `grid_ratio_builtin.py`,
which stays frozen, so a new aggregator (or a new capability on an existing
one) gets its column here instead of disturbing that baseline. Task 3 adds
`stRatio`'s `share` column, whose denominator is a window-wide constant
(`den_const`) rather than a summed field, plus a row-group-only `mixed_den`
column proving `den_const` combines with a real summed `den` field rather
than replacing it. Tasks 4-6 append more grids and more columns on top of the
same two scenarios.

Grid 0 row-groups by campaign then country, carrying the raw component
columns (`aggFunc: "sum"`) alongside every declared aggregation column. Grid 1
is the same fixture pivoted on country with campaign down the rows. Same
fixture, same dimensions as `grid_ratio_builtin.py` — only the column set
differs.

Run standalone with:  streamlit run test/grid_agg_builtin.py
"""

import streamlit as st

from st_aggrid import AgGrid

from ratio_fixture import (
    COMPONENT_FIELDS,
    PIVOT_DIM,
    RATIO_ROWS,
    RatioSpec,
    ROW_DIM,
    SHARE_SPEC,
    evaluate,
    ratio_dataframe,
)


def _agg_column_def(col_id: str, header: str, agg_func: str, context: dict) -> dict:
    """The colDef shape every aggregated column in this app takes. A new
    aggregator is a new spec-to-colDef wrapper around this shared shape, not a
    new dict literal — `ratio_column_def` below is the first; Tasks 4-6 add a
    `ratio_of_ratios_column_def` and a `weighted_avg_column_def` alongside
    it."""
    return {
        "colId": col_id,
        "field": col_id,
        "headerName": header,
        "type": "numericColumn",
        "aggFunc": agg_func,
        "context": context,
        "width": 130,
    }


def ratio_column_def(spec: RatioSpec) -> dict:
    """One `stRatio` colDef from a `RatioSpec`."""
    return _agg_column_def(
        spec.col_id, spec.header, "stRatio", {"stRatio": spec.to_context()}
    )


def component_column_defs() -> list[dict]:
    return [
        {
            "colId": name,
            "field": name,
            "aggFunc": "sum",
            "width": 110,
            "type": "numericColumn",
        }
        for name in COMPONENT_FIELDS
    ]


#: Ratio-family columns declared on both grids, in a fixed order. Task 3 adds
#: only `share`; later tasks extend this tuple rather than hand-writing a new
#: columnDefs list.
RATIO_COLUMNS: tuple[RatioSpec, ...] = (SHARE_SPEC,)

#: Exercises `den_const` combined with a non-empty `den` at runtime: `share`'s
#: `den` is always empty, so nothing else proves both terms land in the same
#: denominator (`denominator = den_const + Σden`) rather than one silently
#: replacing the other. Row-group-grid-only, mirroring how
#: `grid_ratio_builtin.py`'s `overlap_column_def` is scoped to its grid 0 —
#: this column exists purely to guard that arithmetic, not to model a
#: real-world metric. Declared here rather than in `ratio_fixture.py`: that
#: module's blind-spot frozensets (`DEGENERATE_NODES`, `PIVOT_BLIND_CELLS`)
#: are measured against its own specs, so a new entry there would ripple.
MIXED_DEN_SPEC = RatioSpec(
    col_id="mixed_den",
    header="Cost / (rebate + const)",
    num=("cost",),
    den=("rebate",),
    den_const=200.0,
)


COMMON_OPTIONS = {
    "suppressColumnVirtualisation": True,
    "suppressRowVirtualisation": True,
    "groupDefaultExpanded": -1,
    "grandTotalRow": "bottom",
}


def rowgroup_grid_options() -> dict:
    return {
        **COMMON_OPTIONS,
        "groupDisplayType": "multipleColumns",
        "columnDefs": [
            {"colId": ROW_DIM, "field": ROW_DIM, "rowGroup": True, "rowGroupIndex": 0},
            {"colId": PIVOT_DIM, "field": PIVOT_DIM, "rowGroup": True, "rowGroupIndex": 1},
            *(ratio_column_def(spec) for spec in RATIO_COLUMNS),
            ratio_column_def(MIXED_DEN_SPEC),
            *component_column_defs(),
        ],
    }


def pivot_grid_options() -> dict:
    return {
        **COMMON_OPTIONS,
        "pivotMode": True,
        "groupDisplayType": "multipleColumns",
        "pivotRowTotals": "after",
        "columnDefs": [
            {"colId": ROW_DIM, "field": ROW_DIM, "rowGroup": True, "rowGroupIndex": 0},
            {"colId": PIVOT_DIM, "field": PIVOT_DIM, "pivot": True, "pivotIndex": 0},
            *(ratio_column_def(spec) for spec in RATIO_COLUMNS),
            *component_column_defs(),
        ],
    }


st.set_page_config(layout="wide")

df = ratio_dataframe()
# `ratio_dataframe()` only precomputes columns for the specs it knows about
# (`RATIO_SPECS`, `SHARE_SPEC`, ...); `MIXED_DEN_SPEC` lives here, not in
# `ratio_fixture.py`, so its per-row value is precomputed the same way, just
# locally.
df[MIXED_DEN_SPEC.col_id] = [evaluate(MIXED_DEN_SPEC, [row]) for row in RATIO_ROWS]

st.subheader("Row grouping — share of a window-wide constant")
AgGrid(
    df,
    grid_options=rowgroup_grid_options(),
    enable_enterprise_modules=True,
    height=420,
    key="agg_builtin_rowgroup",
)

st.subheader("Pivot — campaign down, country across")
AgGrid(
    df,
    grid_options=pivot_grid_options(),
    enable_enterprise_modules=True,
    height=320,
    key="agg_builtin_pivot",
)
