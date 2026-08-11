"""Validation for the built-in ``stRatio`` and ``stRatioOfRatios``
aggregators' declarations.

The arithmetic lives in the frontend (``frontend/src/aggFuncs/stRatio.ts``,
``frontend/src/aggFuncs/stRatioOfRatios.ts``). Python's only job is to reject
a declaration that would otherwise produce a silently wrong number.

An unresolvable field name is the dangerous case: both aggregators sum
``rowNode.data[field]`` over a node's subtree, and a name that is not in the
data contributes ``0``, which skews the ratio without raising anything. Names
are checked against the **data**, not against ``columnDefs`` — a component only
has to be present in the row data, and requiring a column of its own would
reject the common case of an aggregation input that is never displayed.

That check needs a column set to check names against, so it only runs when
``AgGrid`` is called with a DataFrame. A grid fed entirely through
``grid_options["rowData"]`` (``data=None``) has no such column set, so a
typo'd field entry is not caught here — it reaches the browser and silently
contributes ``0``, same as a genuinely absent field would.

``stRatioOfRatios`` reuses ``stRatio``'s leg shape (``num``, ``den``, and
optionally ``num_signs``, ``multiplier``, ``scale``, ``den_const``) twice —
once for its ``from`` leg, once for its ``to`` leg — so ``_validate_leg``
below is the single place those per-leg rules live; ``stRatio``'s own
top-level config is validated as one leg of the same shape.

Sharing ``_validate_leg`` between the two aggregators changed the wording of
five pre-existing ``stRatio`` error messages, on purpose: a non-string field
name, ``multiplier``/``scale``/``den_const``, a non-numeric-list
``num_signs``, a length-mismatched ``num_signs``, and a non-numeric
``fill_null`` now all name their location as ``context['stRatio'][...]``
(previously just ``'key'``). The new text is strictly more specific — it
also correctly names the *leg's* location for a ``stRatioOfRatios`` error,
e.g. ``context['stRatioOfRatios']['from']['num_signs']`` — and nothing in
this codebase parses these strings; the existing tests match on a loose
substring (e.g. ``match="num_signs"``) precisely so wording is free to
improve without becoming a second thing every future change has to keep
in sync.
"""

from __future__ import annotations

from typing import Any, Callable, Iterable, Iterator, Optional, Sequence

AGG_FUNC_NAME = "stRatio"
CONTEXT_KEY = "stRatio"

#: Aggregator name and context key are always the same string, as with
#: `stRatio` above (see the plan's Global Constraints).
RATIO_OF_RATIOS_AGG_FUNC = RATIO_OF_RATIOS_CONTEXT_KEY = "stRatioOfRatios"

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


def _field_names(value: Any, key: str, label: str, context_path: str) -> list[str]:
    if not isinstance(value, (list, tuple)) or not value:
        raise ValueError(
            f"{label}: {context_path}['{key}'] must be a non-empty list of "
            f"field names, got {value!r}."
        )
    for name in value:
        if not isinstance(name, str) or not name:
            raise ValueError(
                f"{label}: every '{key}' entry in {context_path} must be a "
                f"non-empty string, got {value!r}."
            )
    return list(value)


def _validate_leg(
    leg: Any, label: str, context_path: str
) -> tuple[list[str], list[str]]:
    """Validate one ``{num, den, num_signs?, multiplier?, scale?, den_const?}``
    leg and return its resolved ``(num, den)`` field lists.

    Shared by ``stRatio``'s single top-level config (one leg) and each of
    ``stRatioOfRatios``'s two legs (``from``/``to``) — same rules, same
    messages, one place to keep them from drifting apart. ``context_path``
    names where in the declaration this leg lives (``"context['stRatio']"``,
    or ``"context['stRatioOfRatios']['from']"``) purely for error messages.

    Takes no ``known`` set: field-existence is deliberately **not** checked
    here — the caller does that once per column, over the union of every
    leg's fields, so a field shared between two legs (or between a leg's own
    ``num`` and ``den``) is reported once, not per occurrence.
    """
    if not isinstance(leg, dict):
        raise ValueError(
            f"{label}: {context_path} must be a dict, got {type(leg).__name__}."
        )

    num = _field_names(leg.get("num"), "num", label, context_path)

    for key in ("multiplier", "scale", "den_const"):
        if key in leg and leg[key] is not None and not _is_number(leg[key]):
            raise ValueError(
                f"{label}: {context_path}['{key}'] must be a number, got {leg[key]!r}."
            )

    # `den` may be an empty list only when `den_const` is a valid number: the
    # constant is then the whole denominator (SHARE_SPEC's `share`). Both
    # empty — no summed field and no constant — is still an error, so this
    # only widens `_field_names`' non-empty rule, never replaces it. The
    # numeric check above runs first so a malformed `den_const` (a string, a
    # bool) is reported by name instead of surfacing as a misleading "'den'
    # must be a non-empty list" error.
    den_value = leg.get("den")
    if (
        _is_number(leg.get("den_const"))
        and isinstance(den_value, (list, tuple))
        and not den_value
    ):
        den: list[str] = []
    else:
        den = _field_names(den_value, "den", label, context_path)

    signs = leg.get("num_signs")
    if signs is not None:
        if not isinstance(signs, (list, tuple)) or not all(_is_number(s) for s in signs):
            raise ValueError(
                f"{label}: {context_path}['num_signs'] must be a list of "
                f"numbers, got {signs!r}."
            )
        if len(signs) != len(num):
            raise ValueError(
                f"{label}: {context_path}['num_signs'] has {len(signs)} "
                f"entries but 'num' has {len(num)}; they must line up term "
                f"for term."
            )

    return num, den


