"""Validation rules for the built-in `stRatio` declaration.

The dangerous failure is a field name that resolves to nothing: the aggregator
sums `rowNode.data[field]`, a missing key contributes 0, and the ratio comes
out wrong with nothing raised anywhere. Every rule here exists to turn a silent
wrong number into a loud error.
"""

import pytest

from st_aggrid.ratio import validate_ratio_columns

COLUMNS = ["campaign", "cost", "installs", "rebate"]


def grid_options(context, **col_overrides):
    """One ratio column carrying `context`, plus a plain dimension column."""
    column = {"colId": "cpi", "field": "cpi", "aggFunc": "stRatio"}
    column.update(col_overrides)
    if context is not None:
        column["context"] = {"stRatio": context}
    return {"columnDefs": [{"field": "campaign", "rowGroup": True}, column]}


VALID = {"num": ["cost"], "den": ["installs"]}


def test_a_valid_declaration_passes():
    validate_ratio_columns(grid_options(VALID), COLUMNS)


def test_every_optional_key_is_accepted():
    validate_ratio_columns(
        grid_options(
            {
                "num": ["cost", "rebate"],
                "den": ["installs"],
                "num_signs": [1, -1],
                "multiplier": 1000,
                "scale": 0.5,
                "fill_null": 0.0,
            }
        ),
        COLUMNS,
    )


def test_fill_null_may_be_none():
    validate_ratio_columns(grid_options({**VALID, "fill_null": None}), COLUMNS)


def test_unknown_numerator_field_is_rejected():
    with pytest.raises(ValueError, match="spend"):
        validate_ratio_columns(grid_options({"num": ["spend"], "den": ["installs"]}), COLUMNS)


def test_unknown_denominator_field_is_rejected():
    with pytest.raises(ValueError, match="clicks"):
        validate_ratio_columns(grid_options({"num": ["cost"], "den": ["clicks"]}), COLUMNS)


def test_the_error_names_the_column_and_lists_what_is_available():
    with pytest.raises(ValueError) as excinfo:
        validate_ratio_columns(grid_options({"num": ["spend"], "den": ["installs"]}), COLUMNS)
    message = str(excinfo.value)
    assert "cpi" in message
    assert "spend" in message
    assert "installs" in message  # the available names


def test_fields_are_checked_against_the_data_not_the_column_defs():
    """`revenue_total` has no colDef and never will — it rides in the
    dataframe as an aggregation input only. Requiring a column would reject
    every ARPU and ROAS column the consumer defines."""
    validate_ratio_columns(
        grid_options({"num": ["revenue_total"], "den": ["installs"]}),
        ["campaign", "revenue_total", "installs"],
    )


def test_field_existence_is_skipped_when_there_is_no_data_to_check_against():
    validate_ratio_columns(grid_options({"num": ["spend"], "den": ["installs"]}), None)


def test_structural_rules_still_apply_without_data():
    with pytest.raises(ValueError, match="num"):
        validate_ratio_columns(grid_options({"num": [], "den": ["installs"]}), None)


@pytest.mark.parametrize(
    "context",
    [
        {"den": ["installs"]},
        {"num": ["cost"]},
        {"num": [], "den": ["installs"]},
        {"num": ["cost"], "den": []},
        {"num": "cost", "den": ["installs"]},
        {"num": [""], "den": ["installs"]},
        {"num": [1], "den": ["installs"]},
    ],
    ids=["no-num", "no-den", "empty-num", "empty-den", "num-not-a-list", "empty-name", "non-string"],
)
def test_num_and_den_must_be_non_empty_lists_of_names(context):
    with pytest.raises(ValueError):
        validate_ratio_columns(grid_options(context), COLUMNS)


def test_num_signs_length_must_match_num():
    with pytest.raises(ValueError, match="num_signs"):
        validate_ratio_columns(
            grid_options({"num": ["cost", "rebate"], "den": ["installs"], "num_signs": [1]}),
            COLUMNS,
        )


def test_num_signs_must_be_numbers():
    with pytest.raises(ValueError, match="num_signs"):
        validate_ratio_columns(grid_options({**VALID, "num_signs": ["+"]}), COLUMNS)


@pytest.mark.parametrize("key", ["multiplier", "scale"])
def test_multiplier_and_scale_must_be_numeric(key):
    with pytest.raises(ValueError, match=key):
        validate_ratio_columns(grid_options({**VALID, key: "1000"}), COLUMNS)


def test_fill_null_must_be_numeric_or_none():
    with pytest.raises(ValueError, match="fill_null"):
        validate_ratio_columns(grid_options({**VALID, "fill_null": "blank"}), COLUMNS)


def test_agg_func_without_a_context_is_rejected():
    with pytest.raises(ValueError, match="context"):
        validate_ratio_columns(grid_options(None), COLUMNS)


def test_a_context_on_a_column_group_child_is_validated():
    """Marketing wraps its metric columns in column groups, so the walk has to
    descend into `children` or validation silently covers nothing."""
    options = {
        "columnDefs": [
            {
                "headerName": "Acquisition",
                "children": [
                    {
                        "colId": "cpi",
                        "aggFunc": "stRatio",
                        "context": {"stRatio": {"num": ["spend"], "den": ["installs"]}},
                    }
                ],
            }
        ]
    }
    with pytest.raises(ValueError, match="spend"):
        validate_ratio_columns(options, COLUMNS)


def test_columns_without_a_ratio_context_are_ignored():
    options = {
        "columnDefs": [
            {"field": "campaign", "rowGroup": True},
            {"field": "cost", "aggFunc": "sum"},
            {"field": "notes", "context": {"metric_doc": {"name": "notes"}}},
        ]
    }
    validate_ratio_columns(options, COLUMNS)


def test_missing_or_empty_grid_options_are_ignored():
    validate_ratio_columns(None, COLUMNS)
    validate_ratio_columns({}, COLUMNS)
    validate_ratio_columns({"columnDefs": []}, COLUMNS)


def test_aggrid_rejects_an_unresolvable_ratio_before_rendering():
    """The rule has to fire from `AgGrid`, not just from the validator."""
    import pandas as pd

    from st_aggrid import AgGrid

    frame = pd.DataFrame({"campaign": ["A"], "cost": [10], "installs": [2]})
    options = {
        "columnDefs": [
            {"field": "campaign", "rowGroup": True},
            {
                "colId": "cpi",
                "aggFunc": "stRatio",
                "context": {"stRatio": {"num": ["spend"], "den": ["installs"]}},
            },
        ]
    }

    with pytest.raises(ValueError, match="spend"):
        AgGrid(frame, grid_options=options, key="ratio_validation_probe")
