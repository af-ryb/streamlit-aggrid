"""Validation for the built-in colour scales' declarations.

The arithmetic lives in the frontend (``frontend/src/colorScales/``). Python's
only job here is to reject a declaration that would otherwise paint nothing
with nothing raised — which is indistinguishable, on screen, from the feature
being switched off.

Unlike ``ratio.py``'s validator this one needs no DataFrame: a colour scale
names no data fields, only a shape. So it runs for every grid, including one
fed entirely through ``grid_options["rowData"]``.

A declaration lives under ``context['stColorScale']`` at two levels. The grid
level (``gridOptions['context']``) carries **defaults only** and never
activates painting; a column is painted when its own colDef carries an entry
that is not ``False``. The two are merged per key with the column winning, and
it is the **merged** result that must name a valid scheme. That is how
``color_scale=True`` with no grid-level default is caught here instead of
silently painting nothing in the browser.

The frontend implements the same merge again, as a guard, because it has to
cope with grid options that never went through ``GridOptionsBuilder`` — but
returning ``null`` inside a cell renderer is a worse error than raising here,
so this copy is the one that talks to the developer.
"""

from __future__ import annotations

from typing import Optional

from st_aggrid._coldefs import column_label, iter_column_defs

#: Where a declaration lives inside ``context``, at both levels.
COLOR_SCALE_CONTEXT_KEY = "stColorScale"

#: Palette names. The colours and ramps live in
#: ``frontend/src/colorScales/schemes.ts``; these strings must match its
#: ``SCHEMES`` keys exactly.
COLOR_SCALE_SCHEMES = ("neutral", "positive", "diverging")

#: Normalisation names, matching ``frontend/src/colorScales/normalize.ts``.
COLOR_SCALE_MODES = ("minmax", "zscore")

#: Every key a v1 declaration may carry. ``reverse`` is deliberately absent:
#: it is phase 2's metric-direction flag, and accepting it now would let a
#: consumer come to depend on a key the frontend ignores.
_KNOWN_KEYS = ("scheme", "mode", "skip_non_positive")


def _validate_declaration(declaration: dict, where: str) -> None:
    """The rules shared by the grid-level and the column-level declaration."""
    unknown = sorted(key for key in declaration if key not in _KNOWN_KEYS)
    if unknown:
        raise ValueError(
            f"{where}: unknown key(s) {unknown} in the colour scale "
            f"declaration. Available: {list(_KNOWN_KEYS)}."
        )

    if "scheme" in declaration and declaration["scheme"] not in COLOR_SCALE_SCHEMES:
        raise ValueError(
            f"{where}['scheme'] must be one of {COLOR_SCALE_SCHEMES}, got "
            f"{declaration['scheme']!r}."
        )

    if "mode" in declaration and declaration["mode"] not in COLOR_SCALE_MODES:
        raise ValueError(
            f"{where}['mode'] must be one of {COLOR_SCALE_MODES}, got "
            f"{declaration['mode']!r}."
        )

    if "skip_non_positive" in declaration and not isinstance(
        declaration["skip_non_positive"], bool
    ):
        # Checked against `bool` specifically: `bool` is an `int` subclass, so
        # an `isinstance(..., int)` test would accept `1`. Same trap
        # `ratio.py`'s `_is_number` documents from the other direction.
        raise ValueError(
            f"{where}['skip_non_positive'] must be a bool, got "
            f"{declaration['skip_non_positive']!r}."
        )


def _merge_declaration(grid_declaration: Optional[dict], own: dict) -> dict:
    """The single place the column-over-grid-defaults rule lives: per key,
    the column's own declaration wins over the grid-level default. The
    frontend implements the same rule again in ``colorScales/index.ts``.
    """
    return {**(grid_declaration or {}), **own}


def validate_color_scale_columns(grid_options: Optional[dict]) -> None:
    """Raise ``ValueError`` for a malformed or unresolvable colour-scale
    declaration.

    Parameters
    ----------
    grid_options:
        The built grid options. Ignored when not a dict.
    """
    if not isinstance(grid_options, dict):
        return

    raw_grid_context = grid_options.get("context")
    grid_context = raw_grid_context if isinstance(raw_grid_context, dict) else {}
    grid_declaration = grid_context.get(COLOR_SCALE_CONTEXT_KEY)

    if grid_declaration is not None:
        if not isinstance(grid_declaration, dict):
            raise ValueError(
                f"gridOptions context['{COLOR_SCALE_CONTEXT_KEY}'] must be a "
                f"dict, got {type(grid_declaration).__name__}. The grid level "
                f"carries defaults only; a column opts in with its own entry."
            )
        _validate_declaration(
            grid_declaration, f"gridOptions context['{COLOR_SCALE_CONTEXT_KEY}']"
        )

    for column in iter_column_defs(grid_options.get("columnDefs")):
        raw_context = column.get("context")
        context = raw_context if isinstance(raw_context, dict) else {}
        if COLOR_SCALE_CONTEXT_KEY not in context:
            continue

        own = context[COLOR_SCALE_CONTEXT_KEY]
        where = f"{column_label(column)}: context['{COLOR_SCALE_CONTEXT_KEY}']"

        if own is False:
            continue
        if own is True:
            own = {}
        elif not isinstance(own, dict):
            raise ValueError(
                f"{where} must be True, False or a dict, got "
                f"{type(own).__name__}."
            )

        _validate_declaration(own, where)

        merged = _merge_declaration(grid_declaration, own)
        if merged.get("scheme") not in COLOR_SCALE_SCHEMES:
            raise ValueError(
                f"{where} resolves to no valid 'scheme'. Set one on the "
                f"column, or supply a grid-level default with "
                f"GridOptionsBuilder.configure_color_scale(scheme=...). "
                f"Available: {COLOR_SCALE_SCHEMES}."
            )
