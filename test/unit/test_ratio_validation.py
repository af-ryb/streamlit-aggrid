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


def test_den_const_alone_may_stand_in_for_an_empty_den():
    """`share = cost / 1020`: `den` is empty and the whole denominator is the
    constant."""
    validate_ratio_columns(
        grid_options({"num": ["cost"], "den": [], "den_const": 1020}), COLUMNS
    )


def test_den_const_may_be_combined_with_a_summed_den():
    validate_ratio_columns(
        grid_options({"num": ["cost"], "den": ["installs"], "den_const": 100}), COLUMNS
    )


def test_den_const_must_be_numeric():
    with pytest.raises(ValueError, match="den_const"):
        validate_ratio_columns(
            grid_options({"num": ["cost"], "den": [], "den_const": "1020"}), COLUMNS
        )


def test_den_const_rejects_bool_like_multiplier_and_scale():
    """`bool` is an `int` subclass; a `True` constant is a mistake, not a 1 —
    the same rule `_is_number` already applies to `multiplier`/`scale`."""
    with pytest.raises(ValueError, match="den_const"):
        validate_ratio_columns(
            grid_options({"num": ["cost"], "den": [], "den_const": True}), COLUMNS
        )


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


def test_validation_survives_the_json_rowdata_fallback():
    """`use_json_serialization="auto"` nulls out the DataFrame for any frame
    with a dict cell, even in a column the ratio never touches. The check must
    still fire — that path is exactly where a silently wrong ratio would go
    unnoticed."""
    import pandas as pd

    from st_aggrid import AgGrid

    frame = pd.DataFrame(
        {"campaign": ["A"], "cost": [10], "installs": [2], "tags": [{"a": 1}]}
    )
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
        AgGrid(frame, grid_options=options, key="ratio_validation_json_probe")


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


# --------------------------------------------------------------------------
# stRatioOfRatios
# --------------------------------------------------------------------------

ROR_COLUMNS = ["campaign", "ads_d0", "inst_d0", "ads_d1", "inst_d1"]

VALID_FROM_LEG = {"num": ["ads_d0"], "den": ["inst_d0"]}
VALID_TO_LEG = {"num": ["ads_d1"], "den": ["inst_d1"]}


def ror_grid_options(context, **col_overrides):
    """One `stRatioOfRatios` column carrying `context`, plus a plain
    dimension column — the ratio-of-ratios counterpart of `grid_options`
    above."""
    column = {"colId": "growth", "field": "growth", "aggFunc": "stRatioOfRatios"}
    column.update(col_overrides)
    if context is not None:
        column["context"] = {"stRatioOfRatios": context}
    return {"columnDefs": [{"field": "campaign", "rowGroup": True}, column]}


VALID_ROR = {"from": VALID_FROM_LEG, "to": VALID_TO_LEG}


def test_a_valid_ratio_of_ratios_declaration_passes():
    validate_ratio_columns(ror_grid_options(VALID_ROR), ROR_COLUMNS)


def test_a_leg_may_use_every_optional_key():
    """`num_signs`/`multiplier`/`scale`/`den_const` are the full `stRatio`
    leg shape (`_validate_leg`), available on either leg."""
    validate_ratio_columns(
        ror_grid_options(
            {
                "from": {
                    "num": ["ads_d0", "inst_d0"],
                    "den": ["inst_d0"],
                    "num_signs": [1, -1],
                    "multiplier": 1000,
                    "scale": 0.5,
                    "den_const": 10,
                },
                "to": VALID_TO_LEG,
            }
        ),
        ROR_COLUMNS,
    )


def test_ror_fill_null_may_be_none():
    validate_ratio_columns(ror_grid_options({**VALID_ROR, "fill_null": None}), ROR_COLUMNS)


def test_ror_fill_null_must_be_numeric_or_none():
    with pytest.raises(ValueError, match="fill_null"):
        validate_ratio_columns(
            ror_grid_options({**VALID_ROR, "fill_null": "blank"}), ROR_COLUMNS
        )


