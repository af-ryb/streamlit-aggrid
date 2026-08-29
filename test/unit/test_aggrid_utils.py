"""_parse_data_and_grid_options turns user input into the component payload."""

import json

import pandas as pd

from st_aggrid.aggrid_utils import _parse_data_and_grid_options
from st_aggrid.shared import JsCode


def _parse(data, grid_options=None, **kwargs):
    kwargs.setdefault("default_column_parameters", {})
    kwargs.setdefault("unsafe_allow_jscode", False)
    return _parse_data_and_grid_options(
        data,
        grid_options,
        kwargs["default_column_parameters"],
        kwargs["unsafe_allow_jscode"],
        use_json_serialization=kwargs.get("use_json_serialization", "auto"),
    )


def test_grid_options_are_derived_from_the_dataframe():
    df = pd.DataFrame({"names": ["a"], "ages": [1]})
    _data, grid_options, _types = _parse(df)
    fields = [c["field"] for c in grid_options["columnDefs"]]
    assert fields == ["names", "ages"]


def test_an_auto_row_id_column_is_added_when_get_row_id_is_absent():
    df = pd.DataFrame({"a": [1, 2, 3]})
    data, _grid_options, _types = _parse(df)
    assert data["::auto_unique_id::"].tolist() == ["0", "1", "2"]


def test_a_user_supplied_get_row_id_suppresses_the_auto_column():
    df = pd.DataFrame({"a": [1, 2]})
    data, _grid_options, _types = _parse(df, {"getRowId": "someJs"})
    assert "::auto_unique_id::" not in data.columns


def test_a_json_string_is_parsed_into_a_dataframe():
    payload = json.dumps([{"a": 1, "b": "x"}, {"a": 2, "b": "y"}])
    data, _grid_options, _types = _parse(payload)
    assert list(data["a"]) == [1, 2]


def test_grid_options_may_be_a_json_string():
    df = pd.DataFrame({"a": [1]})
    _data, grid_options, _types = _parse(
        df, json.dumps({"columnDefs": [{"field": "a", "headerName": "A"}]})
    )
    assert grid_options["columnDefs"][0]["headerName"] == "A"


def test_jscode_is_converted_only_when_unsafe_jscode_is_allowed():
    df = pd.DataFrame({"a": [1]})
    code = JsCode("function(){ return 1 }")

    _d, converted, _t = _parse(
        df, {"getRowId": code}, unsafe_allow_jscode=True
    )
    assert converted["getRowId"] == code.js_code

    _d, untouched, _t = _parse(
        df, {"getRowId": JsCode("function(){ return 1 }")}, unsafe_allow_jscode=False
    )
    assert isinstance(untouched["getRowId"], JsCode)


def test_dict_cells_fall_back_to_json_row_data():
    # Arrow unifies dict columns into one struct type, which flattens
    # per-row keys. JSON serialization keeps each row's shape.
    df = pd.DataFrame({"payload": [{"a": 1}, {"b": 2}]})
    data, grid_options, _types = _parse(df)
    assert data is None
    assert isinstance(grid_options["rowData"], str)
    assert json.loads(grid_options["rowData"])[1]["payload"] == {"b": 2}


def test_column_types_are_reported():
    df = pd.DataFrame({"a": [1], "b": ["x"]})
    _data, _grid_options, column_types = _parse(df)
    assert column_types["a"].kind == "i"
    assert column_types["b"].kind == "O"