def _check_known_fields(
    fields: Sequence[str], label: str, agg_func_name: str, known: Optional[set]
) -> None:
    """Raise when any of ``fields`` is not in ``known``. A no-op when
    ``known`` is ``None`` — the field-existence check only runs when
    ``AgGrid`` was called with a DataFrame (see module docstring)."""
    if known is None:
        return
    unknown = [name for name in fields if name not in known]
    if unknown:
        raise ValueError(
            f"{label}: unknown field(s) {unknown} in the ratio declaration. "
            f"{agg_func_name} sums these from the row data; a name that is "
            f"not there contributes 0 and silently skews the ratio. "
            f"Available: {sorted(known)}."
        )


def _validate_fill_null(config: dict, label: str, context_path: str) -> None:
    if "fill_null" in config:
        fill_null = config["fill_null"]
        if fill_null is not None and not _is_number(fill_null):
            raise ValueError(
                f"{label}: {context_path}['fill_null'] must be a number or "
                f"None, got {fill_null!r}."
            )


def _validate_stratio_config(config: Any, column: dict, known: Optional[set]) -> None:
    """``context["stRatio"]`` is a single leg, plus its own `fill_null`."""
    label = _label(column)
    context_path = f"context['{CONTEXT_KEY}']"

    num, den = _validate_leg(config, label, context_path)
    _validate_fill_null(config, label, context_path)
    _check_known_fields((*num, *den), label, AGG_FUNC_NAME, known)


def _validate_ratio_of_ratios_config(
    config: Any, column: dict, known: Optional[set]
) -> None:
    """``context["stRatioOfRatios"]`` is two legs (``from``, ``to``), each the
    same shape ``_validate_leg`` already validates for ``stRatio``, plus one
    outer `fill_null` — a leg has no `fill_null` of its own (see
    `RatioOfRatiosSpec`), so it is validated once here rather than per leg.
    Field-existence runs once over the deduplicated union of all four field
    lists, so a field named in both legs (or by both `num` and `den` of the
    same leg) is reported once, not once per occurrence.
    """
    label = _label(column)
    context_path = f"context['{RATIO_OF_RATIOS_CONTEXT_KEY}']"

    if not isinstance(config, dict):
        raise ValueError(
            f"{label}: {context_path} must be a dict, got {type(config).__name__}."
        )

    fields: list[str] = []
    for leg_key in ("from", "to"):
        leg_path = f"{context_path}['{leg_key}']"
        num, den = _validate_leg(config.get(leg_key), label, leg_path)
        fields.extend(num)
        fields.extend(den)

    _validate_fill_null(config, label, context_path)
    _check_known_fields(
        list(dict.fromkeys(fields)), label, RATIO_OF_RATIOS_AGG_FUNC, known
    )


#: Dispatch table: context key -> (validator, "no context" declaration hint).
#: Since aggregator name and context key are always the same string (Global
#: Constraints), this table's keys double as the set of `aggFunc` names
#: `validate_ratio_columns` recognizes. One table, not two dicts keyed by the
#: same names kept in sync by hand: a validator with no matching hint (or
#: vice versa) would otherwise turn the "aggFunc without context" path into a
#: bare `KeyError` instead of the intended `ValueError` — exactly the kind of
#: gap a new aggregator (`stWeightedAvg`) could fall into silently.
_AGGREGATORS: dict[str, tuple[Callable[[Any, dict, Optional[set]], None], str]] = {
    AGG_FUNC_NAME: (_validate_stratio_config, "'num' and 'den'"),
    RATIO_OF_RATIOS_AGG_FUNC: (_validate_ratio_of_ratios_config, "'from' and 'to'"),
}


def validate_ratio_columns(
    grid_options: Optional[dict],
    data_columns: Optional[Iterable[str]] = None,
) -> None:
    """Raise ``ValueError`` for a malformed or unresolvable ratio declaration.

    The single entry point and the single colDef walk for every built-in
    ratio aggregator's declaration (``stRatio``, ``stRatioOfRatios``). For
    each column, every context key in `_AGGREGATORS` is checked: present ->
    validated by its dispatched function; absent but named by `aggFunc` ->
    rejected, mirroring the sibling aggregator's own rule.

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
        every declaration are validated against this set. ``None`` skips the
        field-existence check — the structural rules still apply — allowing
        the caller to opt out when columns are not available.
    """
    if not isinstance(grid_options, dict):
        return

    known = set(data_columns) if data_columns is not None else None

    for column in _iter_column_defs(grid_options.get("columnDefs")):
        raw_context = column.get("context")
        context = raw_context if isinstance(raw_context, dict) else {}
        agg_func = column.get("aggFunc")

        for name, (validate, hint) in _AGGREGATORS.items():
            config = context.get(name)
            if config is not None:
                validate(config, column, known)
            elif agg_func == name:
                raise ValueError(
                    f"{_label(column)}: aggFunc {name!r} requires "
                    f"context[{name!r}] carrying {hint}."
                )
