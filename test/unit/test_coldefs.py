"""The colDef walk shared by the built-in validators.

Both `ratio.py` and `color_scale.py` must see every column on a grouped grid;
a walk that stopped at the top level would cover nothing there, and the
consumer this feature exists for wraps all of its metric columns in groups.
"""

from st_aggrid._coldefs import column_label, iter_column_defs


def test_walk_yields_leaf_columns():
    defs = [{"field": "a"}, {"field": "b"}]
    assert [c["field"] for c in iter_column_defs(defs)] == ["a", "b"]


def test_walk_descends_into_column_groups():
    defs = [{"headerName": "G", "children": [{"field": "a"}, {"field": "b"}]}]
    # The group itself is yielded too — a declaration on a group colDef is
    # malformed rather than invisible, and the validators must be able to say so.
    assert [c.get("field") for c in iter_column_defs(defs)] == [None, "a", "b"]


def test_walk_nests_arbitrarily_deep():
    defs = [{"children": [{"children": [{"field": "deep"}]}]}]
    assert [c.get("field") for c in iter_column_defs(defs)] == [None, None, "deep"]


def test_walk_tolerates_a_non_list_and_non_dict_entries():
    assert list(iter_column_defs(None)) == []
    assert list(iter_column_defs("columnDefs")) == []
    assert [c["field"] for c in iter_column_defs([None, 7, {"field": "a"}])] == ["a"]


def test_column_label_prefers_col_id_then_field():
    assert column_label({"colId": "cpi", "field": "cost"}) == "column 'cpi'"
    assert column_label({"field": "cost"}) == "column 'cost'"
    assert column_label({}) == "unnamed aggregation column"
