"""What `AgGrid(rollup=...)` hands the component.

The component is replaced by a recorder, so this runs without a Streamlit
runtime. Pure Python.
"""

import datetime as dt

import pandas as pd
import pytest

from st_aggrid import AgGrid


@pytest.fixture
def sent(monkeypatch):
    captured = {}

    def component(**kwargs):
        captured.update(kwargs["data"])
        return None

    monkeypatch.setattr("st_aggrid.aggrid.get_aggrid_component", lambda: component)
    return captured


def leaves():
    return pd.DataFrame({"day": [dt.date(2026, 10, 1)], "dau": [10]})


def cube():
    return pd.DataFrame(
        {
            "day": [dt.date(2026, 10, 1), None],
            "dau": [10, 12],
            "_grouping_day": [0, 1],
        }
    )


OPTIONS = {"columnDefs": [{"field": "day"}, {"field": "dau", "aggFunc": "stRollup"}]}


def test_arrow_leaves_send_an_arrow_totals_frame(sent):
    AgGrid(leaves(), grid_options=dict(OPTIONS), rollup={"data": cube(), "dimensions": ["day"]})
    assert isinstance(sent["rollup_data"], pd.DataFrame)
    assert sent["rollup_meta"] == {"dimensions": ["day"], "flags": {"day": "_grouping_day"}}


def test_json_leaves_send_json_totals(sent):
    AgGrid(
        leaves(),
        grid_options=dict(OPTIONS),
        rollup={"data": cube(), "dimensions": ["day"]},
        use_json_serialization=True,
    )
    assert isinstance(sent["rollup_data"], str)
    assert sent["rollup_data"] == cube().to_json(orient="records", default_handler=str)


def test_a_grid_without_a_dataframe_sends_json_totals(sent):
    options = dict(OPTIONS, rowData=[{"day": "2026-10-01", "dau": 10}])
    AgGrid(None, grid_options=options, rollup={"data": cube(), "dimensions": ["day"]})
    assert isinstance(sent["rollup_data"], str)


def test_no_rollup_sends_nothing(sent):
    AgGrid(leaves(), grid_options={"columnDefs": [{"field": "day"}, {"field": "dau"}]})
    assert sent["rollup_data"] is None
    assert sent["rollup_meta"] is None


def test_a_strollup_column_without_rollup_raises_before_sending(sent):
    with pytest.raises(ValueError, match="rollup="):
        AgGrid(leaves(), grid_options=dict(OPTIONS))
    assert sent == {}
