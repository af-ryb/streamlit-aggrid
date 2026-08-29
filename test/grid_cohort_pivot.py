"""Streamlit app: the consumer's cohort grid, rebuilt from its configuration.

Mirrors ``hitapps_analytics/web_app/web/dashboards/cohort/grid_builder.py`` —
the only grid in that service that puts a dimension in AG-Grid's *Column
Labels* by default. Reproduced here because a defect reported against that grid
(cells drawn on top of one another, and occasional wrong numbers) does not
appear on production, and the only delta reaching it is this fork's pin.

Everything the consumer's grid declares is carried over verbatim, because any
of it could be the part that matters: pivot mode with ``cohort_day`` pivoted,
two row-group dimensions displayed as ``multipleColumns``, a grand-total row
before the body, ``enableStrictPivotColumnOrder``, ``suppressAggFuncInHeader``,
a JS ``valuePerInstall`` aggregator folding flat numerator/denominator pairs,
a ``valueGetter`` that hands whole leaf rows to that aggregator, and — the
riskiest of them — an ``onStateUpdated`` hook that calls ``setColumnsVisible``
on *pivot result* columns from inside a state callback.

The controls reproduce the three distinct ways the consumer re-feeds the grid,
so each can be exercised on its own:

* ``max_day`` — rowData only. The pivot key set grows or shrinks while the
  columnDefs stay byte-identical, which is what an ordinary data refresh does
  and the path the report follows most closely.
* ``metrics`` — columnDefs change, rowData does not (the frame always carries
  every metric). Drives the component's ``updateGridOptions`` path.
* ``breakdown`` — the second row-group dimension appears/disappears. Drives
  ``setRowGroupColumns`` and the auto-group-column reorder.

``suppress_virtualisation`` is a manual-debugging aid, not part of the
consumer's config: with it off (the default) AG-Grid renders only the columns
in view, which is the state the defect was seen in. AG-Grid reads
``suppressColumnVirtualisation`` once when the grid is constructed, so ticking
the box on a running grid does nothing — flip the default and restart the app
to use it.
"""

import streamlit as st

from cohort_pivot_fixture import (
    INSTALL_DATES,
    MAX_DAY_LIMIT,
    METRICS,
    Shape,
    frame,
)
from st_aggrid import AgGrid, GridOptionsBuilder, JsCode

# --- JS carried over from the consumer's ``cohort/js_funcs.py`` -------------

js_value_getter = JsCode("""
     function(params) {
         // For leaf nodes
         if (params.data) {
             return params.data;
         }
         // For aggregated values, return the numeric value directly
         return params.value && typeof params.value === 'object' ? params.value.value : params.value;
     }
     """)

js_value_per_install = JsCode("""
function PivotAggFunc(params) {
    // Both leaf rows (whole row objects from js_value_getter) and group-level
    // aggregation results carry the same flat keys: `<metric>_numerator` /
    // `<metric>_denominator` — the SQL emits flat columns, no STRUCTs.
    const values = params.values;
    let totalNumerator = 0;
    let totalDenominator = 0;
    let groupCount = 0;
    const metricName = params.colDef.headerName;
    const numKey = metricName + '_numerator';
    const denKey = metricName + '_denominator';

    values.forEach(value => {
        if (typeof value === 'object' && value !== null) {
            totalNumerator += value[numKey] || 0;
            totalDenominator += value[denKey] || 0;
            groupCount += value.count || 1;
        }
    });

    const result = totalDenominator > 0 ? totalNumerator / totalDenominator : 0;

    const returnObj = {
        count: groupCount,
        value: result,
        toString: function() {
            return this.value > 0 ? this.value.toFixed(2) : '';
        }
    };
    returnObj[numKey] = totalNumerator;
    returnObj[denKey] = totalDenominator;

    return returnObj;
}
""")

js_value_comparator = JsCode("""
     function(valueA, valueB, nodeA, nodeB, isInverted) {
         const numA = typeof valueA === 'object' ? valueA.value : valueA;
         const numB = typeof valueB === 'object' ? valueB.value : valueB;
         const valA = numA === null || numA === undefined ? 0 : numA;
         const valB = numB === null || numB === undefined ? 0 : numB;
         return valA - valB;
     }
     """)

js_value_cell_render = JsCode("""
     function(params) {
         if (params.value === null || params.value === undefined) {
             return '';
         }
         if (typeof params.value === 'object' && params.value !== null) {
             return params.value.toString();
         }
         return params.value > 0 ? params.value.toFixed(2) : '';
     }
     """)

