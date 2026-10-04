"""Validation and transport for the built-in `stRollup` aggregator.

Every rule here exists because the failure it prevents is silent in the
browser: a totals table whose keys never meet the grid's group keys renders
as a grid of empty group cells, indistinguishable from "no total applies".

Pure Python — no browser, no Streamlit runtime.
"""

import datetime as dt

import pandas as pd
import pytest

from st_aggrid.rollup import DEFAULT_FLAG_PREFIX, prepare_rollup


def grid_options(*columns):
    return {"columnDefs": list(columns) or [{"field": "dau", "aggFunc": "stRollup"}]}


def leaves():
    return pd.DataFrame(
        {
            "event_date": [dt.date(2026, 10, 1), dt.date(2026, 10, 1)],
            "app_version": ["1.19.1", None],
            "dau": [10, 20],
        }
    )


def cube():
    """The whole CUBE answer over (event_date, app_version)."""
    d = dt.date(2026, 10, 1)
    return pd.DataFrame(
        {
            "event_date": [d, d, d, None, None, None],
            "app_version": ["1.19.1", None, None, "1.19.1", None, None],
            "dau": [10, 20, 25, 10, 20, 25],
            "_grouping_event_date": [0, 0, 0, 1, 1, 1],
            "_grouping_app_version": [0, 0, 1, 0, 0, 1],
        }
    )


def rollup(**overrides):
    spec = {"data": cube(), "dimensions": ["event_date", "app_version"]}
    spec.update(overrides)
    return spec


def run(spec=None, options=None, dtypes="leaves", leaves_as_json=False):
    if isinstance(dtypes, str) and dtypes == "leaves":
        dtypes = leaves().dtypes
    return prepare_rollup(
        spec, options if options is not None else grid_options(), dtypes, leaves_as_json
    )


# --- rule 1: declaration and table come together --------------------------


def test_no_rollup_and_no_strollup_column_is_a_no_op():
    assert run(None, {"columnDefs": [{"field": "dau", "aggFunc": "sum"}]}) == (None, None)


def test_a_strollup_column_without_a_table_is_rejected():
    with pytest.raises(ValueError, match="rollup="):
        run(None)


def test_a_table_without_a_strollup_column_is_rejected():
    with pytest.raises(ValueError, match="no column declares"):
        run(rollup(), {"columnDefs": [{"field": "dau", "aggFunc": "sum"}]})


def test_a_strollup_column_inside_a_column_group_is_found():
    options = {"columnDefs": [{"headerName": "g", "children": [{"field": "dau", "aggFunc": "stRollup"}]}]}
    payload, meta = run(rollup(), options)
    assert meta["dimensions"] == ["event_date", "app_version"]


# --- rule 2: shape ---------------------------------------------------------


@pytest.mark.parametrize(
    "spec, message",
    [
        ("not a dict", "must be a dict"),
        ({"data": cube()}, "dimensions"),
        ({"data": cube(), "dimensions": []}, "dimensions"),
        ({"data": cube(), "dimensions": ["event_date", "event_date"]}, "more than once"),
        ({"data": cube(), "dimensions": ["event_date"], "flags": {"app_version": "x"}}, "not a dimension"),
        ({"data": cube(), "dimensions": ["event_date"], "flags": {"event_date": 3}}, "flags"),
        ({"data": cube(), "dimensions": ["event_date"], "extra": 1}, "unknown key"),
        ({"data": [1, 2], "dimensions": ["event_date"]}, "DataFrame"),
    ],
)
def test_a_malformed_rollup_is_rejected(spec, message):
    with pytest.raises(ValueError, match=message):
        run(spec)


def test_flags_default_to_the_grouping_prefix():
    _, meta = run(rollup(flags={"event_date": "_grouping_event_date"}))
    assert meta["flags"] == {
        "event_date": "_grouping_event_date",
        "app_version": f"{DEFAULT_FLAG_PREFIX}app_version",
    }


# --- rule 3: dimensions and flags exist; flags are 0/1 ---------------------


def test_a_dimension_missing_from_the_totals_is_rejected():
    with pytest.raises(ValueError, match="not columns of rollup"):
        run(rollup(data=cube().drop(columns=["app_version"])))