def test_missing_from_leg_is_rejected():
    with pytest.raises(ValueError, match="from"):
        validate_ratio_columns(ror_grid_options({"to": VALID_TO_LEG}), ROR_COLUMNS)


def test_missing_to_leg_is_rejected():
    with pytest.raises(ValueError, match="to"):
        validate_ratio_columns(ror_grid_options({"from": VALID_FROM_LEG}), ROR_COLUMNS)


def test_a_leg_that_is_not_a_dict_is_rejected():
    with pytest.raises(ValueError, match="from"):
        validate_ratio_columns(
            ror_grid_options({"from": ["ads_d0"], "to": VALID_TO_LEG}), ROR_COLUMNS
        )


def test_a_leg_with_no_num_is_rejected():
    with pytest.raises(ValueError, match="num"):
        validate_ratio_columns(
            ror_grid_options({"from": {"den": ["inst_d0"]}, "to": VALID_TO_LEG}),
            ROR_COLUMNS,
        )


def test_a_leg_with_no_den_is_rejected():
    with pytest.raises(ValueError, match="den"):
        validate_ratio_columns(
            ror_grid_options({"from": {"num": ["ads_d0"]}, "to": VALID_TO_LEG}),
            ROR_COLUMNS,
        )


def test_a_legs_den_const_alone_may_stand_in_for_an_empty_den():
    validate_ratio_columns(
        ror_grid_options(
            {"from": {"num": ["ads_d0"], "den": [], "den_const": 10}, "to": VALID_TO_LEG}
        ),
        ROR_COLUMNS,
    )


def test_a_legs_num_signs_length_must_match_its_num():
    with pytest.raises(ValueError, match="num_signs"):
        validate_ratio_columns(
            ror_grid_options(
                {
                    "from": {
                        "num": ["ads_d0", "inst_d0"],
                        "den": ["inst_d0"],
                        "num_signs": [1],
                    },
                    "to": VALID_TO_LEG,
                }
            ),
            ROR_COLUMNS,
        )


@pytest.mark.parametrize("key", ["multiplier", "scale", "den_const"])
def test_a_legs_numeric_options_must_be_numeric(key):
    with pytest.raises(ValueError, match=key):
        validate_ratio_columns(
            ror_grid_options({"from": {**VALID_FROM_LEG, key: "1000"}, "to": VALID_TO_LEG}),
            ROR_COLUMNS,
        )


def test_unknown_field_in_either_leg_is_rejected():
    with pytest.raises(ValueError, match="ad_spend"):
        validate_ratio_columns(
            ror_grid_options({"from": {"num": ["ad_spend"], "den": ["inst_d0"]}, "to": VALID_TO_LEG}),
            ROR_COLUMNS,
        )
    with pytest.raises(ValueError, match="conversions"):
        validate_ratio_columns(
            ror_grid_options({"from": VALID_FROM_LEG, "to": {"num": ["ads_d1"], "den": ["conversions"]}}),
            ROR_COLUMNS,
        )


def test_a_field_shared_by_both_legs_is_reported_once():
    """`inst_d0` unknown to `ROR_COLUMNS`-minus-itself, named by both `from`
    and `to` — the union is deduplicated so it appears once in the message,
    not twice."""
    columns = ["campaign", "ads_d0", "ads_d1"]
    with pytest.raises(ValueError) as excinfo:
        validate_ratio_columns(
            ror_grid_options(
                {
                    "from": {"num": ["ads_d0"], "den": ["inst_d0"]},
                    "to": {"num": ["ads_d1"], "den": ["inst_d0"]},
                }
            ),
            columns,
        )
    message = str(excinfo.value)
    assert message.count("inst_d0") == 1


def test_ror_field_existence_is_skipped_when_there_is_no_data_to_check_against():
    validate_ratio_columns(
        ror_grid_options({"from": {"num": ["spend"], "den": ["inst_d0"]}, "to": VALID_TO_LEG}),
        None,
    )


def test_agg_func_ratio_of_ratios_without_a_context_is_rejected():
    with pytest.raises(ValueError, match="context"):
        validate_ratio_columns(ror_grid_options(None), ROR_COLUMNS)


