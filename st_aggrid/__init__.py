"""Public API for `st_aggrid`.

`validate_ratio_columns` and the six ratio/ratio-of-ratios/weighted-avg name
constants (`AGG_FUNC_NAME`, `CONTEXT_KEY`, `RATIO_OF_RATIOS_AGG_FUNC`,
`RATIO_OF_RATIOS_CONTEXT_KEY`, `WEIGHTED_AVG_AGG_FUNC`,
`WEIGHTED_AVG_CONTEXT_KEY`) are re-exported here so a consumer can validate
its own grid options, or reference an aggregator's name/context key, without
importing `st_aggrid.ratio` directly.

This does **not** help every consumer, though. A module that sits on an
import-time-`streamlit`-free path — e.g. a data-source discovery walk that
must not pull in `streamlit` as a side effect of import — cannot import
`st_aggrid` at all, and must hard-code the literal (`"stRatio"`, ...)
regardless of what this package exports. The re-export helps test code and
grid-builder modules, which import `st_aggrid` anyway.
"""

from st_aggrid.aggrid import AgGrid, call_grid_api
from st_aggrid.column_state import (
    derive_overlay,
    derive_user_hidden,
    set_visibility,
    visibility_state,
)
from st_aggrid.grid_options_builder import GridOptionsBuilder
from st_aggrid.ratio import (
    AGG_FUNC_NAME,
    CONTEXT_KEY,
    RATIO_OF_RATIOS_AGG_FUNC,
    RATIO_OF_RATIOS_CONTEXT_KEY,
    WEIGHTED_AVG_AGG_FUNC,
    WEIGHTED_AVG_CONTEXT_KEY,
    validate_ratio_columns,
)
from st_aggrid.result import AgGridResult
from st_aggrid.shared import (
    AgGridTheme,
    JsCode,
    StAggridTheme,
    walk_grid_options,
)

__all__ = [
    "AGG_FUNC_NAME",
    "AgGrid",
    "AgGridResult",
    "AgGridTheme",
    "CONTEXT_KEY",
    "GridOptionsBuilder",
    "JsCode",
    "RATIO_OF_RATIOS_AGG_FUNC",
    "RATIO_OF_RATIOS_CONTEXT_KEY",
    "StAggridTheme",
    "WEIGHTED_AVG_AGG_FUNC",
    "WEIGHTED_AVG_CONTEXT_KEY",
    "call_grid_api",
    "derive_overlay",
    "derive_user_hidden",
    "set_visibility",
    "validate_ratio_columns",
    "visibility_state",
    "walk_grid_options",
]
