import uuid
from typing import Callable, Dict, List, Literal, Optional, Union

import pandas as pd
import streamlit as st

from st_aggrid.aggrid_utils import _parse_data_and_grid_options
from st_aggrid.component import _aggrid_component
from st_aggrid.result import AgGridResult
from st_aggrid.shared import AgGridTheme, StAggridTheme


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
    theme: Union[str, StAggridTheme, None] = "streamlit",
    custom_css: Optional[Dict] = None,
    key: Optional[str] = None,
    show_toolbar: bool = False,
    show_search: bool = True,
    show_download_button: bool = False,
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

    allow_unsafe_jscode : bool, optional
        Allow JsCode injection in grid_options. Default: False.

    enable_enterprise_modules : bool | str, optional
        Enable AG-Grid Enterprise features. Default: False.

    license_key : str, optional
        AG-Grid Enterprise license key.

    columns_state : dict, optional
        Initial column state (visibility, order, width).

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

    on_grid_state_change : callable, optional
        Callback when auto-collected grid state changes.

    on_api_response_change : callable, optional
        Callback when an explicit API call returns a response.

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
        - .data: Original input DataFrame
        - .get(key): Access any auto-collected value by key
    """
    # Defaults
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
    data_df, grid_options, _column_types = _parse_data_and_grid_options(
        data,
        grid_options,
        default_column_parameters,
        allow_unsafe_jscode,
        use_json_serialization=use_json_serialization,
    )

    custom_css = custom_css or {}

    if height is None:
        grid_options["domLayout"] = "autoHeight"

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
        "theme": theme_obj,
        "custom_css": custom_css,
        "show_toolbar": show_toolbar,
        "show_search": show_search,
        "show_download_button": show_download_button,
        "api_call": api_call,
        "pro_assets": pro_assets,
        "debug": debug,
    }

    # Ensure callbacks are set so result attributes exist
    def _noop() -> None:
        return None

    if on_grid_state_change is None:
        on_grid_state_change = _noop
    if on_api_response_change is None:
        on_api_response_change = _noop

    # Mount the component
    result = _aggrid_component(
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
