"""Column-state helpers for state-driven column visibility.

These are pure, framework-agnostic helpers (no Streamlit, no product
vocabulary) that build AG-Grid ``ColumnState[]`` deltas — the same shape
produced by ``gridApi.getColumnState()`` and accepted by the ``columns_state``
prop. They let an application drive column visibility through a *single*
channel (column state) instead of rebuilding ``columnDefs`` every rerun.

Design
------
Visibility is expressed differently per grid mode:

* **normal mode** — a column is hidden via ``{"colId": id, "hide": True}``.
* **pivot mode** — ``hide`` is ignored by AG-Grid; a value column shows iff it
  carries an ``aggFunc``. A hidden value column therefore needs an *explicit*
  ``{"aggFunc": None}`` — omitting the key leaves a stale aggregation in place
  (the frontend's ``extractColumnStateFromDefs`` only emits properties present
  in its input). These helpers always emit the explicit ``None`` so callers
  never hit that footgun.

Two owners, one surface
-----------------------
Column visibility commonly has two owners: coarse application controls (e.g. a
"show these groups" selector) and the user's fine manual edits in AG-Grid's
Columns tool panel. They reconcile on one surface — the column state — under a
**union-of-hides** rule: a governed column is visible iff the control includes
it *and* the user has not manually hidden it.

* :func:`visibility_state` turns a control selection into the delta to apply
  (call it every rerun, feeding it the user's accumulated manual hides).
* :func:`derive_user_hidden` recovers that manual-hide set from a captured live
  state, disambiguating a manual hide from a control exclusion via the control
  inclusion snapshot taken at capture time.

Apply the delta with ``AgGrid(..., columns_state=delta,
columns_state_mode="merge")`` so columns absent from the delta (structural
columns, and the user's edits elsewhere) are left untouched.
"""

from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Union

__all__ = ["set_visibility", "visibility_state", "derive_user_hidden"]

# An AG-Grid getColumnState()/applyColumnState() entry.
ColumnState = Dict[str, object]

# How to pick the aggFunc for a shown value column in pivot mode: one function
# for all columns (str) or per-column ({colId: aggFunc}).
AggFuncSpec = Union[str, Mapping[str, str]]


def _agg_func_for(col_id: str, value_agg_func: Optional[AggFuncSpec]) -> str:
    if isinstance(value_agg_func, str):
        return value_agg_func
    if isinstance(value_agg_func, Mapping):
        if col_id not in value_agg_func:
            raise ValueError(
                f"value_agg_func has no entry for visible value column {col_id!r}; "
                "in pivot mode every shown value column needs an aggFunc."
            )
        return value_agg_func[col_id]
    raise TypeError(
        "value_agg_func must be a str or a mapping {colId: aggFunc} when "
        "pivot_mode=True and there are visible columns."
    )


def set_visibility(
    *,
    visible_col_ids: Iterable[str],
    hidden_col_ids: Iterable[str],
    pivot_mode: bool = False,
    value_agg_func: Optional[AggFuncSpec] = None,
) -> List[ColumnState]:
    """Build a ``ColumnState[]`` delta for the listed columns only.

    Parameters
    ----------
    visible_col_ids, hidden_col_ids : iterable of str
        Column ids to show / hide. A column in neither list is omitted from the
        delta (and so left untouched under ``columns_state_mode="merge"``). If
        an id appears in both, "hidden" wins.
    pivot_mode : bool
        When True, visibility is expressed through ``aggFunc`` (value columns):
        shown -> the column's aggFunc, hidden -> ``None``. When False, through
        ``hide``.
    value_agg_func : str | mapping, optional
        The aggFunc to assign to *shown* value columns in pivot mode. A single
        string applies to all; a mapping ``{colId: aggFunc}`` assigns per
        column. Required when ``pivot_mode`` is True and there are visible
        columns.

    Returns
    -------
    list of dict
        ColumnState entries sorted by ``colId`` (stable output so the frontend's
        ``isEqual`` diff doesn't re-fire on dict-ordering noise).
    """
    visible = list(dict.fromkeys(visible_col_ids))
    hidden = set(hidden_col_ids)

    entries: Dict[str, ColumnState] = {}
    if pivot_mode:
        for cid in visible:
            if cid in hidden:
                continue  # hidden wins on overlap
            entries[cid] = {"colId": cid, "aggFunc": _agg_func_for(cid, value_agg_func)}
        for cid in hidden:
            entries[cid] = {"colId": cid, "aggFunc": None}
    else:
        for cid in visible:
            if cid in hidden:
                continue  # hidden wins on overlap
            entries[cid] = {"colId": cid, "hide": False}
        for cid in hidden:
            entries[cid] = {"colId": cid, "hide": True}

    return [entries[cid] for cid in sorted(entries)]


