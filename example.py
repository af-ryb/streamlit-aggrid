import streamlit as st
import pandas as pd
import numpy as np

from st_aggrid import AgGrid, GridOptionsBuilder, AgGridResult, call_grid_api

st.set_page_config(layout="wide")
st.title("AG-Grid CCv2 Example")

# Sample data
@st.cache_data
def get_data():
    return pd.DataFrame(
        {
            "Name": ["Alice", "Bob", "Charlie", "Diana", "Eve", "Frank"],
            "Age": [25, 30, 35, 28, 32, 45],
            "City": ["New York", "London", "Paris", "Berlin", "Tokyo", "Sydney"],
            "Score": [88.5, 92.3, 76.1, 95.0, 81.7, 69.4],
            "Active": [True, False, True, True, False, True],
        }
    )


df = get_data()

# Configure grid options
gb = GridOptionsBuilder.from_dataframe(df)
gb.configure_selection(selection_mode="multiple", use_checkbox=True)
gb.configure_pagination(enabled=True, auto_page_size=True)
grid_options = gb.build()

# Render grid with auto-collect
result: AgGridResult = AgGrid(
    df,
    grid_options=grid_options,
    height=400,
    collect=["getSelectedRows", "getFilterModel", "getColumnState"],
    update_on=["selectionChanged", "filterChanged", "sortChanged"],
    key="example_grid",
    show_toolbar=True,
    theme="streamlit",
)

# Display auto-collected state
st.subheader("Selected Rows")
if result.selected_rows is not None:
    st.dataframe(result.selected_rows)
else:
    st.write("No rows selected")

col1, col2 = st.columns(2)

with col1:
    st.subheader("Filter Model")
    st.json(result.filter_model or {})

with col2:
    st.subheader("Column State")
    if result.column_state:
        st.json(result.column_state)
    else:
        st.write("No column state yet")

# Explicit API call example
st.subheader("Explicit API Call")
if st.button("Get Displayed Row Count"):
    call_grid_api("example_grid", "getDisplayedRowCount")

if result.api_response:
    st.write(f"API Response: {result.api_response}")

st.subheader("Event Info")
st.write(f"Last event: {result.event_name}")
