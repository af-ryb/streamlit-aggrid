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

from st_aggrid import AgGrid, JsCode

from ratio_fixture import (
    COMPONENT_FIELDS,
    GROWTH_SPECS,
    PIVOT_DIM,
    RATIO_ROWS,
    RatioOfRatiosSpec,
    RatioSpec,
    ROW_DIM,
    SHARE_SPEC,
    WEIGHTED_SPECS,
    WeightedAvgSpec,
    evaluate,
    evaluate_ratio_of_ratios,
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


def ratio_of_ratios_column_def(spec: RatioOfRatiosSpec) -> dict:
    """One `stRatioOfRatios` colDef from a `RatioOfRatiosSpec`."""
    return _agg_column_def(
        spec.col_id, spec.header, "stRatioOfRatios", {"stRatioOfRatios": spec.to_context()}
    )


def weighted_avg_column_def(spec: WeightedAvgSpec) -> dict:
    """One `stWeightedAvg` colDef from a `WeightedAvgSpec`."""
    return _agg_column_def(
        spec.col_id, spec.header, "stWeightedAvg", {"stWeightedAvg": spec.to_context()}
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

#: `stRatioOfRatios` columns declared on both grids: `growth` (the direction-
#: discriminating column, see `test_growth_pivot_cell_direction_diverges_from_its_row_total`
#: in the test suite) and `growth_neg` (pins the `> 0` -> `!== 0` behaviour
#: change — see `GROWTH_SPECS`'s docstring in `ratio_fixture.py`).
GROWTH_COLUMNS: tuple[RatioOfRatiosSpec, ...] = GROWTH_SPECS

#: `stWeightedAvg` columns declared on the row-group grid, the pivot grid,
#: and the grouped-columns grid (Task 6): `wavg` (the skip-rule column —
#: NaN-value and negative-weight leaves, and the not-the-average-of-children
#: anchor at campaign A) plus `wavg_blank`/`wavg_zero`, the `fill_null`-both-
#: ways pair sharing `payers` as their weight — see `WEIGHTED_SPECS`'s
#: docstring in `ratio_fixture.py`.
WEIGHTED_COLUMNS: tuple[WeightedAvgSpec, ...] = WEIGHTED_SPECS

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

#: A `stRatioOfRatios` column whose `to` leg collapses for campaign B: every
#: B row has `payers == 0` (the same fact `arpp`/`arpp_blank` already exploit
#: for `stRatio`), so `growth_blank` is a real number for campaign A and
#: `None` throughout campaign B — a nulls-sort-last fixture `growth`/
#: `growth_neg` cannot provide on their own, since every leg they use
#: (`ads_d0`/`inst_d0`/`ads_d1`/`inst_d1`) is positive on every row of this
#: fixture. Declared here rather than in `ratio_fixture.py`, same reasoning as
#: `MIXED_DEN_SPEC`: that module's blind-spot frozensets are measured against
#: its own specs, so a column that exists purely to guard sort behaviour
#: would ripple there for no benefit.
GROWTH_BLANK_SPEC = RatioOfRatiosSpec(
    col_id="growth_blank",
    header="Growth (blank)",
    from_leg={"num": ("ads_d0",), "den": ("inst_d0",)},
    to_leg={"num": ("revenue",), "den": ("payers",)},
)

#: A deliberately backwards comparator, attached only to the row-group grid's
#: `growth` column (see `rowgroup_growth_column_defs`). Exists so a test can
#: prove a caller-supplied `comparator` is left alone; the fork's own
#: comparator would sort the other way. Copied from `grid_ratio_builtin.py`'s
#: `js_reversed_comparator` — same shape, same reasoning — rather than
#: imported, because `grid_ratio_builtin.py` is itself an executable
#: Streamlit app: importing it would run its top-level `AgGrid()` calls and
#: mount a second, unwanted copy of its grids, and it is frozen (see the plan's
#: Global Constraints), so it is not a place this module should reach into.
#: `test/` modules can and do import each other freely otherwise — this
#: module already imports plenty from `ratio_fixture.py` above — it is
#: specifically an *app* file that cannot be imported for its side effects.
js_reversed_comparator = JsCode("""
function(a, b) {
    const x = (a && typeof a.toNumber === 'function') ? a.toNumber() : a;
    const y = (b && typeof b.toNumber === 'function') ? b.toNumber() : b;
    if (x == null || y == null) { return 0; }
    return x > y ? -1 : (x < y ? 1 : 0);
}
""")


def rowgroup_growth_column_defs() -> list[dict]:
    """Growth-family colDefs for the row-group grid only: `growth` carries
    the reversed comparator (proving a caller-supplied one is left alone),
    and `growth_blank` (proving nulls sort last) rides along — neither
    belongs on the pivot grid or the grouped-columns grid, which test other
    things and would only pick up incidental coupling from these."""
    columns = []
    for spec in GROWTH_COLUMNS:
        column = ratio_of_ratios_column_def(spec)
        if spec.col_id == "growth":
            column["comparator"] = js_reversed_comparator
        columns.append(column)
    columns.append(ratio_of_ratios_column_def(GROWTH_BLANK_SPEC))
    return columns


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
            *rowgroup_growth_column_defs(),
            *(weighted_avg_column_def(spec) for spec in WEIGHTED_COLUMNS),
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
            *(ratio_of_ratios_column_def(spec) for spec in GROWTH_COLUMNS),
            *(weighted_avg_column_def(spec) for spec in WEIGHTED_COLUMNS),
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
#: `columnDefs`, so such a colDef never reaches the browser this way through
#: a colDef that Python validated: every column that ever reaches
#: `stRatioAggFunc` with `aggFunc === "stRatio"` in the *original*
#: `columnDefs` is therefore guaranteed to carry a structurally valid
#: declaration too, which means
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
# (`RATIO_SPECS`, `SHARE_SPEC`, `GROWTH_SPECS`, ...); `MIXED_DEN_SPEC` and
# `GROWTH_BLANK_SPEC` live here, not in `ratio_fixture.py`, so their per-row
# values are precomputed the same way, just locally.
df[MIXED_DEN_SPEC.col_id] = [evaluate(MIXED_DEN_SPEC, [row]) for row in RATIO_ROWS]
df[GROWTH_BLANK_SPEC.col_id] = [
    evaluate_ratio_of_ratios([row], GROWTH_BLANK_SPEC) for row in RATIO_ROWS
]

st.subheader("Row grouping — share of a window-wide constant")
AgGrid(
    df,
    grid_options=rowgroup_grid_options(),
    allow_unsafe_jscode=True,
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

# `registerAggFunc` installs the null-ordering comparator by walking
# `columnDefs`, and the consumer this feature exists for wraps every metric
# column in a column group — mirrors `grid_ratio_builtin.py`'s own
# "grouped-cols" grid, but for `stRatioOfRatios`/`stWeightedAvg` rather than
# `stRatio`, so `eachColDef`'s descent into `children` is under test for both
# newer aggregators too, not just inspected by inference from the sibling
# suite. `growth_blank` rides along (nested here too, unlike on the pivot
# grid) because it is what lets a test prove the comparator that reached this
# nested column is specifically the nulls-last one — `growth`/`growth_neg`
# never produce a null in this fixture, so sorting by either would pass under
# AG-Grid's own default comparator too and prove nothing about the descent.
# `wavg_blank` plays the identical role for the `stWeightedAvg` group below:
# `wavg`/`wavg_zero` never blank on this fixture either.
st.subheader("Row grouping — stRatioOfRatios and stWeightedAvg columns nested in column groups")
AgGrid(
    df,
    grid_options={
        **COMMON_OPTIONS,
        "groupDisplayType": "multipleColumns",
        "columnDefs": [
            {"colId": ROW_DIM, "field": ROW_DIM, "rowGroup": True, "rowGroupIndex": 0},
            {
                "headerName": "Growth",
                # Not `groupId: "growth"`: that collides with the child
                # column's `colId: "growth"` — AG-Grid disambiguates by
                # silently renaming the column to `growth_1`, which is not
                # what any test here expects.
                "groupId": "growthMetrics",
                "children": [
                    *(ratio_of_ratios_column_def(spec) for spec in GROWTH_COLUMNS),
                    ratio_of_ratios_column_def(GROWTH_BLANK_SPEC),
                ],
            },
            {
                "headerName": "Weighted Avg",
                "groupId": "weightedAvgMetrics",
                "children": [
                    *(weighted_avg_column_def(spec) for spec in WEIGHTED_COLUMNS),
                ],
            },
            *component_column_defs(),
        ],
    },
    enable_enterprise_modules=True,
    height=260,
    key="agg_builtin_grouped_cols",
)
