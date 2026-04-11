from typing import Any, Dict, List, Optional

import pandas as pd


class AgGridResult:
    """Result from an AgGrid component instance.

    Provides typed access to auto-collected grid state and explicit API call responses.
    """

    def __init__(
        self,
        component_result: Any,
        original_data: Optional[pd.DataFrame] = None,
    ):
        self._component_result = component_result
        self._original_data = original_data

    @property
    def _grid_state(self) -> Optional[Dict]:
        if self._component_result is None:
            return None
        gs = getattr(self._component_result, "grid_state", None)
        return gs

    @property
    def _api_response(self) -> Optional[Dict]:
        if self._component_result is None:
            return None
        return getattr(self._component_result, "api_response", None)

    @property
    def data(self) -> Optional[pd.DataFrame]:
        """Original data (read-only grid, data doesn't change)."""
        return self._original_data

    @property
    def selected_rows(self) -> Optional[pd.DataFrame]:
        """Selected rows as a DataFrame."""
        if self._grid_state and "selectedRows" in self._grid_state:
            rows = self._grid_state["selectedRows"]
            if rows:
                df = pd.DataFrame(rows)
                # Remove internal columns
                return df[[c for c in df.columns if not c.startswith("::")]]
        return None

    @property
    def column_state(self) -> Optional[List[Dict]]:
        """Column state (width, visibility, order, pinned, etc.)."""
        if self._grid_state:
            return self._grid_state.get("columnState")
        return None

    @property
    def filter_model(self) -> Optional[Dict]:
        """Current filter model."""
        if self._grid_state:
            return self._grid_state.get("filterModel")
        return None

    @property
    def sort_model(self) -> Optional[List[Dict]]:
        """Current sort model."""
        if self._grid_state:
            return self._grid_state.get("sortModel")
        return None

    @property
    def grid_state(self) -> Optional[Dict]:
        """Full grid state from AG-Grid getState()."""
        if self._grid_state:
            return self._grid_state.get("state")
        return None

    @property
    def displayed_row_count(self) -> Optional[int]:
        """Number of displayed rows (if collected)."""
        if self._grid_state:
            return self._grid_state.get("displayedRowCount")
        return None

    @property
    def event_name(self) -> Optional[str]:
        """Name of the event that triggered this update."""
        if self._grid_state:
            return self._grid_state.get("eventName")
        return None

    @property
    def event_data(self) -> Optional[Dict]:
        """Serialized event data from the triggering event."""
        if self._grid_state:
            return self._grid_state.get("eventData")
        return None

    @property
    def api_response(self) -> Optional[Dict]:
        """Response from an explicit API call (one-shot trigger)."""
        return self._api_response

    def get(self, key: str, default: Any = None) -> Any:
        """Get any auto-collected value by its key name."""
        if self._grid_state:
            return self._grid_state.get(key, default)
        return default

    def __getitem__(self, key: str) -> Any:
        """Dictionary-like access to auto-collected values."""
        if self._grid_state and key in self._grid_state:
            return self._grid_state[key]
        raise KeyError(key)

    def __repr__(self) -> str:
        state_keys = list(self._grid_state.keys()) if self._grid_state else []
        return f"AgGridResult(event={self.event_name}, state_keys={state_keys})"
