"""AgGridResult reads a CCv2 component result.

The component result is an attribute-accessible mapping; SimpleNamespace is a
faithful enough stand-in to test the accessors without a Streamlit runtime.
"""

import types

import pandas as pd

from st_aggrid.result import AgGridResult


def _component_result(**kwargs):
    base = {"grid_state": None, "api_response": None, "notes": None}
    base.update(kwargs)
    return types.SimpleNamespace(**base)


def test_missing_component_result_yields_empty_accessors():
    result = AgGridResult(component_result=None, original_data=None)
    assert result.selected_rows is None
    assert result.column_state is None
    assert result.filter_model is None
    assert result.event_name is None
    assert result.get("anything") is None


def test_data_returns_the_original_frame():
    df = pd.DataFrame({"a": [1, 2]})
    result = AgGridResult(component_result=_component_result(), original_data=df)
    pd.testing.assert_frame_equal(result.data, df)


def test_selected_rows_become_a_dataframe_without_internal_columns():
    component = _component_result(
        grid_state={
            "selectedRows": [
                {"a": 1, "::auto_unique_id::": "0"},
                {"a": 2, "::auto_unique_id::": "1"},
            ]
        }
    )
    result = AgGridResult(component_result=component, original_data=None)
    assert list(result.selected_rows.columns) == ["a"]
    assert result.selected_rows["a"].tolist() == [1, 2]


def test_empty_selection_is_none():
    component = _component_result(grid_state={"selectedRows": []})
    result = AgGridResult(component_result=component, original_data=None)
    assert result.selected_rows is None


def test_named_state_accessors():
    component = _component_result(
        grid_state={
            "columnState": [{"colId": "a"}],
            "filterModel": {"a": {"type": "equals"}},
            "sortModel": [{"colId": "a", "sort": "asc"}],
            "state": {"rowGroup": {"groupColIds": ["a"]}},
            "displayedRowCount": 7,
            "eventName": "filterChanged",
            "eventData": {"source": "ui"},
        }
    )
    result = AgGridResult(component_result=component, original_data=None)
    assert result.column_state == [{"colId": "a"}]
    assert result.filter_model == {"a": {"type": "equals"}}
    assert result.sort_model == [{"colId": "a", "sort": "asc"}]
    assert result.grid_state == {"rowGroup": {"groupColIds": ["a"]}}
    assert result.displayed_row_count == 7
    assert result.event_name == "filterChanged"
    assert result.event_data == {"source": "ui"}


def test_api_response_and_notes_pass_through():
    component = _component_result(
        api_response={"call_id": "x", "value": 1},
        notes={"token": 3, "notes": {"0": {"a": "hi"}}},
    )
    result = AgGridResult(component_result=component, original_data=None)
    assert result.api_response == {"call_id": "x", "value": 1}
    assert result.notes["token"] == 3


def test_get_and_getitem():
    component = _component_result(grid_state={"displayedRowCount": 3})
    result = AgGridResult(component_result=component, original_data=None)
    assert result.get("displayedRowCount") == 3
    assert result.get("missing", "fallback") == "fallback"
    assert result["displayedRowCount"] == 3

    try:
        result["missing"]
    except KeyError:
        pass
    else:
        raise AssertionError("expected KeyError for a missing key")
