import sys
from pathlib import Path


cwd = Path().resolve()

sys.path.append(cwd.parent.as_posix())

import streamlit as st
import numpy as np
import pandas as pd

from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode

@st.fragment
def show_specs(dct):
    btn = st.button("Show specs")
    if btn:
        # st.write(dct.data)
        st.write(st.session_state.ag_columns_state)
        st.write(st.session_state.ag_grid_state)
        st.write(st.session_state.ag_selected_rows)


@st.cache_data()
def get_data():
    df = pd.DataFrame(
        np.random.randint(0, 100, 50).reshape(-1, 5), columns= list("abcde")
    )
    df['dimension'] = np.random.choice(['A', 'B', 'C'], 10)
    df['dimension2'] = np.random.choice(['X_2', 'Y_2', 'Z_2', 'X_1', 'Y_1', 'Z_1'], 10)
    df['dates'] = pd.date_range('2020-01-01', periods=10, freq='D')
    df['dates'] = df['dates'].apply(lambda x: x.strftime('%Y-%m-%d'))

    return df


def show_grid():
    data = get_data()
    gb = GridOptionsBuilder.from_dataframe(data)
    gb.configure_side_bar(defaultToolPanel='', filters_panel=True)
    # make all numeric columns editable
    gb.configure_columns(list('abcde'), editable=True, enableValue=True)
    gb.configure_column('dates', editable=False, enableRowGroup=True, hide=False)
    gb.configure_column('dimension', editable=False, enableRowGroup=True, hide=False)
    gb.configure_column('dimension2', editable=False, enableRowGroup=True, enablePivot=True, hide=False)

    # Create a calculated column that updates when data is edited. Use agAnimateShowChangeCellRenderer to show changes
    # gb.configure_column('row total', valueGetter='Number(data.a) + Number(data.b) + Number(data.c) + Number(data.d) + Number(data.e)', cellRenderer='agAnimateShowChangeCellRenderer', editable='false', type=['numericColumn'])

    options = {"rowSelection": "multiple", "rowMultiSelectWithClick": "true", "animateRows": "true", "enableRangeSelection": "true"}
    gb.configure_grid_options(**options)
    grid_options = gb.build()

    # Setting a fixed key for the component will prevent the grid to reinitialize when dataframe parameter change, simulated here
    # by pressing the button on the side bar.
    # Data will only be refreshed when the parameter reload_data is set to True

    if use_fixed_key:
        grid = AgGrid(
            data,
            gridOptions=grid_options,
            height=height,
            fit_columns_on_grid_load=True,
            key='an_unique_key',
            reload_data=reload_data,
            update_mode=GridUpdateMode.GRID_CHANGED,
            try_to_convert_back_to_original_types=False
        )
    else:
        grid = AgGrid(
            data,
            gridOptions=grid_options,
            height=height,
            enable_enterprise_modules=True,
            fit_columns_on_grid_load=True,
            update_mode=GridUpdateMode.GRID_CHANGED,
            try_to_convert_back_to_original_types=False
        )

    # st.write(grid.selected_rows_id)
    # st.write(grid.data_groups)
    return grid



st.subheader("Controling Ag-Grid redraw in Streamlit.")
st.markdown("""
The grid will redraw itself and reload the data whenever the key of the component changes.  
If ```key=None``` or not set at all, streamlit will compute a hash from AgGrid() parameters to use as a unique key.  
This can be simulated by changing the grid height, for instance, with the slider:
""")

c1,_ = st.columns([3,2])

height = c1.slider('Height (px)', min_value=100, max_value=800, value=400)

st.markdown("""
As there is no key parameter set, whenever the height parameter changes grid is redrawn.  
This behavior can be prevented by setting a fixed key on aggrid call (check the box below):  
""")

use_fixed_key = st.checkbox("Use fixed key in AgGrid call", value=False)
if use_fixed_key:
    key="'an_unique_key'"
else:
    key=None

st.markdown(f"""
However, blocking redraw, also blocks grid from rendering new data, unless the ```reload_data```  parameter is set to true.  
(note that grid return value shows new data, however as redraw is blocked grid does not show the new values)
""")
reload_data=False
c1,c2,_ = st.columns([1,2,1])
button = c1.button("Generate 10 new random lines of data")
reload_data_option = c2.checkbox("Set reload_data as true on next app refresh.", value=False)

if button:
    st.cache_data.clear()

    if reload_data_option:
        reload_data=True




key_md = ", key=None" if not key else f",key={key}"
st.markdown(f"""
Grid call below is:
```python
AgGrid(data, grid_options, {key_md}, reload_data={reload_data}, height={height})
```""")

ag = show_grid()

st.subheader("Grid Options")
show_specs(ag)
