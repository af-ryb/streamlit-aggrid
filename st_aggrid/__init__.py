"""Public API for `st_aggrid`.

`validate_ratio_columns` and the name constants for all three built-in
aggregators are re-exported here so a consumer can validate its own grid
options, or reference an aggregator's name/context key, without importing
`st_aggrid.ratio` directly.

`stRatio`'s pair is exported under two names: `RATIO_AGG_FUNC`/
`RATIO_CONTEXT_KEY` are the **preferred** names — prefixed like their two
siblings (`RATIO_OF_RATIOS_AGG_FUNC`, `WEIGHTED_AVG_AGG_FUNC`) so
`from st_aggrid import RATIO_AGG_FUNC` says what it means at the call site.
`AGG_FUNC_NAME`/`CONTEXT_KEY` are the original, unprefixed names from
`st_aggrid.ratio` — kept exported, and always equal to the preferred pair
(same underlying object), for whatever may already import them. Prefer the
`RATIO_*` names in new code.

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

#: Preferred, prefixed names for `stRatio`'s aggFunc name / context key —
#: added alongside the pre-existing `AGG_FUNC_NAME`/`CONTEXT_KEY` (see module
#: docstring) rather than replacing them, since 2.3.0 has not shipped yet and
#: this is the last point a rename here is free; both pairs must always name
#: the same string.
RATIO_AGG_FUNC = AGG_FUNC_NAME
RATIO_CONTEXT_KEY = CONTEXT_KEY

__all__ = [
    "AGG_FUNC_NAME",
    "AgGrid",
    "AgGridResult",
    "AgGridTheme",
    "CONTEXT_KEY",
    "GridOptionsBuilder",
    "JsCode",
    "RATIO_AGG_FUNC",
    "RATIO_CONTEXT_KEY",
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