def test_a_dimension_missing_from_the_row_data_is_rejected():
    with pytest.raises(ValueError, match="not columns of the row data"):
        run(rollup(), dtypes=leaves().drop(columns=["app_version"]).dtypes)


def test_a_missing_flag_column_is_rejected():
    with pytest.raises(ValueError, match="_grouping_app_version"):
        run(rollup(data=cube().drop(columns=["_grouping_app_version"])))


@pytest.mark.parametrize("bad", [2, None, -1])
def test_a_flag_that_is_not_zero_or_one_is_rejected(bad):
    data = cube()
    data["_grouping_app_version"] = data["_grouping_app_version"].astype(object)
    data.loc[0, "_grouping_app_version"] = bad
    with pytest.raises(ValueError, match="0 or 1"):
        run(rollup(data=data))


# --- rule 4: the value field exists ----------------------------------------


def test_a_value_field_missing_from_the_totals_is_rejected():
    with pytest.raises(ValueError, match="'users'"):
        run(rollup(), grid_options({"field": "users", "aggFunc": "stRollup"}))


def test_context_field_overrides_the_coldef_field():
    options = grid_options(
        {"field": "users", "aggFunc": "stRollup", "context": {"stRollup": {"field": "dau"}}}
    )
    assert run(rollup(), options)[1] is not None


def test_a_strollup_column_with_no_field_at_all_is_rejected():
    with pytest.raises(ValueError, match="needs a 'field'"):
        run(rollup(), grid_options({"colId": "x", "aggFunc": "stRollup"}))


def test_a_malformed_context_declaration_is_rejected():
    with pytest.raises(ValueError, match="context\\['stRollup'\\]"):
        run(rollup(), grid_options({"field": "dau", "aggFunc": "stRollup", "context": {"stRollup": "dau"}}))


# --- rule 5: dimension dtypes agree ----------------------------------------


def test_a_dimension_dtype_mismatch_is_rejected():
    data = cube()
    data["event_date"] = pd.to_datetime(data["event_date"])
    with pytest.raises(ValueError, match="dtype"):
        run(rollup(data=data))


def test_datetime64_on_both_sides_is_accepted():
    """Both frames go through `prepare_frame`, so both become ISO strings."""
    data = cube()
    data["event_date"] = pd.to_datetime(data["event_date"])
    rows = leaves()
    rows["event_date"] = pd.to_datetime(rows["event_date"])
    from st_aggrid.aggrid_utils import prepare_frame

    payload, _ = run(rollup(data=data), dtypes=prepare_frame(rows).dtypes)
    assert payload["event_date"].iloc[0] == "2026-10-01T00:00:00"


def test_without_row_data_the_leaf_checks_are_skipped():
    data = cube()
    data["event_date"] = pd.to_datetime(data["event_date"])
    assert run(rollup(data=data), dtypes=None)[1] is not None


def test_numeric_dtype_mismatch_int64_to_float64_is_accepted():
    """Rolled-up rows convert int64 to float64 (NaN for missing), same key in AG-Grid."""
    # Create numeric CUBE: two dimensions (count is int64 in leaves, float64 in totals with NaN)
    data = pd.DataFrame(
        {
            "count": [1.0, 2.0, 1.0, 2.0, None, None],  # float64 (NaN for rolled-up)
            "type": ["a", "a", "b", "b", "a", "b"],  # string stays string
            "value": [10, 20, 30, 40, 50, 60],
            "_grouping_count": [0, 0, 0, 0, 1, 1],
            "_grouping_type": [0, 0, 0, 0, 0, 0],
        }
    )
    rows = pd.DataFrame({"count": [1, 2, 1, 2], "type": ["a", "a", "b", "b"], "value": [10, 20, 30, 40]})
    rows["count"] = rows["count"].astype("int64")
    options = {"columnDefs": [{"field": "value", "aggFunc": "stRollup"}]}
    assert run(rollup(data=data, dimensions=["count", "type"]), options, dtypes=rows.dtypes)[1] is not None


