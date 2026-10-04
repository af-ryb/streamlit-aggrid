"""Validation and transport for the built-in ``stRollup`` aggregator.

``stRollup`` shows a group row's total from a table the server computed
(``GROUP BY CUBE``) instead of computing it from the group's children — the
only correct choice for a distinct count, whose group value is not derivable
from its children's. The lookup lives in the frontend
(``frontend/src/aggFuncs/stRollup.ts``). This module rejects a declaration
whose lookups would all miss silently, and prepares the totals so that their
dimension values reach the browser through exactly the path the row data
takes: ``prepare_frame`` for both, and the same transport — Arrow, or the
same ``to_json`` call when the leaves go JSON. A ``date32`` value renders
differently through the two transports, so mixing them would make every date
key miss.

``rollup["data"]`` is the **whole** ``CUBE`` answer, full-grain rows
included: the deepest group of a grouping over every dimension is keyed by
all of them. Flags follow BigQuery's ``GROUPING()``: 1 — the level is rolled
up in this row; 0 — present, even when its value is NULL.
"""

from __future__ import annotations

from typing import Any, Optional, Union

import pandas as pd

from st_aggrid._coldefs import column_label, iter_column_defs
from st_aggrid.aggrid_utils import _dataframe_arrow_compatible, prepare_frame

#: Aggregator name and context key are the same string, as for `stRatio`.
AGG_FUNC_NAME = CONTEXT_KEY = "stRollup"

#: A dimension's flag column unless `rollup["flags"]` names another.
DEFAULT_FLAG_PREFIX = "_grouping_"

_ROLLUP_KEYS = {"data", "dimensions", "flags"}


def _rollup_columns(grid_options: Any) -> list[dict]:
    if not isinstance(grid_options, dict):
        return []
    return [
        column
        for column in iter_column_defs(grid_options.get("columnDefs"))
        if column.get("aggFunc") == AGG_FUNC_NAME
    ]


def _value_field(column: dict) -> str:
    """The totals column a `stRollup` column reads: `context["stRollup"]["field"]`
    when given, else the colDef's own `field`."""
    context = column.get("context")
    config = context.get(CONTEXT_KEY) if isinstance(context, dict) else None
    if config is not None:
        if not isinstance(config, dict) or not isinstance(config.get("field", ""), str):
            raise ValueError(
                f"{column_label(column)}: context['{CONTEXT_KEY}'] must be a dict "
                f"whose optional 'field' is a string, got {config!r}."
            )
        if config.get("field"):
            return config["field"]
    field = column.get("field")
    if not isinstance(field, str) or not field:
        raise ValueError(
            f"{column_label(column)}: aggFunc '{AGG_FUNC_NAME}' needs a 'field', "
            f"or context['{CONTEXT_KEY}']['field'], naming the totals column to read."
        )
    return field


def _resolve_meta(rollup: Any) -> tuple[Any, dict]:
    if not isinstance(rollup, dict):
        raise ValueError(
            f"rollup must be a dict with 'data' and 'dimensions', got "
            f"{type(rollup).__name__}."
        )
    unknown = sorted(set(rollup) - _ROLLUP_KEYS)
    if unknown:
        raise ValueError(
            f"rollup has unknown key(s) {unknown}; expected 'data', 'dimensions' "
            f"and optionally 'flags'."
        )

    dimensions = rollup.get("dimensions")
    if (
        not isinstance(dimensions, (list, tuple))
        or not dimensions
        or not all(isinstance(d, str) and d for d in dimensions)
    ):
        raise ValueError(
            f"rollup['dimensions'] must be a non-empty list of field names, got "
            f"{dimensions!r}."
        )
    repeated = sorted({d for d in dimensions if list(dimensions).count(d) > 1})
    if repeated:
        raise ValueError(
            f"rollup['dimensions'] names {repeated} more than once."
        )

    flags = rollup.get("flags") or {}
    if not isinstance(flags, dict) or not all(
        isinstance(k, str) and isinstance(v, str) and v for k, v in flags.items()
    ):
        raise ValueError(
            f"rollup['flags'] must map dimension names to flag column names, got "
            f"{flags!r}."
        )
    stray = sorted(k for k in flags if k not in dimensions)
    if stray:
        raise ValueError(
            f"rollup['flags'] names {stray}, which is not a dimension; "
            f"dimensions are {list(dimensions)}."
        )

    meta = {
        "dimensions": list(dimensions),
        "flags": {d: flags.get(d, f"{DEFAULT_FLAG_PREFIX}{d}") for d in dimensions},
    }
    return rollup.get("data"), meta


def _prepared_totals(data: Any) -> pd.DataFrame:
    """A prepared copy: the caller's frame is never changed."""
    if isinstance(data, pd.DataFrame):
        return prepare_frame(data.copy())
    converted = prepare_frame(data)  # polars → a new pandas frame
    if not isinstance(converted, pd.DataFrame):
        raise ValueError(
            f"rollup['data'] must be a pandas or polars DataFrame, got "
            f"{type(data).__name__}."
        )
    return converted


