"""Walking a ``columnDefs`` tree, shared by the built-in validators.

``ratio.py`` and ``color_scale.py`` both need every leaf and group colDef, and
both name a column the same way in their error messages. A walk that stopped
at the top level would cover nothing on a grouped grid — and the consumer this
exists for wraps every metric column in a group — so a second, independently
written copy of it is exactly the thing that drifts once only one of the two
callers is still being edited.
"""

from __future__ import annotations

from typing import Any, Iterator


def iter_column_defs(column_defs: Any) -> Iterator[dict]:
    """Every leaf and group colDef, depth first. Column groups nest their
    columns under ``children``."""
    if not isinstance(column_defs, (list, tuple)):
        return
    for column in column_defs:
        if not isinstance(column, dict):
            continue
        yield column
        yield from iter_column_defs(column.get("children"))


def column_label(column: dict) -> str:
    """How a colDef is named in a validation error.

    Named ``column_label`` rather than ``label`` because ``ratio.py``'s
    validators already bind a **local** ``label`` from it
    (``label = column_label(column)``); a function of the same name would be
    shadowed by that local and raise ``UnboundLocalError`` on the line that
    calls it.
    """
    name = column.get("colId") or column.get("field")
    return f"column {name!r}" if name else "unnamed aggregation column"
