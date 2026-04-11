import json
import os
from collections.abc import Mapping
from io import StringIO
from pathlib import Path

import pandas as pd

from st_aggrid.grid_options_builder import GridOptionsBuilder
from st_aggrid.shared import JsCode, walk_grid_options


def _dataframe_arrow_compatible(df: "pd.DataFrame") -> bool:
    """Return True if the DataFrame can be round-tripped through Arrow.

    Streamlit CCv2 serializes DataFrames via Apache Arrow. Columns holding
    lists/sets with heterogeneous item types (e.g. ``[1, "a", True]``) fail
    Arrow conversion and leave the frontend with ``undefined`` gridOptions.
    """
    try:
        import pyarrow as pa
    except Exception:
        return True
    try:
        pa.Table.from_pandas(df, preserve_index=False)
        return True
    except Exception:
        return False


def _parse_data_and_grid_options(
    data,
    grid_options,
    default_column_parameters,
    unsafe_allow_jscode,
    use_json_serialization="auto",
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

        # Compute column types before adding ID column
        column_types = data.dtypes

    # Resolve grid_options independently of data — it may be a Mapping, a JSON
    # string, or a path to a .json file. Do this unconditionally so callers can
    # combine any data source with any grid_options source.
    if isinstance(grid_options, (str, Path)):
        if isinstance(grid_options, Path):
            grid_options = Path(grid_options).resolve().absolute()
        # If grid_options is a path to a json file
        if str(grid_options).endswith(".json") and os.path.exists(str(grid_options)):
            try:
                with open(os.path.abspath(str(grid_options))) as f:
                    grid_options = json.load(f)
            except Exception as ex:
                raise Exception(f"Error reading {grid_options}. {ex}")
        else:
            # Otherwise treat it as a raw JSON string
            try:
                grid_options = json.loads(grid_options)
            except Exception:
                raise Exception("Error parsing grid_options parameter as raw json.")

    # If there is data and no grid options, build defaults from the DataFrame
    if isinstance(data, pd.DataFrame) and not grid_options:
        gb = GridOptionsBuilder.from_dataframe(data, **default_column_parameters)
        grid_options = gb.build()

    # If rowId is not defined, create a unique row_id
    if (
        isinstance(grid_options, Mapping)
        and "getRowId" not in grid_options
        and isinstance(data, pd.DataFrame)
    ):
        data["::auto_unique_id::"] = list(map(str, range(data.shape[0])))

    # Optionally serialize rowData as a JSON string to bypass Arrow limits
    # (e.g. cells with heterogeneous lists or sets). The frontend's parseData
    # fall-back in parsers.ts handles gridOptions.rowData as a JSON string.
    if isinstance(data, pd.DataFrame) and grid_options is not None:
        should_json_serialize = False
        if use_json_serialization is True:
            should_json_serialize = True
        elif use_json_serialization == "auto":
            should_json_serialize = not _dataframe_arrow_compatible(data)

        if should_json_serialize:
            grid_options["rowData"] = data.to_json(
                orient="records", default_handler=str
            )
            data = None

    # Process JsCode objects
    if unsafe_allow_jscode and grid_options:
        walk_grid_options(
            grid_options, lambda v: v.js_code if isinstance(v, JsCode) else v
        )

    return data, grid_options, column_types
