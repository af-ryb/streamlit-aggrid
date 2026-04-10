import pandas as pd
import streamlit as st

from st_aggrid import AgGrid, GridOptionsBuilder, JsCode


st.set_page_config(page_title="AG Grid Drag and Drop Example")

data = [
    {"id": "1", "v": 1},
    {"id": "2", "v": 2},
    {"id": "3", "v": 3},
    {"id": "4", "v": 4},
]

df = pd.DataFrame(data)

gb = GridOptionsBuilder.from_dataframe(df)
gb.configure_columns("v", rowDrag=True)
gb.configure_grid_options(
    rowDragManaged=True,
    getRowId=JsCode("params => params.data.id"),
    autoSizeStrategy={"type": "fitGridWidth"},
)

grid_options = gb.build()

r = AgGrid(
    df,
    gridOptions=grid_options,
    enable_enterprise_modules=False,
    height=300,
    key="drag_grid",
    allow_unsafe_jscode=True,
    collect=["getSelectedRows"],
    update_on=["dragStopped"],
)
st.dataframe(r.data)