#: `_renderer_for` picks a renderer per metric from `MetricDefinition
#: .default_format`. Both are carried over, and both are used: the reported
#: overlap was spotted precisely because a `%` value and a `¢` value landed in
#: the same slot, which a single shared renderer would have disguised.
js_value_cell_render_percent = JsCode("""
     function(params) {
         if (params.value === null || params.value === undefined) {
             return '';
         }
         const n = (typeof params.value === 'object' && params.value !== null)
             ? params.value.value
             : params.value;
         if (n === null || n === undefined || isNaN(n)) {
             return '';
         }
         return n > 0 ? (Number(n) * 100).toFixed(2) + '%' : '';
     }
     """)

js_value_cell_render_currency = JsCode("""
     function(params) {
         if (params.value === null || params.value === undefined) {
             return '';
         }
         const n = (typeof params.value === 'object' && params.value !== null)
             ? params.value.value
             : params.value;
         if (n === null || n === undefined || isNaN(n) || n === 0) {
             return '';
         }
         const sign = n < 0 ? '-' : '';
         const abs = Math.abs(n);
         if (abs < 1) {
             return sign + (abs * 100).toFixed(2) + '¢';
         }
         const formatted = abs.toLocaleString('en-US', {
             minimumFractionDigits: 2,
             maximumFractionDigits: 2,
         });
         return sign + '$' + formatted;
     }
     """)

RENDERERS = {
    "retention": js_value_cell_render_percent,
    "arpu": js_value_cell_render_currency,
}

js_installs_styler = JsCode("""
function cellStyle(params) {
  let secondaryBackgroundColor = getComputedStyle(document.documentElement)
    .getPropertyValue('--secondary-background-color');
  return { backgroundColor: secondaryBackgroundColor };
}
""")

js_cohort_row_style = JsCode("""
function cohortStyle(params) {
  let secondaryBackgroundColor = getComputedStyle(document.documentElement)
    .getPropertyValue('--secondary-background-color');
    if (params.node.group) {
        if (params.node.key === 'cohort_1') {
            return { background: secondaryBackgroundColor};
        }
    }
    return null;
}
""")

js_hide_columns = JsCode("""
function hide_columns(gridOptions) {
  // Metrics to hide for non-zero cohort days
  const metricsToHide = ['installs', '%_installs', 'total_installs', 'spend', 'cpi'];

  // Get the actual pivot columns (not the result columns)
  const pivotColumns = gridOptions.api.getPivotColumns();
  if (pivotColumns.length === 0) {
    return;
  }

  const hasCohortDay = pivotColumns.some(col =>
    col.colDef.field === 'cohort_day' ||
    col.colDef.field === 'cohort-day'
  );
  if (!hasCohortDay) {
    return;
  }

  const pivotResultColumns = gridOptions.api.getPivotResultColumns();
  const allColumnIds = pivotResultColumns.map(col => col.colDef.colId);

  const columnsToHide = allColumnIds.filter(colId => {
    const containsMetricToHide = metricsToHide.some(metric =>
      colId.endsWith(metric) ||
      colId.includes('_' + metric) ||
      colId.includes('-' + metric)
    );
    if (!containsMetricToHide) {
      return false;
    }
    const isDayZeroColumn =
      colId.includes('-00_') || colId.includes('_00_') || colId.includes('-00-') || colId.includes('_00-') ||
      colId.includes('-000_') || colId.includes('_000_') || colId.includes('-000-') || colId.includes('_000-');
    const isAggregateColumn = !/-\\d+_|_\\d+_|-\\d+-|_\\d+-/.test(colId);
    return containsMetricToHide && !isDayZeroColumn && !isAggregateColumn;
  });

  if (columnsToHide.length > 0) {
    gridOptions.api.setColumnsVisible(columnsToHide, false);
  }
}
""")


# --- Controls ---------------------------------------------------------------

DATE_LIMIT = len(INSTALL_DATES)
MAX_DAY_CHOICES = (2, 4, 6, MAX_DAY_LIMIT)
DATE_RANGE_CHOICES = (2, 4, 6, DATE_LIMIT)

max_day = st.radio(
    "max_day",
    MAX_DAY_CHOICES,
    index=len(MAX_DAY_CHOICES) - 1,
    horizontal=True,
    key="max_day",
)
# Widening the range reaches back to older, more mature cohorts, so it grows
# the pivot key set as well as the row count — one control, both kinds of
# reshape, exactly as "расширили диапазон дат" does in the service.
n_dates = st.radio(
    "n_dates",
    DATE_RANGE_CHOICES,
    index=len(DATE_RANGE_CHOICES) - 1,
    horizontal=True,
    key="n_dates",
)
metrics = tuple(
    m for m in METRICS if st.checkbox(f"metric_{m}", value=True, key=f"metric_{m}")
)
breakdown = st.checkbox("breakdown", value=True, key="breakdown")
hide_hook = st.checkbox("hide_hook", value=True, key="hide_hook")
# Bisection knob, defaulting to the consumer's value. `enableStrictPivotColumnOrder`
# is the one option in this config that exists to constrain pivot *column order*,
# so it is the first thing to rule in or out of a column-layout defect.
strict_pivot_order = st.checkbox(
    "strict_pivot_order", value=True, key="strict_pivot_order"
)
suppress_virtualisation = st.checkbox(
    "suppress_virtualisation", value=False, key="suppress_virtualisation"
)

