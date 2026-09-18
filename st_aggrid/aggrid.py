import inspect
import uuid
import warnings
from typing import Callable, Dict, List, Literal, Optional, Union

import pandas as pd
import streamlit as st

from st_aggrid.aggrid_utils import _parse_data_and_grid_options
from st_aggrid.color_scale import validate_color_scale_columns
from st_aggrid.component import get_aggrid_component
from st_aggrid.ratio import validate_ratio_columns
from st_aggrid.result import AgGridResult
from st_aggrid.shared import AgGridTheme, JsCode, StAggridTheme, walk_grid_options


#: AG-Grid events this component serves as lifecycle callbacks bound at grid
#: creation rather than as subscriptions. Each is emitted at most once per grid
#: instance, and ``gridReady`` is itself the event that makes subscription
#: possible, so ``AgGridComponent`` calls the collector directly for both. They
#: work as zero-interaction ``update_on`` triggers; what they cannot take is a
#: debounce, which is all this module now rejects.
#:
#: Mirrors ``LIFECYCLE_EVENTS`` in
#: ``st_aggrid/frontend/src/hooks/useAutoCollect.ts``. The two must agree: the
#: hook skips exactly these names when attaching listeners, so a name here that
#: is missing there would be collected twice.
LIFECYCLE_UPDATE_ON_EVENTS: frozenset = frozenset(
    {"gridReady", "firstDataRendered"}
)


def validate_update_on(update_on: Optional[List]) -> None:
    """Reject a debounce on an event that fires at most once.

    A debounce coalesces a burst of firings. ``gridReady`` and
    ``firstDataRendered`` are emitted once per grid creation, so
    ``(name, debounce_ms)`` on either is a request the component cannot honour
    — and dropping it silently is the failure class this guard exists to
    prevent. Every offender is reported in one raise, so a caller who debounced
    both fixes them in one pass.

    Args:
        update_on: The list as the caller passed it; ``None`` (meaning "use the
            default") is valid.

    Raises:
        ValueError: if any entry debounces an event in
            :data:`LIFECYCLE_UPDATE_ON_EVENTS`.
    """
    if not update_on:
        return

    offenders = [
        entry[0]
        for entry in update_on
        if isinstance(entry, (tuple, list))
        and entry
        and entry[0] in LIFECYCLE_UPDATE_ON_EVENTS
    ]
    if not offenders:
        return

    raise ValueError(
        f"update_on={offenders!r} cannot be debounced: these AG-Grid events are "
        "emitted at most once per grid creation, so there is no burst of "
        "firings for a debounce to coalesce. Pass the bare event name instead "
        f"(e.g. {offenders[0]!r}), which collects exactly once as soon as the "
        "grid is ready."
    )


def _callback_wants_result(callback: Callable) -> bool:
    """True if ``callback`` accepts the grid result as a positional argument.

    Callbacks were historically invoked with no arguments, so both arities have
    to keep working. Anything whose signature cannot be read is treated as
    zero-arity — the safe direction, since calling a zero-argument callable
    with an argument raises at the worst possible moment.
    """
    try:
        parameters = inspect.signature(callback).parameters.values()
    except (TypeError, ValueError):
        return False

    positional = (
        inspect.Parameter.POSITIONAL_ONLY,
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
        inspect.Parameter.VAR_POSITIONAL,
    )
    return any(p.kind in positional for p in parameters)


def _callback_has_required_keyword_only(callback: Callable) -> bool:
    """True if ``callback`` declares a keyword-only parameter with no default.

    Such a callback fits neither supported arity: it declares no positional
    parameter to receive the result, and it cannot be invoked with no
    arguments either. Rejecting it here beats a TypeError raised from inside
    a rerun, far from the AgGrid() call that accepted it.
    """
    try:
        parameters = inspect.signature(callback).parameters.values()
    except (TypeError, ValueError):
        return False
    return any(
        p.kind is inspect.Parameter.KEYWORD_ONLY
        and p.default is inspect.Parameter.empty
        for p in parameters
    )


