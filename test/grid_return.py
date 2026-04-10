import json

import pandas as pd
import streamlit as st

from st_aggrid import AgGrid


TESTS = st.radio(
    "Select Test",
    options=range(1, 5),
)

"""grid launches with json data and grid options"""

data = json.dumps(
    [
        {"name": "alice", "age": 25},
        {"name": "bob", "age": 30},
        {"name": "charlie", "age": 35},
        {"name": "diana", "age": 28},
        {"name": "eve", "age": 32},
        {"name": "frank", "age": 27},
        {"name": "grace", "age": 29},
        {"name": "henry", "age": 33},
        {"name": "iris", "age": 26},
        {"name": "jack", "age": 31},
    ]
)


def _selected_rows_text(r):
    sel = r.selected_rows
    if sel is None or len(sel) == 0:
        return "No rows selected"
    return sel.to_string()


def make_grid():
    go = {
        "columnDefs": [
            {
                "headerName": "First Name",
                "field": "name",
                "type": [],
            },
            {
                "headerName": "ages",
                "field": "age",
                "type": ["numericColumn", "numberColumnFilter"],
            },
        ],
        "autoSizeStrategy": {"type": "fitCellContents", "skipHeader": False},
        "rowSelection": {"mode": "multiRow", "checkboxes": True},
    }
    r = AgGrid(
        data,
        go,
        collect=["getSelectedRows"],
        update_on=["selectionChanged", "sortChanged"],
        key="event_return_grid",
    )

    st.html(
        f"""
    <span>
    <h1> Returned Grid Data </h1>
    <pre data-testid='returned-grid-data'>{r.data.to_string() if r.data is not None else ''}</pre>
    </span>
    """
    )

    st.html(
        f"""
    <span>
    <h1> Event Return Data </h1>
    <pre data-testid='event-return-data'>event={r.event_name} data={r.event_data}</pre>
    </span>
    """
    )

    st.html(
        f"""
    <span>
    <h1> Selected Data </h1>
    <pre data-testid='selected-data'>{_selected_rows_text(r)}</pre>
    </span>
    """
    )

    st.html(
        f"""
    <span>
    <h1> Full Grid Response </h1>
    <pre data-testid='full-grid-response'>event={r.event_name} state_keys={list(r._grid_state.keys()) if r._grid_state else []}</pre>
    </span>
    """
    )


@st.cache_resource
def get_dummy_data():
    dummy_data = []
    for i in range(300_00):
        row = {
            "employee_id": f"EMP{i + 1:03d}",
            "first_name": f"FirstName{i + 1}",
            "last_name": f"LastName{i + 1}",
            "email": f"user{i + 1}@company.com",
        }
        dummy_data.append(row)
    return json.dumps(dummy_data)


def make_grid2():
    """v2 equivalent of the v1 "custom return" test — track column state
    via getColumnState() auto-collect on columnMoved events."""
    data2 = get_dummy_data()
    go = {
        "columnDefs": [
            {"field": "employee_id"},
            {"field": "first_name"},
            {"field": "last_name"},
            {"field": "email"},
        ],
        "rowSelection": {"mode": "singleRow"},
    }
    r = AgGrid(
        data2,
        go,
        collect=["getColumnState"],
        update_on=["columnMoved", "sortChanged"],
        key="custom_event_return_grid",
    )

    column_state = r.column_state
    if column_state is not None:
        column_order = [c.get("colId") for c in column_state]
    else:
        column_order = None

    st.html(
        f"""
    <span>
    <h1> Column Order (only column names) </h1>
    <pre data-testid='custom-grid-return-data'>{column_order}</pre>
    </span>
    """
    )


