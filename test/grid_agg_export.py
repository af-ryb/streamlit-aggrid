"""Streamlit app: what lands in a CSV export, for both `useValueFormatterForExport`
settings, across all three built-in aggregators.

`AgGridComponent.tsx`'s toolbar button calls `exportDataAsCsv()` with no
parameters, and this fork installs no `defaultCsvExportParams` and no
`processCellForClipboard` — so whatever AG-Grid 36 does with the column-level
`useValueFormatterForExport` setting (default `true`) is exactly what a
consumer gets. A group cell's value is an `IAggFuncResult` object (`toNumber`,
`toString`); a leaf cell is a plain number straight off the DataFrame. This app
measures the CSV text for both, rather than assuming it.

Two grids, otherwise identical, row-grouped by `campaign` only (single level —
this probe's job is to export, not to demonstrate the aggregators, so it
carries none of `grid_agg_builtin.py`'s pivot/fallback/nesting scenarios):

- grid 0 (`export_formatted`): every ratio-family column sets
  `useValueFormatterForExport: True` (the default, set explicitly so the
  colDef reads the same shape as grid 1) *and* carries a `valueFormatter`
  (four decimals, empty string for null — the same convention
  `ratio_fixture.as_text` uses elsewhere in this plan) so the two settings
  produce visibly different CSV text. Without a formatter the two grids could
  easily export identically, proving nothing.
- grid 1 (`export_raw`): the same columns, `useValueFormatterForExport: False`,
  no `valueFormatter`.

Six columns, one pair per aggregator — a column that is a real number for
both campaigns, and a `fill_null` column that blanks for campaign B (zero
`payers` throughout, the same fact `arpp_blank`/`wavg_blank` already exploit
elsewhere in this plan):

- `cpi` / `arpp_blank` — `stRatio` (`RATIO_SPECS_BY_ID`, already in the
  fixture).
- `growth` / `growth_blank` — `stRatioOfRatios`. `growth` is `GROWTH_SPECS_BY_ID`
  (already in the fixture; never blanks on this fixture — see its docstring).
  `growth_blank` is declared locally, the same shape `grid_agg_builtin.py` and
  `test_grid_agg_builtin.py` each declare independently for the same reason:
  apps in this repo run via `streamlit run`, never as an imported module, so a
  locally-needed spec that is not part of the shared fixture is redeclared
  rather than imported.
- `wavg` / `wavg_blank` — `stWeightedAvg` (`WEIGHTED_SPECS_BY_ID`, both already
  in the fixture).

Grid 0 carries a seventh column, `cpi_no_formatter` (`_no_formatter_column_def`):
`useValueFormatterForExport: True` but no `valueFormatter` configured — proves
that setting is a no-op with nothing to format, i.e. that it behaves exactly
like grid 1's `False`, rather than leaving that as an inference from reading
AG-Grid's `formatValue` source (see `test_true_without_a_value_formatter_behaves_like_false`).

Each grid's `getDataAsCsv()` is collected via `collect=["getDataAsCsv"]`
(`useAutoCollect.ts:99-113` calls any zero-argument grid-API method and
returns its value into `AgGridResult` — no download interception needed) and
rendered with `st.text` inside a `st.container(key=...)`, the same
`.st-key-<key>` scoping every other e2e suite in this repo uses to find a
specific piece of rendered output (see `grid_mixed_modules.py`,
`grid_return.py`, etc.).

`update_on=["sortChanged"]`, not `["gridReady"]`: measured (not assumed) that
`gridReady` does not work as a zero-interaction auto-collect trigger here.
`useAutoCollect`'s listener-attaching effect depends on the `gridApi` state
set inside `AgGridComponent`'s own `onGridReady` callback, so by the time
that effect runs and calls `gridApi.addEventListener("gridReady", ...)`, the
grid's own internal `gridReady` event has already fired and will never fire
again — confirmed via `debug=True` console logs, where `[AgGridComponent]
Grid ready` always logs before `[useAutoCollect] Attached listener:
gridReady`. `firstDataRendered` was tried too and is equally unreliable here,
for the same reason (it also fires during/immediately after grid creation,
before the listener is attached) — with static `rowData` there is no
asynchronous data load to delay it past the attach point. So the test clicks
the (hidden) row-group column's header once, ascending, purely to fire a
genuine `sortChanged` after the grid has settled — ascending because it
reproduces the fixture's natural campaign order (A before B) so the CSV is
identical to what an unsorted grid would export, keeping the pinned strings
meaningful. See `test_grid_agg_export.py` for the click.

Run standalone with:  streamlit run test/grid_agg_export.py
"""

import streamlit as st

from st_aggrid import AgGrid, JsCode

from ratio_fixture import (
    GROWTH_SPECS_BY_ID,
    RATIO_ROWS,
    RATIO_SPECS_BY_ID,
    RatioOfRatiosSpec,
    WEIGHTED_SPECS_BY_ID,
    evaluate_ratio_of_ratios,
    ratio_dataframe,
)

CPI_SPEC = RATIO_SPECS_BY_ID["cpi"]
ARPP_BLANK_SPEC = RATIO_SPECS_BY_ID["arpp_blank"]
GROWTH_SPEC = GROWTH_SPECS_BY_ID["growth"]
WAVG_SPEC = WEIGHTED_SPECS_BY_ID["wavg"]
WAVG_BLANK_SPEC = WEIGHTED_SPECS_BY_ID["wavg_blank"]

