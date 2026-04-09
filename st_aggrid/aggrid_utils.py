import os
import json
import pandas as pd

from typing import Any, Mapping, Tuple
from st_aggrid.grid_options_builder import GridOptionsBuilder
from st_aggrid.shared import JsCode, walk_gridOptions
from io import StringIO
from pathlib import Path


def _parse_data_and_grid_options(
    data, grid_options, default_column_parameters, unsafe_allow_jscode
):
    column_types = None

    if data is not None:

        if isinstance(data, (str, Path)):
            if isinstance(data, Path):
                data = Path(data).resolve().absolute()

            # If data is a path to a json file, validate and load it as string
            if str(data).endswith(".json") and os.path.exists(str(data)):
                try:
                    with open(os.path.abspath(str(data))) as f:
                        data = json.dumps(json.load(f))
                except Exception as ex:
                    raise Exception(f"Error reading {data}. {ex}")

            # If data is a json string, load it as a DataFrame
            try:
                data = pd.read_json(StringIO(data))
            except Exception:
                raise Exception("Error parsing data parameter as raw json.")

        # Handle Polars DataFrames without adding dependency
        if (
            hasattr(data, "__class__")
            and data.__class__.__module__
            and "polars" in data.__class__.__module__
            and data.__class__.__name__ == "DataFrame"
        ):
            data = data.to_pandas(use_pyarrow_extension_array=False)

        if isinstance(data, pd.DataFrame):
            # Convert date columns to ISO format
            for c, d in data.dtypes.items():
                if d.kind == "M":
                    data[c] = data[c].apply(lambda s: s.isoformat())

        # If there is data and no grid options, create grid options from the data
        if (data is not None) and (not grid_options):
            gb = GridOptionsBuilder.from_dataframe(data, **default_column_parameters)
            grid_options = gb.build()

        # Compute column types before adding ID column
        column_types = data.dtypes

    # If grid_options is supplied as a dictionary, use it as-is
    elif isinstance(grid_options, Mapping):
        grid_options = grid_options

    elif isinstance(grid_options, (str, Path)):
        if isinstance(grid_options, Path):
            grid_options = Path(grid_options).resolve().absolute()
        # If grid_options is a path to a json file
        if str(grid_options).endswith(".json") and os.path.exists(str(grid_options)):
            try:
                with open(os.path.abspath(str(grid_options))) as f:
                    grid_options = json.dumps(json.load(f))
            except Exception as ex:
                raise Exception(f"Error reading {grid_options}. {ex}")

        # If grid_options is a json string, parse it
        try:
            grid_options = json.loads(grid_options)
        except Exception:
            raise Exception("Error parsing grid_options parameter as raw json.")

    # If rowId is not defined, create a unique row_id
    if grid_options and "getRowId" not in grid_options and data is not None:
        data["::auto_unique_id::"] = list(map(str, range(data.shape[0])))

    # Process JsCode objects
    if unsafe_allow_jscode and grid_options:
        walk_gridOptions(
            grid_options, lambda v: v.js_code if isinstance(v, JsCode) else v
        )

    return data, grid_options, column_types
