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
it is the **merged** result that must resolve. That is how ``color_scale=True``
with no grid-level default is caught here instead of silently painting nothing
in the browser.

Two rules keep grid-level defaults harmless. Every key that is *present* is
type-checked, at both levels — a typo never survives. But a key a scheme does
not *read* is ignored, not rejected: a grid default of ``mode: "minmax"`` must
not break a column that says ``scheme: "fill"``.

The frontend implements the same resolution again, as a guard, because it has
to cope with grid options that never went through ``GridOptionsBuilder`` — but
returning ``null`` inside a cell renderer is a worse error than raising here,
so this copy is the one that talks to the developer.
"""

from __future__ import annotations

from typing import Optional

from st_aggrid._coldefs import column_label, iter_column_defs
from st_aggrid._numbers import is_finite_number

#: Where a declaration lives inside ``context``, at both levels.
COLOR_SCALE_CONTEXT_KEY = "stColorScale"

#: Scheme names. The three ramps' colours live in
#: ``frontend/src/colorScales/schemes.ts``; ``rank`` is a predicate (the best
#: value in the population) and ``fill`` a constant colour. These strings
#: must match ``schemes.ts``'s ``SCHEME_NAMES`` exactly.
COLOR_SCALE_SCHEMES = ("neutral", "positive", "diverging", "rank", "fill")

#: The schemes that run a ramp and so read ``mode``.
_RAMP_SCHEMES = ("neutral", "positive", "diverging")

#: Normalisation names, matching ``frontend/src/colorScales/normalize.ts``.
#: ``anchor`` measures deviation from a fixed value rather than from a
#: population statistic.
COLOR_SCALE_MODES = ("minmax", "zscore", "anchor")

#: What a population-based scheme is compared against: every row at the same
#: group depth (``level``), or only the row's siblings under one parent
#: (``parent``). Matches ``schemes.ts``'s ``SCOPE_NAMES``.
COLOR_SCALE_SCOPES = ("level", "parent")

#: Every key a declaration may carry.
_KNOWN_KEYS = (
    "scheme",
    "mode",
    "scope",
    "reverse",
    "skip_non_positive",
    "anchor",
    "span",
    "color",
)


def _validate_declaration(declaration: dict, where: str) -> None:
    """The rules shared by the grid-level and the column-level declaration:
    every present key has the right shape. Relevance is not checked here."""
    unknown = sorted(key for key in declaration if key not in _KNOWN_KEYS)
    if unknown:
        raise ValueError(
            f"{where}: unknown key(s) {unknown} in the colour scale "
            f"declaration. Available: {list(_KNOWN_KEYS)}."
        )

    for key, allowed in (
        ("scheme", COLOR_SCALE_SCHEMES),
        ("mode", COLOR_SCALE_MODES),
        ("scope", COLOR_SCALE_SCOPES),
    ):
        if key in declaration and declaration[key] not in allowed:
            raise ValueError(
                f"{where}['{key}'] must be one of {allowed}, got "
                f"{declaration[key]!r}."
            )

    for flag in ("reverse", "skip_non_positive"):
        # Checked against `bool` specifically: `bool` is an `int` subclass, so
        # an `isinstance(..., int)` test would accept `1`. Same trap
        # `_numbers.is_number` guards from the other direction.
        if flag in declaration and not isinstance(declaration[flag], bool):
            raise ValueError(
                f"{where}['{flag}'] must be a bool, got {declaration[flag]!r}."
            )

    if "anchor" in declaration and not is_finite_number(declaration["anchor"]):
        raise ValueError(
            f"{where}['anchor'] must be a finite number, got "
            f"{declaration['anchor']!r}."
        )

    if "span" in declaration and not (
        is_finite_number(declaration["span"]) and declaration["span"] > 0
    ):
        raise ValueError(
            f"{where}['span'] must be a finite number greater than zero, got "
            f"{declaration['span']!r}."
        )

    if "color" in declaration and not (
        isinstance(declaration["color"], str) and declaration["color"].strip()
    ):
        # No attempt to parse CSS: the browser is the only authority on what a
        # colour string means, and `var(--x)` cannot be checked from here.
        raise ValueError(
            f"{where}['color'] must be a non-empty CSS colour string, got "
            f"{declaration['color']!r}."
        )


def _merge_declaration(grid_declaration: Optional[dict], own: dict) -> dict:
    """The single place the column-over-grid-defaults rule lives: per key,
    the column's own declaration wins over the grid-level default. The
    frontend implements the same rule again in ``colorScales/index.ts``.
    """
    return {**(grid_declaration or {}), **own}


def _resolved_scheme(merged: dict) -> Optional[str]:
    """The scheme a merged declaration paints with. ``mode: "anchor"`` with no
    scheme at either level defaults to ``diverging`` — an anchored scale is
    almost always "above or below a reference" — and that is the one
    asymmetry in resolution. An explicit scheme always wins."""
    scheme = merged.get("scheme")
    if scheme is None and merged.get("mode") == "anchor":
        return "diverging"
    return scheme


def _validate_resolution(merged: dict, where: str) -> None:
    """The rules that only make sense on the merged declaration: it must
    resolve to a scheme, and that scheme's required keys must be present."""
    scheme = _resolved_scheme(merged)
    if scheme not in COLOR_SCALE_SCHEMES:
        raise ValueError(
            f"{where} resolves to no valid 'scheme'. Set one on the column, "
            f"or supply a grid-level default with "
            f"GridOptionsBuilder.configure_color_scale(scheme=...), or use "
            f"mode='anchor' (which defaults to 'diverging'). "
            f"Available: {COLOR_SCALE_SCHEMES}."
        )

    if scheme == "fill" and "color" not in merged:
        raise ValueError(
            f"{where} resolves to scheme 'fill' but no 'color'. Set one on "
            f"the column or as a grid-level default, e.g. "
            f"'var(--secondary-background-color)'."
        )

    if scheme in _RAMP_SCHEMES and merged.get("mode") == "anchor":
        missing = [key for key in ("anchor", "span") if key not in merged]
        if missing:
            raise ValueError(
                f"{where} resolves to mode 'anchor' but is missing {missing}. "
                f"An anchored scale needs the reference value ('anchor') and "
                f"the deviation that reaches full intensity ('span')."
            )


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
        _validate_resolution(_merge_declaration(grid_declaration, own), where)