def _wrap_callback(
    callback: Optional[Callable],
    key: Optional[str],
    original_data: Optional[pd.DataFrame],
) -> Callable[[], None]:
    """Adapt a user callback to the zero-argument shape CCv2 expects.

    A callback that takes an argument is handed an ``AgGridResult`` built from
    the component state Streamlit stores under ``key``; a zero-argument
    callback is passed straight through.
    """
    if callback is None:
        return lambda: None

    if not _callback_wants_result(callback):
        if _callback_has_required_keyword_only(callback):
            raise ValueError(
                "A callback with a required keyword-only parameter cannot be used: "
                "the component invokes callbacks with no arguments. Declare the grid "
                "result as a positional parameter instead, e.g. def cb(result)."
            )
        return callback

    if key is None:
        raise ValueError(
            "A callback that accepts the grid result requires key= to be set, "
            "because the result is read back from st.session_state[key]."
        )

    def _dispatch() -> None:
        callback(
            AgGridResult(
                component_result=st.session_state.get(key),
                original_data=original_data,
            )
        )

    return _dispatch


def AgGrid(
    data: Union[pd.DataFrame, str] = None,
    grid_options: Optional[Dict] = None,
    height: int = 400,
    collect: Optional[List[str]] = None,
    update_on: Optional[List] = None,
    allow_unsafe_jscode: bool = False,
    enable_enterprise_modules: Union[bool, Literal["enterpriseOnly", "enterprise+AgCharts"]] = False,
    license_key: Optional[str] = None,
    columns_state: Optional[Dict] = None,
    columns_state_mode: Literal["replace", "merge"] = "replace",
    initial_state: Optional[Dict] = None,
    theme: Union[str, StAggridTheme, None] = "streamlit",
    custom_css: Optional[Dict] = None,
    key: Optional[str] = None,
    show_toolbar: bool = False,
    show_search: bool = True,
    show_download_button: bool = False,
    show_find: bool = False,
    toolbar: Optional[Dict] = None,
    notes: Optional[Dict] = None,
    notes_editable: bool = False,
    notes_groups: Optional[List[Dict]] = None,
    debug_group_notes: bool = False,
    on_grid_state_change: Optional[Callable] = None,
    on_api_response_change: Optional[Callable] = None,
    use_json_serialization: Union[bool, Literal["auto"]] = "auto",
    debug: bool = False,
    pro_assets: Optional[List[Dict]] = None,
    **default_column_parameters,
) -> AgGridResult:
    """Renders a DataFrame using AG-Grid (CCv2, no iframe).

    Parameters
    ----------
    data : pd.DataFrame | pl.DataFrame | str | Path, optional
        The data to be displayed. Accepts Pandas/Polars DataFrames,
        JSON string in records format, or path to a JSON file.

    grid_options : dict, optional
        AG-Grid options dictionary. If None, auto-generated from data.
        Keys inside this dictionary must use AG-Grid's camelCase naming
        (``columnDefs``, ``defaultColDef``, ``rowSelection``, …).

    height : int, optional
        Grid height in pixels. Set to None for auto-height. Default: 400.

    collect : list[str], optional
        AG-Grid API method names to auto-collect on events.
        Example: ["getSelectedRows", "getFilterModel", "getColumnState"]
        Default: ["getSelectedRows"].

    update_on : list[str | tuple[str, int]], optional
        AG-Grid events that trigger auto-collection.
        Use tuple (event_name, debounce_ms) for debounced events.
        Default: ["selectionChanged", "filterChanged", "sortChanged"].
        "gridReady" and "firstDataRendered" are zero-interaction triggers that
        collect exactly once per grid creation; they cannot be debounced, and
        the tuple form raises ValueError for them. See
        LIFECYCLE_UPDATE_ON_EVENTS and the README's Auto-Collect section.

    allow_unsafe_jscode : bool, optional
        Allow JsCode injection in grid_options. Default: False.

    enable_enterprise_modules : bool | str, optional
        Enable AG-Grid Enterprise features. Default: False.

    license_key : str, optional
        AG-Grid Enterprise license key.

    columns_state : dict, optional
        A ColumnState[] list (the shape of ``getColumnState()``) applied to the
        grid. Covers visibility, order, width, pinning, sort, rowGroup, pivot and
        aggFunc. To clear an aggregation in pivot mode pass an explicit
        ``aggFunc: None`` (an omitted key leaves the aggregation in place) — the
        ``st_aggrid.column_state`` helpers do this for you.

    columns_state_mode : {"replace", "merge"}, optional
        How ``columns_state`` is applied. ``"replace"`` (default) applies it as a
        full layout (``applyOrder=True``) — use for restoring a complete saved
        layout. ``"merge"`` applies it as a partial overlay (``applyOrder=False``,
        no defaultState) so columns absent from the delta, and the user's manual
        per-column edits, are left untouched. Use ``"merge"`` to drive visibility
        from app controls without clobbering the user's Columns-panel edits.

    initial_state : dict, optional
        A raw AG-Grid ``GridState`` applied once at grid creation via the
        ``initialState`` prop. Unlike ``columns_state`` it also covers
        filterModel, group expansion, focus and scroll — use it to restore a full
        saved view. AG-Grid reads it only at creation, so switching views must
        remount the grid (change ``key``). Takes precedence over ``columns_state``
        for the pre-paint initial state.

    theme : str | StAggridTheme, optional
        Grid theme. Options: "streamlit", "alpine", "balham", "material",
        or a StAggridTheme instance. Default: "streamlit".

    custom_css : dict, optional
        Custom CSS rules as {selector: {prop: value}}.

    key : str, optional
        Streamlit widget key for state preservation.

    show_toolbar : bool, optional
        Show toolbar overlay. Default: False.

    show_search : bool, optional
        Show search in toolbar. Default: True.

    show_download_button : bool, optional
        Show CSV download button in toolbar. Default: False.

    show_find : bool, optional
        Show the Find widget in the toolbar (AG-Grid 35.3 **Enterprise** feature).
        Find highlights and lets you navigate matches *without* hiding rows —
        independent of ``show_search`` (quick-filter), so both can be enabled at
        once. Requires ``enable_enterprise_modules``; no-op in community mode.
        Tune behaviour via ``grid_options["findOptions"]``
        (``{"caseSensitive": bool, "currentPageOnly": bool, "searchDetail": bool}``);
        Find APIs (``findNext``, ``findGoTo``, ``findGetTotalMatches``, …) are also
        callable from Python via ``call_grid_api``. Default: False.

    toolbar : dict, optional
        Native AG-Grid Quick Access Toolbar (AG-Grid 35.3 **Enterprise**), rendered
        in the grid chrome (distinct from the floating overlay toggled by
        ``show_toolbar``). Convenience for ``grid_options["toolbar"]`` — e.g.
        ``{"items": ["agQuickFilterToolbarItem", "separator", "agFindToolbarItem"]}``.
        Built-in items (``agQuickFilterToolbarItem``, ``agFindToolbarItem``,
        ``agRowGroupPanelToolbarItem``, ``agPivotPanelToolbarItem``,
        ``agMenuToolbarItem``, ``separator``) are plain strings. Custom action items
        are **dicts** — ``{"label", "icon", "alignment", "action": JsCode(...)}`` —
        and need ``allow_unsafe_jscode=True`` for the ``action`` callback (a bare
        ``JsCode`` as a direct list element is NOT converted; wrap it in the item
        dict). If you enable ``agQuickFilterToolbarItem`` / ``agFindToolbarItem``
        here, disable the matching floating buttons (``show_search=False`` /
        ``show_find=False``) so two inputs don't bind the same grid option.
        Requires ``enable_enterprise_modules``. Default: None.

    notes : dict, optional
        Cell Notes (AG-Grid 35.3 **Enterprise**) seeded from the host as a map
        ``{rowId: {colId: note_text}}`` where ``rowId`` matches the grid's
        ``getRowId``. Notes are view-only by default (see ``notes_editable``).
        Requires a **stable** ``getRowId`` — the auto row id is the positional
        index and shifts if the DataFrame is re-sorted/filtered host-side, which
        would mis-attach notes; supply your own ``getRowId`` / id column. Requires
        ``enable_enterprise_modules`` (no-op + warning in community mode). For full
        control you may instead supply your own ``notesDataSource`` via
        ``grid_options`` (with ``JsCode`` + ``allow_unsafe_jscode``). Default: None.

    notes_editable : bool, optional
        When True, ``notes`` become editable in the grid (add/edit/remove) and
        changes are posted back to the host — read ``result.notes`` (a sticky
        ``{token, notes}`` payload that survives reruns). When False (default),
        notes are read-only annotations and nothing is sent back. Default: False.

    notes_groups : list[dict], optional
        Group-dimension Notes (AG-Grid 35.3 **Enterprise**) — read-only notes that
        annotate **row groups** by a predicate over their dimensions, for which the
        flat ``notes`` map can't work (group rows have grid-generated ids). Each
        rule is ``{"match": {field: value, ...}, "note": text_or_obj}``. A rule
        shows on a group row iff its ``match`` is a **subset** of that row's
        dimension ancestry (so it appears regardless of which other dimensions the
        grid groups by, or in what order — as long as every ``match`` field is an
        active row group). It is drawn on the **boundary** row (where the match
        first completes) and, when several rules complete on the same row, the one
        with the **most** ``match`` fields wins. ``match`` keys are grid field ids
        (colIds), not value labels; a ``YYYY-MM-DD`` value matches a date key by its
        first 10 chars, others compare exactly. Read-only (no write-back). Requires
        ``enable_enterprise_modules`` (no-op + warning in community mode).
        Default: None.

    debug_group_notes : bool, optional
        Diagnostic probe for the planned group-dimension notes feature (AG-Grid
        35.3 **Enterprise**; see ``REQUIREMENT-group-dimension-notes.md``). Installs
        a full-width notesDataSource that, for every row-group, logs its
        ``{field: key}`` dimension ancestry to the browser console and renders a
        note showing it. Use it on a grouped/pivot grid to confirm group-row notes
        render and to read the exact dimension keys. Read-only, no write-back; pair
        with ``debug=True``. Default: False.

    on_grid_state_change : callable, optional
        Called when auto-collected grid state changes. May take no arguments,
        or a single argument which receives the ``AgGridResult``. The
        result-taking form requires ``key`` to be set.

    on_api_response_change : callable, optional
        Called when an explicit API call returns a response. May take no
        arguments, or a single argument which receives the ``AgGridResult``.
        The result-taking form requires ``key`` to be set.

    use_json_serialization : bool | "auto", optional
        Whether to serialize rowData as a JSON string (bypasses Arrow
        limits for DataFrames with heterogeneous list/set cells).
        Default: "auto" — detect at runtime.

    debug : bool, optional
        Enable verbose client-side logging. Default: False.

    pro_assets : list[dict], optional
        Extra JS/CSS assets to inject on the client side.
        Each item is ``{"js": "<url>"}`` or ``{"css": "<url>"}``.

    **default_column_parameters
        Additional parameters passed to defaultColDef.

    Returns
    -------
    AgGridResult
        Provides typed access to:
        - .selected_rows: Selected rows as DataFrame
        - .column_state: Column state list
        - .filter_model: Current filter model
        - .grid_state: Full AG-Grid state
        - .event_name: Name of triggering event
        - .api_response: Response from explicit API call
        - .notes: Cell-note edits posted back (editable-notes grids)
        - .data: Original input DataFrame
        - .get(key): Access any auto-collected value by key
    """
    # Defaults
    validate_update_on(update_on)
    if collect is None:
        collect = ["getSelectedRows"]
    if update_on is None:
        update_on = ["selectionChanged", "filterChanged", "sortChanged"]

    # Parse theme
    if isinstance(theme, (str, AgGridTheme)):
        theme_obj = StAggridTheme(None)
        theme_obj["themeName"] = theme if isinstance(theme, str) else theme.value
    elif isinstance(theme, StAggridTheme):
        theme_obj = theme
    elif theme is None:
        theme_obj = StAggridTheme(None)
        theme_obj["themeName"] = "streamlit"
    else:
        raise ValueError(
            f"{theme} is not valid. Available: {AgGridTheme.__members__}"
        )

    # Parse data and grid_options
    data_df, grid_options, column_types = _parse_data_and_grid_options(
        data,
        grid_options,
        default_column_parameters,
        allow_unsafe_jscode,
        use_json_serialization=use_json_serialization,
    )

    # A ratio column whose components are not in the data would aggregate to a
    # wrong number with nothing raised, so reject it here rather than let it
    # reach the browser. Checked against the data's columns: `stRatio` reads
    # row data, so a component needs no column of its own.
    #
    # Read from `column_types` (the dtypes snapshot) rather than `data_df`.
    # `_parse_data_and_grid_options` sets `data_df = None` whenever it
    # JSON-serializes rowData — which the default `use_json_serialization="auto"`
    # does for any frame carrying a dict cell, even in a column unrelated to
    # the ratio. Reading `data_df.columns` there would silently skip the check
    # that is this task's entire point. The dtypes are captured before that
    # branch, and before `::auto_unique_id::` is injected, so they are both
    # available and cleaner.
    validate_ratio_columns(
        grid_options,
        column_types.index if column_types is not None else None,
    )

    # A colour-scale declaration names no data fields, only a shape, so unlike
    # the ratio check above this one needs no column set and runs for every
    # grid — including one built entirely from `grid_options["rowData"]`.
    validate_color_scale_columns(grid_options)

    custom_css = custom_css or {}

    if height is None:
        grid_options["domLayout"] = "autoHeight"

    # Native Quick Access Toolbar (35.3): inject the convenience param into
    # grid_options so it rides the existing passthrough. Convert any JsCode in the
    # toolbar items (e.g. an item's `action` callback) when unsafe jscode is on —
    # _parse_data_and_grid_options already ran for grid_options, so this subtree
    # needs its own pass.
    if toolbar is not None:
        if grid_options is None:
            grid_options = {}
        if allow_unsafe_jscode:
            walk_grid_options(
                toolbar, lambda v: v.js_code if isinstance(v, JsCode) else v
            )
        grid_options["toolbar"] = toolbar

    # Cell Notes (35.3) require Enterprise. Warn + drop in community mode rather
    # than shipping a notesDataSource the grid can't honor.
    notes_payload = notes
    if notes is not None and not enable_enterprise_modules:
        warnings.warn(
            "notes require enable_enterprise_modules; ignoring in community mode.",
            stacklevel=2,
        )
        notes_payload = None

    notes_groups_payload = notes_groups
    if notes_groups is not None and not enable_enterprise_modules:
        warnings.warn(
            "notes_groups require enable_enterprise_modules; ignoring in community mode.",
            stacklevel=2,
        )
        notes_groups_payload = None

    # Check for pending explicit API call
    api_call = None
    if key:
        api_call_key = f"_aggrid_api_call_{key}"
        api_call = st.session_state.pop(api_call_key, None)

    # Preserve original data for the result
    original_data = None
    if isinstance(data_df, pd.DataFrame):
        original_data = (
            data_df.drop("::auto_unique_id::", axis="columns")
            if "::auto_unique_id::" in data_df.columns
            else data_df
        )

    # Build data payload for CCv2. Keys must stay camelCase where the frontend
    # AgGridData TypeScript interface expects camelCase (rowData, gridOptions).
    component_data = {
        "rowData": data_df,  # CCv2 will Arrow-serialize the DataFrame
        "gridOptions": grid_options,
        "height": height,
        "collect": collect,
        "update_on": update_on,
        "allow_unsafe_jscode": allow_unsafe_jscode,
        "enable_enterprise_modules": enable_enterprise_modules,
        "license_key": license_key,
        "columns_state": columns_state,
        "columns_state_mode": columns_state_mode,
        "initial_state": initial_state,
        "theme": theme_obj,
        "custom_css": custom_css,
        "show_toolbar": show_toolbar,
        "show_search": show_search,
        "show_download_button": show_download_button,
        "show_find": show_find,
        "notes": notes_payload,
        "notes_editable": notes_editable,
        "notes_groups": notes_groups_payload,
        "debug_group_notes": debug_group_notes,
        "api_call": api_call,
        "pro_assets": pro_assets,
        "debug": debug,
    }

    # CCv2 callbacks take no arguments. Adapt any callback that asks for the
    # grid result, and keep a no-op in place otherwise so the component always
    # declares both state keys and the result attributes exist.
    on_grid_state_change = _wrap_callback(on_grid_state_change, key, original_data)
    on_api_response_change = _wrap_callback(on_api_response_change, key, original_data)

    # Mount the component
    result = get_aggrid_component()(
        data=component_data,
        key=key,
        on_grid_state_change=on_grid_state_change,
        on_api_response_change=on_api_response_change,
    )

    return AgGridResult(
        component_result=result,
        original_data=original_data,
    )


def call_grid_api(key: str, method: str, params: Optional[Dict] = None) -> None:
    """Queue an explicit AG-Grid API call.

    The call will be executed on the next Streamlit rerun.
    The result will be available via `result.api_response`.

    Parameters
    ----------
    key : str
        The key of the AgGrid component instance.
    method : str
        AG-Grid API method name (e.g., "exportDataAsCsv", "getColumnState").
    params : dict, optional
        Parameters to pass to the API method.

    Example
    -------
    `if st.button("Export CSV"):
         call_grid_api("my_grid", "exportDataAsCsv", {"fileName": "export.csv"})
    `
    """
    call_id = str(uuid.uuid4())
    st.session_state[f"_aggrid_api_call_{key}"] = {
        "method": method,
        "params": params or {},
        "call_id": call_id,
    }