#: `growth` never blanks on this fixture (every leg it uses is nonzero on
#: every row — see `GROWTH_SPECS`'s docstring in `ratio_fixture.py`), so this
#: probe needs its own blanking column the same way `grid_agg_builtin.py`'s
#: `GROWTH_BLANK_SPEC` does: `to` leg reads `revenue`/`payers`, and every
#: campaign-B row has `payers == 0`.
GROWTH_BLANK_SPEC = RatioOfRatiosSpec(
    col_id="growth_blank",
    header="Growth (blank)",
    from_leg={"num": ("ads_d0",), "den": ("inst_d0",)},
    to_leg={"num": ("revenue",), "den": ("payers",)},
)

#: Unwraps an aggregated group cell's `IAggFuncResult` via `toNumber()` before
#: formatting; a leaf cell's `params.value` is already a plain number (or
#: `null`), so it passes through unchanged. Four decimals / empty-for-null is
#: the same convention `ratio_fixture.as_text` uses, and is also what the
#: retired JavaScript aggregator's own `toString` did (`value.toFixed(4)`) —
#: the exact behaviour this task measures the built-in aggregators against.
FORMATTER = JsCode(
    """
    function(params) {
        var v = params.value;
        var n = (v && typeof v.toNumber === 'function') ? v.toNumber() : v;
        return (n === null || n === undefined) ? '' : n.toFixed(4);
    }
    """
)


def _column_def(col_id: str, header: str, agg_func: str, context_key: str, spec, *, formatted: bool) -> dict:
    col = {
        "colId": col_id,
        "field": col_id,
        "headerName": header,
        "type": "numericColumn",
        "aggFunc": agg_func,
        "context": {context_key: spec.to_context()},
        "useValueFormatterForExport": formatted,
        "width": 130,
    }
    if formatted:
        col["valueFormatter"] = FORMATTER
    return col


def _no_formatter_column_def() -> dict:
    """`useValueFormatterForExport: True` (the default) but no
    `valueFormatter` — grid-0-only, appended after the six shared columns.
    Confirms the README's claim that "True with no formatter" behaves like
    "False" empirically, not only by reading AG-Grid's `formatValue` source:
    with nothing configured to format, `valueFormatted` stays `null` and
    `putInQuotes` falls back to the raw value's own `toString()`, same as the
    `false` grid's own `cpi` column. Reuses `CPI_SPEC` so the two are
    directly comparable cell-for-cell."""
    return {
        "colId": "cpi_no_formatter",
        "field": "cpi",
        "headerName": "CPI (true, no formatter)",
        "type": "numericColumn",
        "aggFunc": "stRatio",
        "context": {"stRatio": CPI_SPEC.to_context()},
        "useValueFormatterForExport": True,
        "width": 130,
    }


def column_defs(*, formatted: bool) -> list[dict]:
    return [
        {
            "colId": "campaign",
            "field": "campaign",
            "rowGroup": True,
            "rowGroupIndex": 0,
            "hide": True,
        },
        _column_def("cpi", "CPI", "stRatio", "stRatio", CPI_SPEC, formatted=formatted),
        _column_def(
            "arpp_blank", "ARPP (blank)", "stRatio", "stRatio", ARPP_BLANK_SPEC, formatted=formatted
        ),
        _column_def(
            "growth", "Growth", "stRatioOfRatios", "stRatioOfRatios", GROWTH_SPEC, formatted=formatted
        ),
        _column_def(
            "growth_blank",
            "Growth (blank)",
            "stRatioOfRatios",
            "stRatioOfRatios",
            GROWTH_BLANK_SPEC,
            formatted=formatted,
        ),
        _column_def(
            "wavg", "Weighted avg", "stWeightedAvg", "stWeightedAvg", WAVG_SPEC, formatted=formatted
        ),
        _column_def(
            "wavg_blank",
            "Weighted avg (blank)",
            "stWeightedAvg",
            "stWeightedAvg",
            WAVG_BLANK_SPEC,
            formatted=formatted,
        ),
    ] + ([_no_formatter_column_def()] if formatted else [])


def grid_options(*, formatted: bool) -> dict:
    return {
        "groupDefaultExpanded": -1,
        "grandTotalRow": "bottom",
        "columnDefs": column_defs(formatted=formatted),
    }


st.set_page_config(layout="wide")

df = ratio_dataframe()
# `ratio_dataframe()` only precomputes columns for the specs it knows about;
# `growth_blank` lives here, not in `ratio_fixture.py`, so its per-row values
# are precomputed the same way, locally — mirrors `grid_agg_builtin.py`.
df[GROWTH_BLANK_SPEC.col_id] = [
    evaluate_ratio_of_ratios([row], GROWTH_BLANK_SPEC) for row in RATIO_ROWS
]

st.subheader("useValueFormatterForExport=True (+ valueFormatter)")
result_formatted = AgGrid(
    df,
    grid_options=grid_options(formatted=True),
    allow_unsafe_jscode=True,
    enable_enterprise_modules=True,
    collect=["getDataAsCsv"],
    update_on=["sortChanged"],
    height=360,
    key="export_formatted",
)
with st.container(key="export_formatted_csv"):
    st.text(result_formatted.get("dataAsCsv") or "")

st.subheader("useValueFormatterForExport=False (raw)")
result_raw = AgGrid(
    df,
    grid_options=grid_options(formatted=False),
    enable_enterprise_modules=True,
    collect=["getDataAsCsv"],
    update_on=["sortChanged"],
    height=360,
    key="export_raw",
)
with st.container(key="export_raw_csv"):
    st.text(result_raw.get("dataAsCsv") or "")