def make_grid3():
    """Grouped data test — Enterprise row grouping with selection."""
    import pathlib

    data_file = str(
        pathlib.Path(__file__).parent.joinpath("olympic-winners.json").absolute()
    )
    go = {
        "columnDefs": [
            {"field": "sport", "rowGroup": True},
            {"field": "athlete", "rowGroup": True},
            {"field": "age", "checkboxSelection": True, "headerCheckboxSelection": True},
        ],
        "defaultColDef": {"width": 150, "cellStyle": {"fontWeight": "bold"}},
        "groupDisplayType": "groupRows",
        "autoGroupColumnDef": {
            "headerName": "Sport",
            "field": "sport",
            "cellRenderer": "agGroupCellRenderer",
            "checkboxSelection": True,
        },
        "rowSelection": {"mode": "multiRow", "groupSelects": "descendants"},
    }
    r = AgGrid(
        data_file,
        go,
        collect=["getSelectedRows", "getFilterModel"],
        update_on=["gridReady", "rowGroupOpened", "sortChanged", "selectionChanged"],
        key="grouped_data_grid",
        enable_enterprise_modules=True,
    )

    # Stub out v1-only "dataGroups" concept — not supported in v2, kept for
    # test stability. Tests should be scoped to v2-supported state below.
    st.html(
        """
    <span>
    <h1> Grouped Data Groups (placeholder) </h1>
    <pre data-testid='grouped-data-groups'></pre>
    </span>
    """
    )

    st.html(
        f"""
    <span>
    <h1> Grouped Grid Response </h1>
    <pre data-testid='grouped-grid-response'>event={r.event_name} event_data={r.event_data}</pre>
    </span>
    """
    )

    st.html(
        f"""
    <span>
    <h1> Grouped Grid Selected Data </h1>
    <pre data-testid='grouped-selected-data'>{_selected_rows_text(r)}</pre>
    </span>
    """
    )

    selection_count = 0 if r.selected_rows is None else len(r.selected_rows)
    st.html(
        f"""
    <span>
    <h1> Grouped Grid Selection Count </h1>
    <pre data-testid='grouped-selection-count'>{selection_count}</pre>
    </span>
    """
    )

    st.html(
        """
    <span>
    <h1> Selected Grouped Data Groups (placeholder) </h1>
    <pre data-testid='selected-grouped-data-groups'></pre>
    </span>
    """
    )


def make_grid4():
    """Comprehensive selection + pagination."""
    selection_data = pd.DataFrame(
        {
            "id": range(1, 21),
            "name": [f"User{i}" for i in range(1, 21)],
            "category": ["A", "B", "C", "D", "E"] * 4,
            "value": [i * 10 for i in range(1, 21)],
            "active": [i % 2 == 0 for i in range(1, 21)],
        }
    )

    go = {
        "columnDefs": [
            {"headerName": "ID", "field": "id", "width": 80},
            {"headerName": "Name", "field": "name", "width": 100},
            {"headerName": "Category", "field": "category", "width": 100},
            {"headerName": "Value", "field": "value", "width": 100},
            {"headerName": "Active", "field": "active", "width": 100},
        ],
        "autoSizeStrategy": {"type": "fitGridWidth"},
        # AG-Grid 34.x auto-adds a selection column when checkboxes=True.
        "rowSelection": {"mode": "multiRow", "checkboxes": True},
        "pagination": True,
        "paginationPageSize": 10,
    }

    r = AgGrid(
        selection_data,
        go,
        collect=["getSelectedRows"],
        update_on=["selectionChanged"],
        key="selection_test_grid",
    )

    st.html(
        f"""
    <span>
    <h1> Selection Test Grid Data </h1>
    <pre data-testid='selection-grid-data'>{r.data.to_string() if r.data is not None else ''}</pre>
    </span>
    """
    )

    st.html(
        f"""
    <span>
    <h1> Selected Rows </h1>
    <pre data-testid='selected-rows-data'>{_selected_rows_text(r)}</pre>
    </span>
    """
    )

    st.html(
        f"""
    <span>
    <h1> Selection Event Data </h1>
    <pre data-testid='selection-event-data'>event={r.event_name}</pre>
    </span>
    """
    )

    selection_count = 0 if r.selected_rows is None else len(r.selected_rows)
    st.html(
        f"""
    <span>
    <h1> Selection Count </h1>
    <pre data-testid='selection-count'>{selection_count}</pre>
    </span>
    """
    )


if TESTS == 1:
    make_grid()

if TESTS == 2:
    make_grid2()

if TESTS == 3:
    make_grid3()

if TESTS == 4:
    make_grid4()
