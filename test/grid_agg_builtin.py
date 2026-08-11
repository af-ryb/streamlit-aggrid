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


#: Task 4: `stRatio` is registered on every grid regardless of whether any
#: column declares it (see `parseGridOptions`), so AG-Grid's columns tool
#: panel aggregation picker offers it on any value column. This grid has no
#: `RATIO_COLUMNS` at all — it exists purely to prove that a column which
#: ends up with `aggFunc: "stRatio"` and no `context["stRatio"]` degrades to
#: a plain sum instead of blanking.
#:
#: Both `cost` and `installs` declare `aggFunc: "sum"` here, in `columnDefs`
#: — deliberately, not `"stRatio"`. `validate_ratio_columns` (`ratio.py`)
#: rejects *any* colDef declaring `aggFunc: "stRatio"` with no
#: `context["stRatio"]` (pinned by
#: `test/unit/test_ratio_validation.py::test_agg_func_without_a_context_is_rejected`)
#: — deliberately, per its own docstring: "every rule here exists to turn a
#: silent wrong number into a loud error." That guard runs unconditionally on
#: `columnDefs`, so it is not possible to get such a colDef past `AgGrid()`
#: at all: every column that ever reaches `stRatioAggFunc` with
#: `aggFunc === "stRatio"` in the *original* `columnDefs` is therefore
#: guaranteed to carry a structurally valid declaration too, which means
#: `readStRatioConfig` can only return `null` for a column whose `aggFunc`
#: became `"stRatio"` **after** Python validated it — i.e. only through
#: runtime acquisition. That is also exactly the real bug this task fixes:
#: the tool-panel aggregation picker is itself a runtime mutation Python
#: never sees.
#:
#: `cost` and `installs` each exercise a different, genuine runtime-mutation
#: mechanism — both real, both already-documented `AgGrid()` features, both
#: entirely outside `columnDefs` so `validate_ratio_columns` never inspects
#: either and `registerStRatio`'s `columnDefs` walk never attaches a
#: comparator to either:
#:
#: - `installs` is switched to `stRatio` via the raw `initial_state` prop
#:   (`GridState.aggregation.aggregationModel`), applied pre-paint, before
#:   the grid is created.
#: - `cost` is switched to `stRatio` via `columns_state` in `"merge"` mode
#:   (a `ColumnState[]` overlay, `aggFunc?: string | IAggFunc | null`),
#:   applied post-creation in `onGridReady`.
#:
#: Both shapes were confirmed against the installed `ag-grid-community@36.0.0`
#: type declarations (`gridState.d.ts`, `columnStateUtils.d.ts`) rather than
#: assumed.
def fallback_grid_options() -> dict:
    return {
        **COMMON_OPTIONS,
        "groupDisplayType": "multipleColumns",
        "columnDefs": [
            {"colId": ROW_DIM, "field": ROW_DIM, "rowGroup": True, "rowGroupIndex": 0},
            {"colId": PIVOT_DIM, "field": PIVOT_DIM, "rowGroup": True, "rowGroupIndex": 1},
            {
                "colId": "cost",
                "field": "cost",
                "headerName": "Cost",
                "type": "numericColumn",
                "aggFunc": "sum",
                "width": 130,
            },
            {
                "colId": "installs",
                "field": "installs",
                "headerName": "Installs",
                "type": "numericColumn",
                "aggFunc": "sum",
                "width": 130,
            },
        ],
    }


#: `GridState.aggregation.aggregationModel: AggregationColumnState[]`, each
#: `{colId, aggFunc}` — switches `installs` to `stRatio` pre-paint.
#:
#: `partialColumnState: True` is required, not decorative: this
#: `initial_state` carries only `aggregation`, and `GridState`'s own
#: docstring says a partial column-state snapshot needs the flag "when
#: providing a partial initialState with some but not all column state
#: properties." Measured, not assumed: without it, AG-Grid treats the
#: partial snapshot as the *complete* column state and drops the
#: `columnDefs`-driven `rowGroup` — the row-group grid rendered as eight flat
#: leaf rows plus one total, no grouping at all, until this was added.
FALLBACK_INITIAL_STATE = {
    "partialColumnState": True,
    "aggregation": {"aggregationModel": [{"colId": "installs", "aggFunc": "stRatio"}]},
}

#: `ColumnState[]` merge overlay — switches `cost` to `stRatio` post-creation,
#: without disturbing `installs` or the row groups `columnDefs` already set
#: up (merge mode only touches the columns named in the delta).
FALLBACK_COLUMNS_STATE = [{"colId": "cost", "aggFunc": "stRatio"}]


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

st.subheader("Fallback — stRatio with no declaration degrades to sum")
AgGrid(
    df,
    grid_options=fallback_grid_options(),
    initial_state=FALLBACK_INITIAL_STATE,
    columns_state=FALLBACK_COLUMNS_STATE,
    columns_state_mode="merge",
    enable_enterprise_modules=True,
    height=420,
    key="agg_builtin_fallback",
)
