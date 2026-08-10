"""Streamlit app: ratio aggregation via the consumer's JavaScript `ratioSum`.

This is the **baseline** for the declarative ratio aggregator described in
``docs/superpowers/specs/2026-08-10-declarative-ratio-aggregation-design.md``.
It runs the JavaScript that `hitapps_analytics` ships today, verbatim, over the
spec's reference fixture, so the built-in aggregator can be developed against a
live, running comparison rather than against remembered numbers.

Two grids render the same data:

- **row grouping** — campaign, then country, with a grand-total row;
- **pivot** — campaign down the rows, country across the columns, with pivot
  row totals and a grand-total row.

The pivot grid is the one that matters most. ``ratioSum`` sums
``rowNode.allLeafChildren``, which is *not* pivot-aware: it returns every leaf
under the row node regardless of which pivot key the cell belongs to. AG-Grid 36
exposes ``params.aggregatedChildren`` for exactly this reason — its documented
contract is "with pivot columns, only rows matching the pivot keys are
included". Whether the current JavaScript is right or wrong in a pivot cell is
therefore a question this app answers by rendering it.

The table under the grids prints the specified semantics computed in Python, so
a developer can read the grid and the reference side by side.

Run standalone with:  streamlit run test/grid_ratio_js.py
"""

import pandas as pd
import streamlit as st

from st_aggrid import AgGrid, JsCode

from ratio_fixture import (
    COMPONENT_FIELDS,
    PIVOT_DIM,
    RATIO_SPECS,
    ROW_DIM,
    evaluate,
    expected,
    expected_legacy,
    ratio_dataframe,
    rows_where,
)

# --------------------------------------------------------------------------
# The consumer's JavaScript, copied verbatim.
#
# Source: hitapps_analytics/web_app/web/dashboards/marketing/js_funcs.py
# (`js_ratio_sum`, `js_ratio_value_formatter`). Do not "improve" these — the
# whole point is that they behave here exactly as they behave in production.
# --------------------------------------------------------------------------

js_ratio_sum = JsCode("""
function RatioSum(params) {
    const ctx = (params.colDef && params.colDef.context) || {};
    const numField = ctx.num;
    const denField = ctx.den;
    const num2Field = ctx.num2;
    const multiplier = (ctx.multiplier != null) ? Number(ctx.multiplier) : 1;
    const scale = (ctx.scale != null) ? Number(ctx.scale) : 1;
    const rows = (params.rowNode && params.rowNode.allLeafChildren) || [];
    let num = 0;
    let den = 0;
    if (numField || denField) {
        for (const r of rows) {
            if (!r.data) { continue; }
            if (numField) {
                num += Number(r.data[numField]) || 0;
            }
            if (num2Field) {
                num += Number(r.data[num2Field]) || 0;
            }
            if (denField) {
                den += Number(r.data[denField]) || 0;
            }
        }
    }
    const value = den > 0 ? (num / den) * multiplier * scale : null;
    return {
        value: value,
        numerator: num,
        denominator: den,
        toString: function() {
            return (this.value != null && !isNaN(this.value))
                ? this.value.toFixed(4)
                : '';
        }
    };
}
""")

js_ratio_value_formatter = JsCode("""
function(params) {
    const v = params.value;
    if (v == null) { return ''; }
    if (typeof v === 'object') {
        return (v.value != null && !isNaN(v.value)) ? v.value.toFixed(4) : '';
    }
    return isNaN(v) ? '' : Number(v).toFixed(4);
}
""")


# --------------------------------------------------------------------------
# Column definitions
# --------------------------------------------------------------------------


def ratio_column_defs() -> list[dict]:
    """One colDef per ratio spec, wired the way the consumer wires them.

    ``emit_value_getter=False`` in the consumer's `configure_metric_column`:
    the leaf cell renders the precomputed scalar straight from the dataframe
    and only group rows run ``ratioSum``, which re-derives the ratio from the
    raw components named in ``colDef.context``.
    """
    return [
        {
            "colId": spec.col_id,
            "field": spec.col_id,
            "headerName": spec.header,
            "type": "numericColumn",
            "aggFunc": "ratioSum",
            "context": spec.to_legacy_context(),
            "valueFormatter": js_ratio_value_formatter,
            "width": 130,
        }
        for spec in RATIO_SPECS
    ]


def component_column_defs() -> list[dict]:
    """Raw components, summed. Present so the numerator and denominator behind
    every ratio can be read off the same row that shows the ratio."""
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


COMMON_OPTIONS = {
    "groupDefaultExpanded": -1,
    "suppressAggFuncInHeader": True,
    "grandTotalRow": "bottom",
    "autoGroupColumnDef": {
        "cellRendererParams": {"suppressCount": True},
        "minWidth": 140,
    },
    # Every cell in the DOM, so an assertion can read a column that happens to
    # sit off-screen — the pivot grid is far wider than any viewport.
    "suppressColumnVirtualisation": True,
    "suppressRowVirtualisation": True,
    "aggFuncs": {"ratioSum": js_ratio_sum},
}


def rowgroup_grid_options() -> dict:
    return {
        **COMMON_OPTIONS,
        "groupDisplayType": "multipleColumns",
        "columnDefs": [
            {"colId": ROW_DIM, "field": ROW_DIM, "rowGroup": True, "rowGroupIndex": 0},
            {
                "colId": PIVOT_DIM,
                "field": PIVOT_DIM,
                "rowGroup": True,
                "rowGroupIndex": 1,
            },
            *ratio_column_defs(),
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
            *ratio_column_defs(),
            *component_column_defs(),
        ],
    }


# --------------------------------------------------------------------------
# Page
# --------------------------------------------------------------------------

st.set_page_config(layout="wide")

df = ratio_dataframe()

st.subheader("Row grouping — campaign / country")
AgGrid(
    df,
    grid_options=rowgroup_grid_options(),
    allow_unsafe_jscode=True,
    enable_enterprise_modules=True,
    height=520,
    key="ratio_js_rowgroup",
)

st.subheader("Pivot — campaign down, country across")
AgGrid(
    df,
    grid_options=pivot_grid_options(),
    allow_unsafe_jscode=True,
    enable_enterprise_modules=True,
    height=320,
    key="ratio_js_pivot",
)

st.subheader("Reference — the semantics the declarative aggregator specifies")
st.caption(
    "Computed in Python by ratio_fixture.evaluate(). Where a cell differs from "
    "the grids above, the JavaScript baseline is the thing that is wrong; "
    "ratio_fixture.evaluate_legacy() says by how much and why."
)

reference_rows = []
for spec in RATIO_SPECS:
    row = {"metric": spec.col_id}
    for campaign in ("A", "B"):
        for country in ("US", "DE"):
            row[f"{campaign}/{country}"] = expected(
                spec.col_id, campaign=campaign, country=country
            )
    for campaign in ("A", "B"):
        row[f"{campaign} (total)"] = expected(spec.col_id, campaign=campaign)
    row["grand total"] = expected(spec.col_id)
    row["legacy grand total"] = expected_legacy(spec.col_id)
    row["legacy gap"] = spec.legacy_gap or ""
    reference_rows.append(row)

st.dataframe(pd.DataFrame(reference_rows), width="stretch")

st.caption(
    "Trap check — averaging the children instead of re-deriving the ratio "
    f"gives {sum(evaluate(RATIO_SPECS[0], [r]) for r in rows_where()) / 8:.4f} "
    "for CPI at the grand-total row (average of the eight leaf ratios) and "
    f"{expected('cpi'):.4f} correctly. The fixture separates the two at every "
    "level, so a wrong implementation cannot pass by coincidence."
)