def visibility_state(
    *,
    governed_col_ids: Sequence[str],
    included_col_ids: Iterable[str],
    user_hidden_col_ids: Iterable[str] = (),
    pivot_mode: bool = False,
    value_agg_func: Optional[AggFuncSpec] = None,
) -> List[ColumnState]:
    """Build the visibility delta for a control's governed columns (union rule).

    ``visible = included - user_hidden`` and ``hidden = governed - visible``,
    all intersected with ``governed`` so the delta only ever touches columns
    this control owns. Call this every rerun and apply the result with
    ``columns_state_mode="merge"``.

    Parameters
    ----------
    governed_col_ids : sequence of str
        The full set of columns this control owns (its "universe"). Every one of
        them gets an explicit entry, so a column moving from excluded to included
        is re-shown.
    included_col_ids : iterable of str
        Columns the control currently includes (wants shown).
    user_hidden_col_ids : iterable of str
        Columns the user manually hid (see :func:`derive_user_hidden`). They stay
        hidden even when the control includes them.
    pivot_mode, value_agg_func
        See :func:`set_visibility`.
    """
    governed = set(governed_col_ids)
    included = set(included_col_ids) & governed
    user_hidden = set(user_hidden_col_ids) & governed
    visible = included - user_hidden
    hidden = governed - visible
    return set_visibility(
        visible_col_ids=visible,
        hidden_col_ids=hidden,
        pivot_mode=pivot_mode,
        value_agg_func=value_agg_func,
    )


def _reads_hidden(entry: Optional[ColumnState], pivot_mode: bool) -> bool:
    """Whether a captured ColumnState entry represents a hidden column.

    A missing entry (column absent from the capture) is treated as not-hidden:
    absence is not evidence of a manual hide.
    """
    if entry is None:
        return False
    if pivot_mode:
        return not entry.get("aggFunc")
    return entry.get("hide") is True


def derive_user_hidden(
    captured_state: Optional[Sequence[ColumnState]],
    *,
    governed_col_ids: Sequence[str],
    control_included_at_capture: Iterable[str],
    pivot_mode: bool = False,
) -> List[str]:
    """Recover the user's manual-hide set from a captured live column state.

    A governed column that reads *hidden* in ``captured_state`` but was
    *included* by the control when the state was captured can only have been
    hidden by the user — so it is a manual hide. A column the control excluded
    also reads hidden, but is filtered out here (that is the control's doing,
    not the user's).

    Pass the *raw* control inclusion (the same ``included_col_ids`` given to
    :func:`visibility_state`) as ``control_included_at_capture`` — not the
    post-user-hidden visible set — so the manual-hide set accumulates across
    interactions and a column drops out only when the user un-hides it.

    Parameters
    ----------
    captured_state : sequence of dict | None
        The ColumnState[] from ``AgGridResult.column_state`` (``getColumnState``
        output). ``None`` / empty -> no manual hides.
    governed_col_ids : sequence of str
        Columns this control owns.
    control_included_at_capture : iterable of str
        What the control included at the moment the state was captured.
    pivot_mode : bool
        Match the grid mode: pivot -> "hidden" means no aggFunc; normal ->
        ``hide is True``.

    Returns
    -------
    list of str
        Manually-hidden governed column ids, sorted.
    """
    governed = set(governed_col_ids)
    candidates = set(control_included_at_capture) & governed

    by_id: Dict[str, ColumnState] = {}
    for entry in captured_state or []:
        cid = entry.get("colId")
        if isinstance(cid, str):
            by_id[cid] = entry

    return sorted(cid for cid in candidates if _reads_hidden(by_id.get(cid), pivot_mode))