# The consumer never calls AgGrid directly: `render_managed_grid` seeds
# `columns_state` from a saved snapshot (replace mode), collects
# `getColumnState` on every event, and stores the capture back. `save_view`
# promotes the latest capture to the restore slot, so the next data-shape
# change re-applies a column state that was captured against the *previous*
# shape — the exact sequence the "stale pivot result columns" hypothesis needs.
if st.button("save_view", key="save_view"):
    st.session_state["saved_view"] = st.session_state.get("captured_state")
if st.button("clear_view", key="clear_view"):
    st.session_state.pop("saved_view", None)
restore_state = st.session_state.get("saved_view")
st.write(f"restore_state: {'none' if restore_state is None else len(restore_state)}")

shape = Shape(n_dates=n_dates, max_day=max_day, metrics=metrics)
df = frame(shape)


# --- Grid configuration (transcribed from the consumer's create_grid_config) -

gb = GridOptionsBuilder()
gb.configure_side_bar(default_tool_panel="", filters_panel=True)

gb.configure_column(
    "install_date",
    header_name="Install Date",
    enableRowGroup=True,
    initialRowGroupIndex=0,
    enablePivot=True,
    filter=True,
    initialSort="asc",
    initialRowGroup=True,
    wrapHeaderText=True,
    autoHeaderHeight=True,
    minWidth=200,
    maxWidth=450,
    width=200,
)

if breakdown:
    gb.configure_column(
        "country",
        header_name="Country",
        enableRowGroup=True,
        initialRowGroupIndex=1,
        enablePivot=True,
        filter=True,
        initialSort="desc",
        wrapHeaderText=True,
        autoHeaderHeight=True,
        minWidth=220,
        maxWidth=450,
        width=220,
    )

gb.configure_column(
    "cohort_day",
    header_name="Cohort Day",
    enableRowGroup=True,
    filter=True,
    initialSort="asc",
    enablePivot=True,
    initialPivotIndex=0,
)

gb.configure_column(
    "installs",
    headerName="installs",
    headerTooltip="Installs",
    minWidth=85,
    maxWidth=130,
    enableValue=True,
    type="numericColumn",
    wrapHeaderText=True,
    autoHeaderHeight=True,
    aggFunc="sum",
    allowedAggFuncs=["sum"],
    cellStyle=js_installs_styler,
)

for metric_name in metrics:
    gb.configure_column(
        metric_name,
        headerName=metric_name,
        headerTooltip=metric_name,
        type="numericColumn",
        enableValue=True,
        filter=False,
        minWidth=85,
        maxWidth=130,
        valueGetter=js_value_getter,
        aggFunc="valuePerInstall",
        cellRenderer=RENDERERS.get(metric_name, js_value_cell_render),
        comparator=js_value_comparator,
    )

options = {
    "pivotMode": True,
    "pivotDefaultExpanded": -1,
    "groupDefaultExpanded": -1,
    "groupDisplayType": "multipleColumns",
    "grandTotalRow": "before",
    "suppressAggFuncInHeader": True,
    "enableStrictPivotColumnOrder": strict_pivot_order,
    "getRowStyle": js_cohort_row_style,
    "autoGroupColumnDef": {"cellRendererParams": {"suppressCount": True}},
    "cellSelection": True,
    "copyHeadersToClipboard": True,
    "tooltipShowDelay": 1000,
    "aggFuncs": {"valuePerInstall": js_value_per_install},
}
if hide_hook:
    options["onStateUpdated"] = js_hide_columns
if suppress_virtualisation:
    # Probe aid only — see the module docstring.
    options["suppressColumnVirtualisation"] = True

gb.configure_grid_options(**options)

result = AgGrid(
    df,
    grid_options=gb.build(),
    height=720,
    allow_unsafe_jscode=True,
    enable_enterprise_modules=True,
    columns_state=restore_state,
    collect=["getColumnState"],
    update_on=["filterChanged", "sortChanged", "columnVisible", "columnPivotChanged"],
    key="cohort_pivot",
)

if result.column_state is not None:
    st.session_state["captured_state"] = result.column_state
