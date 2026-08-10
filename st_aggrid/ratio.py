"""Validation for the built-in ``stRatio`` aggregator's declaration.

The arithmetic lives in the frontend (``frontend/src/aggFuncs/stRatio.ts``).
Python's only job is to reject a declaration that would otherwise produce a
silently wrong number.

An unresolvable field name is the dangerous case: the aggregator sums
``rowNode.data[field]`` over a node's subtree, and a name that is not in the
data contributes ``0``, which skews the ratio without raising anything. Names
are checked against the **data**, not against ``columnDefs`` — a component only
has to be present in the row data, and requiring a column of its own would
reject the common case of an aggregation input that is never displayed.

That check needs a column set to check names against, so it only runs when
``AgGrid`` is called with a DataFrame. A grid fed entirely through
``grid_options["rowData"]`` (``data=None``) has no such column set, so a
typo'd ``num``/``den`` entry is not caught here — it reaches the browser and
silently contributes ``0``, same as a genuinely absent field would.
"""

from __future__ import annotations

from typing import Any, Iterable, Iterator, Optional

AGG_FUNC_NAME = "stRatio"
CONTEXT_KEY = "stRatio"

_NUMERIC = (int, float)


def _is_number(value: Any) -> bool:
    # bool is an int subclass; a True multiplier is a mistake, not a 1.
    return isinstance(value, _NUMERIC) and not isinstance(value, bool)


def _iter_column_defs(column_defs: Any) -> Iterator[dict]:
    """Every leaf and group colDef, depth first. Column groups nest their
    columns under ``children``; a walk that stops at the top level would cover
    nothing on a grouped grid."""
    if not isinstance(column_defs, (list, tuple)):
        return
    for column in column_defs:
        if not isinstance(column, dict):
            continue
        yield column
        yield from _iter_column_defs(column.get("children"))


def _label(column: dict) -> str:
    name = column.get("colId") or column.get("field")
    return f"column {name!r}" if name else "unnamed ratio column"


def _field_names(value: Any, key: str, label: str) -> list[str]:
    if not isinstance(value, (list, tuple)) or not value:
        raise ValueError(
            f"{label}: context['{CONTEXT_KEY}']['{key}'] must be a non-empty "
            f"list of field names, got {value!r}."
        )
    for name in value:
        if not isinstance(name, str) or not name:
            raise ValueError(
                f"{label}: every '{key}' entry must be a non-empty string, "
                f"got {value!r}."
            )
    return list(value)


def _validate_config(config: Any, column: dict, known: Optional[set]) -> None:
    label = _label(column)

    if not isinstance(config, dict):
        raise ValueError(
            f"{label}: context['{CONTEXT_KEY}'] must be a dict, "
            f"got {type(config).__name__}."
        )

    num = _field_names(config.get("num"), "num", label)
    den = _field_names(config.get("den"), "den", label)

    signs = config.get("num_signs")
    if signs is not None:
        if not isinstance(signs, (list, tuple)) or not all(_is_number(s) for s in signs):
            raise ValueError(f"{label}: 'num_signs' must be a list of numbers, got {signs!r}.")
        if len(signs) != len(num):
            raise ValueError(
                f"{label}: 'num_signs' has {len(signs)} entries but 'num' has "
                f"{len(num)}; they must line up term for term."
            )

    for key in ("multiplier", "scale"):
        if key in config and config[key] is not None and not _is_number(config[key]):
            raise ValueError(f"{label}: '{key}' must be a number, got {config[key]!r}.")

    if "fill_null" in config:
        fill_null = config["fill_null"]
        if fill_null is not None and not _is_number(fill_null):
            raise ValueError(
                f"{label}: 'fill_null' must be a number or None, got {fill_null!r}."
            )

    if known is not None:
        unknown = [name for name in (*num, *den) if name not in known]
        if unknown:
            raise ValueError(
                f"{label}: unknown field(s) {unknown} in the ratio declaration. "
                f"{AGG_FUNC_NAME} sums these from the row data; a name that is "
                f"not there contributes 0 and silently skews the ratio. "
                f"Available: {sorted(known)}."
            )


def validate_ratio_columns(
    grid_options: Optional[dict],
    data_columns: Optional[Iterable[str]] = None,
) -> None:
    """Raise ``ValueError`` for a malformed or unresolvable ratio declaration.

    The structural rules ('num'/'den' shape, 'num_signs' length, numeric
    options) always run. The field-existence check — the one that catches a
    typo'd component name — only runs when `data_columns` is not None, which
    in practice means only when `AgGrid` was called with a DataFrame. A grid
    built entirely from `grid_options["rowData"]` has no column set to check
    names against, so that path is **not** covered: an unresolvable name
    reaches the browser and silently contributes 0 to the ratio instead of
    raising here.

    Parameters
    ----------
    grid_options:
        The built grid options. Ignored when None or when it declares no
        columns.
    data_columns:
        Column names available in the row data. When provided, field names in
        'num' and 'den' are validated against this set. ``None`` skips the
        field-existence check — the structural rules still apply — allowing
        the caller to opt out when columns are not available.
    """
    if not isinstance(grid_options, dict):
        return

    known = set(data_columns) if data_columns is not None else None

    for column in _iter_column_defs(grid_options.get("columnDefs")):
        context = column.get("context")
        config = context.get(CONTEXT_KEY) if isinstance(context, dict) else None

        if config is None:
            if column.get("aggFunc") == AGG_FUNC_NAME:
                raise ValueError(
                    f"{_label(column)}: aggFunc {AGG_FUNC_NAME!r} requires "
                    f"context[{CONTEXT_KEY!r}] carrying 'num' and 'den'."
                )
            continue

        _validate_config(config, column, known)