def test_a_ratio_of_ratios_context_on_a_column_group_child_is_validated():
    """Same descent-into-`children` requirement as `stRatio`'s own
    grouped-columns test."""
    options = {
        "columnDefs": [
            {
                "headerName": "Growth",
                "children": [
                    {
                        "colId": "growth",
                        "aggFunc": "stRatioOfRatios",
                        "context": {
                            "stRatioOfRatios": {
                                "from": {"num": ["ad_spend"], "den": ["inst_d0"]},
                                "to": VALID_TO_LEG,
                            }
                        },
                    }
                ],
            }
        ]
    }
    with pytest.raises(ValueError, match="ad_spend"):
        validate_ratio_columns(options, ROR_COLUMNS)


def test_stratio_and_stratio_of_ratios_are_validated_independently():
    """A grid with one column of each kind: an invalid `stRatio` column must
    not be masked by a valid `stRatioOfRatios` column sitting next to it in
    the same `columnDefs` walk."""
    options = {
        "columnDefs": [
            {"field": "campaign", "rowGroup": True},
            {
                "colId": "cpi",
                "aggFunc": "stRatio",
                "context": {"stRatio": {"num": ["spend"], "den": ["inst_d0"]}},
            },
            {
                "colId": "growth",
                "aggFunc": "stRatioOfRatios",
                "context": {"stRatioOfRatios": VALID_ROR},
            },
        ]
    }
    with pytest.raises(ValueError, match="spend"):
        validate_ratio_columns(options, ROR_COLUMNS)


def test_dispatch_checks_every_registered_context_key_on_one_column():
    """One column carrying both `context["stRatio"]` (invalid) and
    `context["stRatioOfRatios"]` (valid) — a nonsensical declaration nobody
    would write deliberately, but it proves `validate_ratio_columns`'s
    per-column loop checks every entry in `_VALIDATORS` rather than
    returning after the first key it finds."""
    options = {
        "columnDefs": [
            {"field": "campaign", "rowGroup": True},
            {
                "colId": "both",
                "context": {
                    "stRatio": {"num": ["spend"], "den": ["inst_d0"]},
                    "stRatioOfRatios": VALID_ROR,
                },
            },
        ]
    }
    with pytest.raises(ValueError, match="spend"):
        validate_ratio_columns(options, ROR_COLUMNS)


# --------------------------------------------------------------------------
# stWeightedAvg
# --------------------------------------------------------------------------

WAVG_COLUMNS = ["campaign", "wa_value", "wa_weight"]

VALID_WAVG = {"value": "wa_value", "weight": "wa_weight"}


def wavg_grid_options(context, **col_overrides):
    """One `stWeightedAvg` column carrying `context`, plus a plain dimension
    column — the weighted-average counterpart of `grid_options`/
    `ror_grid_options` above."""
    column = {"colId": "wavg", "field": "wavg", "aggFunc": "stWeightedAvg"}
    column.update(col_overrides)
    if context is not None:
        column["context"] = {"stWeightedAvg": context}
    return {"columnDefs": [{"field": "campaign", "rowGroup": True}, column]}


def test_a_valid_weighted_avg_declaration_passes():
    validate_ratio_columns(wavg_grid_options(VALID_WAVG), WAVG_COLUMNS)


def test_weighted_avg_every_optional_key_is_accepted():
    validate_ratio_columns(
        wavg_grid_options({**VALID_WAVG, "scale": 100.0, "fill_null": 0.0}),
        WAVG_COLUMNS,
    )


def test_weighted_avg_fill_null_may_be_none():
    validate_ratio_columns(
        wavg_grid_options({**VALID_WAVG, "fill_null": None}), WAVG_COLUMNS
    )


def test_weighted_avg_missing_value_is_rejected():
    with pytest.raises(ValueError, match="value"):
        validate_ratio_columns(
            wavg_grid_options({"weight": "wa_weight"}), WAVG_COLUMNS
        )


def test_weighted_avg_missing_weight_is_rejected():
    with pytest.raises(ValueError, match="weight"):
        validate_ratio_columns(
            wavg_grid_options({"value": "wa_value"}), WAVG_COLUMNS
        )


