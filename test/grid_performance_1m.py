import time

import numpy as np
import pandas as pd
import streamlit as st

from st_aggrid import AgGrid, JsCode


st.set_page_config(page_title="Grid Performance Test - 1M Records", layout="wide")
st.title("AG Grid Performance Test - 1 Million Records")


@st.cache_data
def generate_large_dataset() -> pd.DataFrame:
    """Generate a dataset with 1 million rows for performance testing."""
    np.random.seed(42)
    n_rows = 1_000_000
    data = {
        "id": range(n_rows),
        "name": [f"User_{i}" for i in range(n_rows)],
        "age": np.random.randint(18, 80, n_rows),
        "score": np.random.uniform(0, 100, n_rows),
        "category": np.random.choice(["A", "B", "C", "D"], n_rows),
        "date": pd.date_range("2020-01-01", periods=n_rows, freq="1min"),
        "value": np.random.normal(50, 15, n_rows),
        "active": np.random.choice([True, False], n_rows),
        "department": np.random.choice(
            ["Sales", "Marketing", "Engineering", "HR", "Finance"], n_rows
        ),
        "salary": np.random.randint(30000, 120000, n_rows),
    }
    return pd.DataFrame(data)


st.info(
    "This test measures the time taken for grid initialization and return "
    "operations with 1 million records."
)

with st.spinner("Generating 1 million records..."):
    df = generate_large_dataset()

st.success(f"Generated {len(df):,} records")

grid_options = {
    "columnDefs": [
        {"headerName": "id", "field": "id", "filter": True},
        {"headerName": "name", "field": "name"},
        {"headerName": "age", "field": "age"},
        {"headerName": "score", "field": "score"},
        {"headerName": "category", "field": "category"},
        {"headerName": "date", "field": "date"},
        {"headerName": "value", "field": "value"},
        {"headerName": "active", "field": "active", "type": ["textColumn"]},
        {"headerName": "department", "field": "department"},
        {"headerName": "salary", "field": "salary"},
    ],
    "autoSizeStrategy": {"type": "fitCellContents", "skipHeader": False},
    "defaultColDef": {"resizable": True, "sortable": True},
    "pagination": True,
    "paginationPageSize": 100,
    "getRowId": JsCode("(params) => params.data.id.toString()"),
}


st.subheader("Performance Grid Test")

start_time = time.time()

grid_response = AgGrid(
    df,
    gridOptions=grid_options,
    theme="alpine",
    key="performance_grid_1m",
    collect=["getSelectedRows", "getColumnState"],
    update_on=["selectionChanged", ("columnMoved", 500)],
    allow_unsafe_jscode=True,
    enable_enterprise_modules=True,
)

end_time = time.time()


st.subheader("Performance Metrics")
col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Grid Creation Time", f"{end_time - start_time:.2f}s")
with col2:
    st.metric("Total Records", f"{len(df):,}")
with col3:
    st.metric("Records per Second", f"{len(df) / max(end_time - start_time, 1e-6):,.0f}")


st.subheader("Grid Return Information")
if grid_response is not None and grid_response.data is not None:
    st.write("First 5 rows of returned data:")
    st.dataframe(grid_response.data.head())

    selected = grid_response.selected_rows
    st.write(
        f"Selected rows: {0 if selected is None else len(selected)}"
    )
