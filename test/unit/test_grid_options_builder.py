"""GridOptionsBuilder derives colDefs from a DataFrame and merges overrides."""

import pandas as pd

from st_aggrid.grid_options_builder import GridOptionsBuilder


def test_from_dataframe_creates_one_col_def_per_column():
    df = pd.DataFrame({"names": ["a"], "ages": [1]})
    options = GridOptionsBuilder.from_dataframe(df).build()
    assert [c["field"] for c in options["columnDefs"]] == ["names", "ages"]
    assert [c["headerName"] for c in options["columnDefs"]] == ["names", "ages"]


def test_numeric_columns_get_numeric_types():
    df = pd.DataFrame({"ages": [1], "names": ["a"]})
    options = GridOptionsBuilder.from_dataframe(df).build()
    by_field = {c["field"]: c for c in options["columnDefs"]}
    assert by_field["ages"]["type"] == ["numericColumn", "numberColumnFilter"]
    assert by_field["names"]["type"] == []


def test_datetime_columns_get_date_types():
    df = pd.DataFrame({"when": pd.to_datetime(["2026-01-01"])})
    options = GridOptionsBuilder.from_dataframe(df).build()
    assert options["columnDefs"][0]["type"] == [
        "dateColumnFilter",
        "shortDateTimeFormat",
    ]


def test_from_dataframe_enables_fit_grid_width():
    df = pd.DataFrame({"a": [1]})
    options = GridOptionsBuilder.from_dataframe(df).build()
    assert options["autoSizeStrategy"] == {"type": "fitGridWidth"}


def test_dotted_column_names_suppress_field_dot_notation():
    df = pd.DataFrame({"a.b": [1]})
    options = GridOptionsBuilder.from_dataframe(df).build()
    assert options["suppressFieldDotNotation"] is True


def test_default_column_parameters_are_routed_to_default_col_def():
    df = pd.DataFrame({"a": [1]})
    options = GridOptionsBuilder.from_dataframe(df, filter=True).build()
    assert options["defaultColDef"]["filter"] is True


def test_configure_column_merges_into_an_existing_col_def():
    df = pd.DataFrame({"a": [1]})
    gb = GridOptionsBuilder.from_dataframe(df)
    gb.configure_column("a", header_name="Alpha", width=120)
    options = gb.build()
    assert options["columnDefs"][0]["headerName"] == "Alpha"
    assert options["columnDefs"][0]["width"] == 120


def test_configure_columns_batches_overrides():
    df = pd.DataFrame({"a": [1], "b": [2]})
    gb = GridOptionsBuilder.from_dataframe(df)
    gb.configure_columns(["a", "b"], resizable=False)
    options = gb.build()
    assert all(c["resizable"] is False for c in options["columnDefs"])


def test_configure_auto_height_sets_dom_layout():
    df = pd.DataFrame({"a": [1]})
    gb = GridOptionsBuilder.from_dataframe(df)
    gb.configure_auto_height(True)
    assert gb.build()["domLayout"] == "autoHeight"


def test_build_turns_col_defs_into_a_list():
    df = pd.DataFrame({"a": [1]})
    options = GridOptionsBuilder.from_dataframe(df).build()
    assert isinstance(options["columnDefs"], list)