@pytest.mark.parametrize(
    "context",
    [
        {"value": "", "weight": "wa_weight"},
        {"value": 1, "weight": "wa_weight"},
        {"value": "wa_value", "weight": ""},
        {"value": "wa_value", "weight": 1},
    ],
    ids=["empty-value", "non-string-value", "empty-weight", "non-string-weight"],
)
def test_weighted_avg_value_and_weight_must_be_non_empty_strings(context):
    with pytest.raises(ValueError):
        validate_ratio_columns(wavg_grid_options(context), WAVG_COLUMNS)


def test_weighted_avg_config_that_is_not_a_dict_is_rejected():
    with pytest.raises(ValueError, match="stWeightedAvg"):
        validate_ratio_columns(
            wavg_grid_options(["wa_value", "wa_weight"]), WAVG_COLUMNS
        )


def test_weighted_avg_scale_must_be_numeric():
    with pytest.raises(ValueError, match="scale"):
        validate_ratio_columns(
            wavg_grid_options({**VALID_WAVG, "scale": "100"}), WAVG_COLUMNS
        )


def test_weighted_avg_fill_null_must_be_numeric_or_none():
    with pytest.raises(ValueError, match="fill_null"):
        validate_ratio_columns(
            wavg_grid_options({**VALID_WAVG, "fill_null": "blank"}), WAVG_COLUMNS
        )


def test_unknown_value_field_is_rejected():
    with pytest.raises(ValueError, match="arpu"):
        validate_ratio_columns(
            wavg_grid_options({"value": "arpu", "weight": "wa_weight"}), WAVG_COLUMNS
        )


def test_unknown_weight_field_is_rejected():
    with pytest.raises(ValueError, match="installs"):
        validate_ratio_columns(
            wavg_grid_options({"value": "wa_value", "weight": "installs"}), WAVG_COLUMNS
        )


def test_weighted_avg_field_existence_is_skipped_when_there_is_no_data_to_check_against():
    validate_ratio_columns(
        wavg_grid_options({"value": "arpu", "weight": "wa_weight"}), None
    )


def test_agg_func_weighted_avg_without_a_context_is_rejected():
    with pytest.raises(ValueError, match="context"):
        validate_ratio_columns(wavg_grid_options(None), WAVG_COLUMNS)


def test_a_weighted_avg_context_on_a_column_group_child_is_validated():
    """Same descent-into-`children` requirement as `stRatio`'s and
    `stRatioOfRatios`'s own grouped-columns tests."""
    options = {
        "columnDefs": [
            {
                "headerName": "Weighted Avg",
                "children": [
                    {
                        "colId": "wavg",
                        "aggFunc": "stWeightedAvg",
                        "context": {
                            "stWeightedAvg": {"value": "arpu", "weight": "wa_weight"}
                        },
                    }
                ],
            }
        ]
    }
    with pytest.raises(ValueError, match="arpu"):
        validate_ratio_columns(options, WAVG_COLUMNS)


def test_all_three_aggregators_are_validated_independently():
    """A grid with one column of each kind: an invalid `stWeightedAvg` column
    must not be masked by valid `stRatio`/`stRatioOfRatios` columns sitting
    next to it in the same `columnDefs` walk, and vice versa."""
    columns = ["campaign", "cost", "installs", "ads_d0", "inst_d0", "ads_d1", "inst_d1", "wa_weight"]
    options = {
        "columnDefs": [
            {"field": "campaign", "rowGroup": True},
            {
                "colId": "cpi",
                "aggFunc": "stRatio",
                "context": {"stRatio": {"num": ["cost"], "den": ["installs"]}},
            },
            {
                "colId": "growth",
                "aggFunc": "stRatioOfRatios",
                "context": {"stRatioOfRatios": VALID_ROR},
            },
            {
                "colId": "wavg",
                "aggFunc": "stWeightedAvg",
                "context": {"stWeightedAvg": {"value": "arpu", "weight": "wa_weight"}},
            },
        ]
    }
    with pytest.raises(ValueError, match="arpu"):
        validate_ratio_columns(options, columns)

