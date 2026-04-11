import logging
from collections import defaultdict

from st_aggrid.shared import _get_all_column_props, _get_all_grid_options

logger = logging.getLogger(__name__)


class GridOptionsBuilder:
    """Builder for gridOptions dictionary"""

    def __init__(self):
        def ddict():
            return defaultdict(ddict)

        self._grid_options = ddict()
        self.sideBar: dict = dict()

    @staticmethod
    def from_dataframe(dataframe, **default_column_parameters):
        """
        Creates an instance and initilizes it from a dataframe.
        ColumnDefs are created based on dataframe columns and data types.

        Args:
            dataframe (pd.DataFrame): a pandas DataFrame.

        Returns:
            GridOptionsBuilder: The instance initialized from the dataframe definition.
        """

        if (
            hasattr(dataframe, "__class__")
            and dataframe.__class__.__module__
            and "polars" in dataframe.__class__.__module__
            and dataframe.__class__.__name__ == "DataFrame"
        ):
            dataframe = dataframe.to_pandas(use_pyarrow_extension_array=False)

        # numpy types: 'biufcmMOSUV' https://numpy.org/doc/stable/reference/generated/numpy.dtype.kind.html
        type_mapper = {
            "b": ["textColumn"],
            "i": ["numericColumn", "numberColumnFilter"],
            "u": ["numericColumn", "numberColumnFilter"],
            "f": ["numericColumn", "numberColumnFilter"],
            "c": [],
            "m": ["timedeltaFormat"],
            "M": ["dateColumnFilter", "shortDateTimeFormat"],
            "O": [],
            "S": [],
            "U": [],
            "V": [],
        }

        column_props = {i["name"] for i in _get_all_column_props()}
        grid_options = {i["name"] for i in _get_all_grid_options()}

        gb = GridOptionsBuilder()

        # fetch extra args that should go to DefaultColumns
        for k, v in default_column_parameters.items():
            if k in column_props:
                gb.configure_default_column(**{k: v})
            elif k in grid_options:
                gb.configure_grid_options(**{k: v})
            else:
                logger.warning("%s is not a valid gridOption or columnDef.", k)

        if any("." in col for col in map(str, dataframe.columns)):
            gb.configure_grid_options(suppressFieldDotNotation=True)

        for col_name, col_type in zip(map(str, dataframe.columns), dataframe.dtypes):
            gb.configure_column(field=col_name, type=type_mapper.get(col_type.kind, []))

        gb.configure_grid_options(autoSizeStrategy={"type": "fitGridWidth"})

        return gb

    def configure_default_column(self, **other_default_column_properties):
        """Configure default column.

        Args:
            **other_default_column_properties:
                Key value pairs that will be merged to defaultColDef dict.
                Check ag-grid documentation for available properties.
        """
        self._grid_options["defaultColDef"] = {
            **self._grid_options["defaultColDef"],
            **other_default_column_properties,
        }

    def configure_auto_height(self, enabled: bool = True):
        """Makes grid autoheight.

        Args:
            enabled (bool, optional): enable or disable autoheight. Defaults to True.
        """
        if enabled:
            self.configure_grid_options(domLayout="autoHeight")
        else:
            self.configure_grid_options(domLayout="normal")

    def configure_grid_options(self, **props):
        """Merges props to gridOptions

        Args:
            props (dict): props dicts will be merged to gridOptions root.
        """
        self._grid_options.update(props)

    def configure_columns(self, column_names=None, **props):
        """Batch configures columns. Key-pair values from props dict will be merged
        to colDefs which field property is in column_names list.

        Args:
            column_names (list, optional):
                columns field properties. If any of colDefs matches **props dict is merged.
                Defaults to None.
        """
        column_names = column_names or []
        for k in self._grid_options["columnDefs"]:
            if k in column_names:
                self._grid_options["columnDefs"][k].update(props)

    def configure_column(self, field, header_name=None, **other_column_properties):
        """Configures an individual column
        check https://www.ag-grid.com/javascript-grid-column-properties/ for more information.

        Args:
            field (String): field name, usually equals the column header.
            header_name (String, optional): [description]. Defaults to None.
        """
        if not self._grid_options.get("columnDefs", None):
            self._grid_options["columnDefs"] = defaultdict(dict)

        col_def = {
            "headerName": field if header_name is None else header_name,
            "field": field,
        }

        if other_column_properties:
            col_def = {**col_def, **other_column_properties}

        self._grid_options["columnDefs"][field].update(col_def)

    def configure_side_bar(
        self,
        filters_panel: bool = True,
        columns_panel: bool = True,
        default_tool_panel: str = "",
    ):
        """configures the side panel of ag-grid.
           Side panels are enterprise features, please check www.ag-grid.com

        Args:
            filters_panel (bool, optional):
                Enable filters side panel. Defaults to True.

            columns_panel (bool, optional):
                Enable columns side panel. Defaults to True.

            default_tool_panel (str, optional): The default tool panel that should open when grid renders.
                                                Either "filters" or "columns".
                                                If value is blank, panel will start closed (default)
        """
        filter_panel = {
            "id": "filters",
            "labelDefault": "Filters",
            "labelKey": "filters",
            "iconKey": "filter",
            "toolPanel": "agFiltersToolPanel",
        }

        columns_panel_def = {
            "id": "columns",
            "labelDefault": "Columns",
            "labelKey": "columns",
            "iconKey": "columns",
            "toolPanel": "agColumnsToolPanel",
        }

        if filters_panel or columns_panel:
            side_bar = {"toolPanels": [], "defaultToolPanel": default_tool_panel}

            if filters_panel:
                side_bar["toolPanels"].append(filter_panel)
            if columns_panel:
                side_bar["toolPanels"].append(columns_panel_def)

            self._grid_options["sideBar"] = side_bar

    def configure_selection(
        self,
        selection_mode: str = "single",
        use_checkbox: bool = False,
        header_checkbox: bool = False,
        header_checkbox_filtered_only: bool = True,
        pre_select_all_rows: bool = False,
        pre_selected_rows: list = None,
        row_multi_select_with_click: bool = False,
        suppress_row_deselection: bool = False,
        suppress_row_click_selection: bool = False,
        group_selects_children: bool = True,
        group_selects_filtered: bool = True,
    ):
        """Configure grid selection features

        Args:
            selection_mode (str, optional):
                Either 'single', 'multiple' or 'disabled'. Defaults to 'single'.

            use_checkbox (bool, optional):
                Set to true to have checkbox next to each row.

            header_checkbox (bool, optional):
                Set to true to have a checkbox in the header to select all rows.

            header_checkbox_filtered_only (bool, optional):
                If header_checkbox is set to True, once the header checkbox is clicked, returned rows depend on this parameter.
                If this is set to True, only filtered (shown) rows will be selected and returned.
                If this is set to False, the whole dataframe (all rows regardless of the applited filter) will be selected and returned.

            pre_selected_rows (list, optional):
                Use list of dataframe row iloc index to set corresponding rows as selected state on load. Defaults to None.

            row_multi_select_with_click (bool, optional):
                If False user must hold shift to multiselect. Defaults to True if selection_mode is 'multiple'.

            suppress_row_deselection (bool, optional):
                Set to true to prevent rows from being deselected if you hold down Ctrl and click the row
                (i.e. once a row is selected, it remains selected until another row is selected in its place).
                By default the grid allows deselection of rows.
                Defaults to False.

            suppress_row_click_selection (bool, optional):
                Supress row selection by clicking. Usefull for checkbox selection for instance
                Defaults to False.

            group_selects_children (bool, optional):
                When rows are grouped selecting a group select all children.
                Defaults to True.

            group_selects_filtered (bool, optional):
                When a group is selected filtered rows are also selected.
                Defaults to True.
        """
        if selection_mode == "disabled":
            self._grid_options.pop("rowSelection", None)
            self._grid_options.pop("rowMultiSelectWithClick", None)
            self._grid_options.pop("suppressRowDeselection", None)
            self._grid_options.pop("suppressRowClickSelection", None)
            self._grid_options.pop("groupSelectsChildren", None)
            self._grid_options.pop("groupSelectsFiltered", None)
            return

        if use_checkbox:
            suppress_row_click_selection = True
            first_key = next(iter(self._grid_options["columnDefs"].keys()))
            self._grid_options["columnDefs"][first_key]["checkboxSelection"] = True
            if header_checkbox:
                self._grid_options["columnDefs"][first_key][
                    "headerCheckboxSelection"
                ] = True
                if header_checkbox_filtered_only:
                    self._grid_options["columnDefs"][first_key][
                        "headerCheckboxSelectionFilteredOnly"
                    ] = True

        if pre_selected_rows:
            self._grid_options["initialState"]["rowSelection"] = pre_selected_rows

        self._grid_options["rowSelection"] = selection_mode
        self._grid_options["rowMultiSelectWithClick"] = row_multi_select_with_click
        self._grid_options["suppressRowDeselection"] = suppress_row_deselection
        self._grid_options["suppressRowClickSelection"] = suppress_row_click_selection
        self._grid_options["groupSelectsChildren"] = (
            group_selects_children and selection_mode == "multiple"
        )
        self._grid_options["groupSelectsFiltered"] = group_selects_filtered

    def configure_pagination(
        self,
        enabled: bool = True,
        auto_page_size: bool = True,
        page_size: int = 10,
    ):
        """Configure grid's pagination features

        Args:
            enabled (bool, optional):
                Self explanatory. Defaults to True.

            auto_page_size (bool, optional):
                Calculates optimal pagination size based on grid Height. Defaults to True.

            page_size (int, optional):
                Forces page to have this number of rows per page. Defaults to 10.
        """
        if not enabled:
            self._grid_options.pop("pagination", None)
            self._grid_options.pop("paginationAutoPageSize", None)
            self._grid_options.pop("paginationPageSize", None)
            return

        self._grid_options["pagination"] = True
        if auto_page_size:
            self._grid_options["paginationAutoPageSize"] = auto_page_size
        else:
            self._grid_options["paginationPageSize"] = page_size

    def configure_first_column_as_index(
        self,
        suppress_menu: bool = True,
        header_text: str = "",
        resizable: bool = False,
        sortable: bool = True,
    ):
        """
        Configures the first column definition to look as an index column.

        Args:
            suppress_menu (bool, optional): Suppresses the header menu for the index col. Defaults to True.
            header_text (str, optional): Header for the index column. Defaults to empty string.
            resizable (bool, optional): Make index column resizable. Defaults to False.
            sortable (bool, optional): Make index column sortable. Defaults to True.

        """
        index_options = {
            "minWidth": 0,
            "cellStyle": {"color": "white", "background-color": "gray"},
            "pinned": "left",
            "resizable": resizable,
            "sortable": sortable,
            "suppressMovable": True,
            "suppressMenu": suppress_menu,
            "menuTabs": ["filterMenuTab"],
        }
        first_col_def = next(iter(self._grid_options["columnDefs"]))

        self.configure_column(first_col_def, header_text, **index_options)

    def build(self):
        """Builds the gridOptions dictionary

        Returns:
            dict: Returns a dicionary containing the configured grid options
        """
        self._grid_options["columnDefs"] = list(
            self._grid_options["columnDefs"].values()
        )

        return self._grid_options