def serialisation_class(series: pd.Series) -> str:
    """How a column's values serialise, as far as a group key is concerned.

    Dtypes are too coarse (a ``datetime.date`` column and the ISO strings
    ``prepare_frame`` makes from ``datetime64`` are both ``object`` on pandas
    2) and too fine (int64 and float64-with-NaN render to the same key). Numbers
    are one class, booleans another, the rest is what pandas infers from the
    values.
    """
    from pandas.api.types import is_bool_dtype, is_numeric_dtype

    if is_bool_dtype(series.dtype):
        return "bool"
    if is_numeric_dtype(series.dtype):
        return "number"
    return pd.api.types.infer_dtype(series, skipna=True)


def serialisation_classes(frame: pd.DataFrame) -> dict[str, str]:
    return {str(name): serialisation_class(frame[name]) for name in frame.columns}


def _key_part(value: Any) -> str:
    """A present dimension's value as AG-Grid keys its group: NULL and `""`
    both group under `""`, a string stays as is, anything else is `str()`'d.
    Python's `str` and JavaScript's `String` differ for floats and dates, so
    this check can under-report there — never false-alarm."""
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return value if isinstance(value, str) else str(value)


def _check_unique_keys(totals: pd.DataFrame, dimensions: list, flags: dict) -> None:
    present = {d: (totals[flags[d]] == 0).to_numpy() for d in dimensions}
    values = {d: totals[d].to_numpy(dtype=object) for d in dimensions}
    seen: dict[tuple, int] = {}
    for position in range(len(totals)):
        key = tuple(
            sorted(
                (d, _key_part(values[d][position]))
                for d in dimensions
                if present[d][position]
            )
        )
        if key in seen:
            raise ValueError(
                f"rollup['data'] rows {seen[key]} and {position} (by position) "
                f"share the key {dict(key)!r}. A key must be unique: the grid "
                f"would show one of them at random. NULL and an empty string "
                f"group together in the grid, so they collide here too."
            )
        seen[key] = position


def prepare_rollup(
    rollup: Optional[dict],
    grid_options: Any,
    data_classes: Optional[dict[str, str]],
    leaves_as_json: bool,
) -> tuple[Union[pd.DataFrame, str, None], Optional[dict]]:
    """Validate ``rollup`` and return ``(payload, meta)`` for the component.

    ``data_classes`` are the row data's ``serialisation_classes`` after
    ``prepare_frame`` (``None`` for a grid without a DataFrame, which skips the
    checks against the leaves). ``leaves_as_json`` is true when the row data reaches the browser
    as JSON; the totals then do too.
    """
    columns = _rollup_columns(grid_options)

    if rollup is None:
        if columns:
            raise ValueError(
                f"{column_label(columns[0])}: aggFunc '{AGG_FUNC_NAME}' needs "
                f"AgGrid(rollup=...) — without the totals table every group cell "
                f"would be empty."
            )
        return None, None

    if not columns:
        raise ValueError(
            f"rollup= was given but no column declares aggFunc '{AGG_FUNC_NAME}'; "
            f"the totals table would never be read."
        )

    data, meta = _resolve_meta(rollup)
    totals = _prepared_totals(data)
    dimensions, flags = meta["dimensions"], meta["flags"]

    missing = [d for d in dimensions if d not in totals.columns]
    if missing:
        raise ValueError(
            f"rollup dimensions {missing} are not columns of rollup['data']; "
            f"it has {list(totals.columns)}."
        )
    if data_classes is not None:
        absent = [d for d in dimensions if d not in data_classes]
        if absent:
            raise ValueError(
                f"rollup dimensions {absent} are not columns of the row data; the "
                f"grid can never group by them."
            )

    for dimension in dimensions:
        flag = flags[dimension]
        if flag not in totals.columns:
            raise ValueError(
                f"rollup flag column {flag!r} (for dimension {dimension!r}) is not "
                f"a column of rollup['data']."
            )
        values = totals[flag]
        if values.isna().any() or not values.isin([0, 1]).all():
            raise ValueError(
                f"rollup flag column {flag!r} must hold only 0 or 1 (BigQuery "
                f"GROUPING()), got {sorted(map(repr, values.unique()))}."
            )

    for column in columns:
        field = _value_field(column)
        if field not in totals.columns:
            raise ValueError(
                f"{column_label(column)}: reads {field!r} from the totals, but "
                f"rollup['data'] has no such column."
            )

    if data_classes is not None:
        for dimension in dimensions:
            total_class = serialisation_class(totals[dimension])
            if data_classes[dimension] != total_class:
                raise ValueError(
                    f"rollup dimension {dimension!r} holds {total_class} values "
                    f"in rollup['data'] but {data_classes[dimension]} values in "
                    f"the row data. They serialise differently and no key would "
                    f"ever match; take both frames from one query result."
                )

    _check_unique_keys(totals, dimensions, flags)

    if leaves_as_json:
        return totals.to_json(orient="records", default_handler=str), meta
    if not _dataframe_arrow_compatible(totals):
        raise ValueError(
            "rollup['data'] cannot be sent as Arrow (a column holds lists or "
            "sets with mixed item types). Convert such a column to strings "
            "first, or send the row data as JSON too."
        )
    return totals, meta