def test_numeric_dtype_mismatch_int64_to_nullable_int64_is_accepted():
    """Both render to the same key despite different dtypes."""
    data = pd.DataFrame(
        {
            "count": pd.array([1, 2, 1, 2, None, None], dtype="Int64"),  # nullable int
            "type": ["a", "a", "b", "b", "a", "b"],
            "value": [10, 20, 30, 40, 50, 60],
            "_grouping_count": [0, 0, 0, 0, 1, 1],
            "_grouping_type": [0, 0, 0, 0, 0, 0],
        }
    )
    rows = pd.DataFrame({"count": [1, 2, 1, 2], "type": ["a", "a", "b", "b"], "value": [10, 20, 30, 40]})
    rows["count"] = rows["count"].astype("int64")
    options = {"columnDefs": [{"field": "value", "aggFunc": "stRollup"}]}
    assert run(rollup(data=data, dimensions=["count", "type"]), options, dtypes=rows.dtypes)[1] is not None


def test_numeric_dtype_mismatch_int64_to_string_is_rejected():
    """Non-numeric mismatch still raises."""
    data = pd.DataFrame(
        {
            "count": ["1", "2", "3", "1", "2", "3"],  # string, not numeric
            "value": [10, 20, 30, 40, 50, 60],
            "_grouping_count": [0, 0, 0, 1, 1, 1],
        }
    )
    rows = pd.DataFrame({"count": [1, 2, 3], "value": [10, 20, 30]})
    rows["count"] = rows["count"].astype("int64")
    options = {"columnDefs": [{"field": "value", "aggFunc": "stRollup"}]}
    with pytest.raises(ValueError, match="dtype"):
        run(rollup(data=data, dimensions=["count"]), options, dtypes=rows.dtypes)


def test_bool_dtype_mismatch_bool_to_int64_is_rejected():
    """Bool is not a compatible numeric type."""
    data = pd.DataFrame(
        {
            "flag": [True, False, True, None, None, None],
            "value": [1, 2, 3, 4, 5, 6],
            "_grouping_flag": [0, 0, 0, 1, 1, 1],
        }
    )
    rows = pd.DataFrame({"flag": [True, False], "value": [1, 2]})
    rows["flag"] = rows["flag"].astype("int64")
    options = {"columnDefs": [{"field": "value", "aggFunc": "stRollup"}]}
    with pytest.raises(ValueError, match="dtype"):
        run(rollup(data=data, dimensions=["flag"]), options, dtypes=rows.dtypes)


# --- rule 6: unique keys after normalisation -------------------------------


def test_a_duplicated_grouping_set_is_rejected():
    data = pd.concat([cube(), cube().iloc[[2]]])
    with pytest.raises(ValueError, match="share the key"):
        run(rollup(data=data))


def test_null_and_empty_string_collide_as_the_grid_groups_them():
    data = cube()
    data.loc[0, "app_version"] = ""  # (date, "") now collides with (date, None)
    with pytest.raises(ValueError, match="share the key"):
        run(rollup(data=data))


def test_an_integer_and_its_string_collide():
    """AG-Grid groups the number 7 under "7"."""
    data = pd.DataFrame(
        {"build": [7, "7"], "dau": [1, 2], "_grouping_build": [0, 0]}, dtype=object
    )
    with pytest.raises(ValueError, match="share the key"):
        run({"data": data, "dimensions": ["build"]}, dtypes=None)


def test_rolled_up_values_do_not_enter_the_key():
    """Rows 3-5 carry event_date None only because it is rolled up."""
    assert run(rollup())[1] is not None


# --- transport -------------------------------------------------------------


def test_arrow_transport_returns_the_prepared_frame():
    payload, _ = run(rollup())
    assert isinstance(payload, pd.DataFrame)
    assert list(payload.columns) == list(cube().columns)


def test_json_transport_matches_the_leaves_to_json_call():
    payload, _ = run(rollup(), leaves_as_json=True)
    assert isinstance(payload, str)
    assert payload == cube().to_json(orient="records", default_handler=str)


def test_the_callers_totals_frame_is_not_mutated():
    data = cube()
    data["event_date"] = pd.to_datetime(data["event_date"])
    before = data.copy()
    rows = leaves()
    rows["event_date"] = pd.to_datetime(rows["event_date"])
    from st_aggrid.aggrid_utils import prepare_frame

    run(rollup(data=data), dtypes=prepare_frame(rows).dtypes)
    pd.testing.assert_frame_equal(data, before)


def test_a_polars_totals_frame_is_accepted():
    pl = pytest.importorskip("polars")
    payload, _ = run(rollup(data=pl.from_pandas(cube())), dtypes=None)
    assert isinstance(payload, pd.DataFrame)
