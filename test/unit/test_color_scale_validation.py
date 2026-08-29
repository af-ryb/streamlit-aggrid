"""Validation rules for the built-in `stColorScale` declaration.

The failure this exists to prevent is a column that quietly paints nothing:
an unknown scheme name, or a `color_scale=True` with no grid-level default to
inherit from, both reach the browser as "no resolvable scheme" and are
indistinguishable from the feature simply being off. Every rule here turns
that silence into a loud error.

Unlike `ratio.py`'s validator this one takes no data columns — a colour scale
names no fields — so it applies to every grid, including one built entirely
from `grid_options["rowData"]`.
"""

import pytest

from st_aggrid.color_scale import (
    COLOR_SCALE_CONTEXT_KEY,
    COLOR_SCALE_MODES,
    COLOR_SCALE_SCHEMES,
    _merge_declaration,
    validate_color_scale_columns,
)


def grid_options(column_declaration, grid_declaration=None):
    """One painted column plus a plain dimension column, and optionally a
    grid-level default."""
    column = {"colId": "cpi", "field": "cpi"}
    if column_declaration is not None:
        column["context"] = {COLOR_SCALE_CONTEXT_KEY: column_declaration}
    options = {"columnDefs": [{"field": "campaign", "rowGroup": True}, column]}
    if grid_declaration is not None:
        options["context"] = {COLOR_SCALE_CONTEXT_KEY: grid_declaration}
    return options


def test_constants_are_the_literals_the_frontend_uses():
    assert COLOR_SCALE_CONTEXT_KEY == "stColorScale"
    assert COLOR_SCALE_SCHEMES == ("neutral", "positive", "diverging")
    assert COLOR_SCALE_MODES == ("minmax", "zscore")


def test_a_full_column_declaration_passes():
    validate_color_scale_columns(
        grid_options({"scheme": "diverging", "mode": "minmax", "skip_non_positive": False})
    )


def test_true_inherits_a_grid_level_scheme():
    validate_color_scale_columns(grid_options(True, {"scheme": "positive"}))


def test_false_is_accepted_and_needs_no_scheme():
    validate_color_scale_columns(grid_options(False))


def test_a_grid_level_default_alone_is_legal():
    # Defaults with nothing opted in paint nothing. That is a valid grid, not
    # an error — the switch simply happens to be off.
    validate_color_scale_columns({"columnDefs": [{"field": "a"}], "context":
                                  {COLOR_SCALE_CONTEXT_KEY: {"scheme": "neutral"}}})


def test_true_without_a_grid_level_default_is_rejected():
    with pytest.raises(ValueError, match="scheme"):
        validate_color_scale_columns(grid_options(True))


def test_a_column_override_wins_over_the_grid_default():
    validate_color_scale_columns(
        grid_options({"scheme": "neutral"}, {"scheme": "positive", "mode": "minmax"})
    )


def test_unknown_scheme_is_rejected():
    with pytest.raises(ValueError, match="scheme"):
        validate_color_scale_columns(grid_options({"scheme": "green"}))


def test_unknown_mode_is_rejected():
    with pytest.raises(ValueError, match="mode"):
        validate_color_scale_columns(grid_options({"scheme": "neutral", "mode": "zed"}))


def test_unknown_key_is_rejected():
    with pytest.raises(ValueError, match="alpha"):
        validate_color_scale_columns(grid_options({"scheme": "neutral", "alpha": 0.4}))


def test_reverse_is_rejected_until_phase_two():
    # Accepting a key the frontend ignores would let a consumer come to depend
    # on behaviour that does not exist.
    with pytest.raises(ValueError, match="reverse"):
        validate_color_scale_columns(grid_options({"scheme": "neutral", "reverse": True}))


def test_skip_non_positive_must_be_a_bool_not_an_int():
    # `bool` is an `int` subclass, so an `isinstance(..., int)` check would
    # let `1` through — the same trap `ratio.py`'s `_is_number` documents.
    with pytest.raises(ValueError, match="skip_non_positive"):
        validate_color_scale_columns(
            grid_options({"scheme": "neutral", "skip_non_positive": 1})
        )


def test_a_non_dict_column_declaration_is_rejected():
    with pytest.raises(ValueError, match="True, False or a dict"):
        validate_color_scale_columns(grid_options("positive"))


def test_a_bare_true_at_the_grid_level_is_rejected():
    # The grid level carries defaults only; `True` there activates nothing and
    # is a misunderstanding worth naming.
    with pytest.raises(ValueError, match="must be a dict"):
        validate_color_scale_columns(grid_options({"scheme": "neutral"}, True))


def test_a_declaration_inside_a_column_group_is_validated():
    options = {
        "columnDefs": [
            {
                "headerName": "Metrics",
                "children": [
                    {"colId": "cpi", "context": {COLOR_SCALE_CONTEXT_KEY: {"scheme": "nope"}}}
                ],
            }
        ]
    }
    with pytest.raises(ValueError, match="cpi"):
        validate_color_scale_columns(options)


def test_a_sibling_context_key_is_left_alone():
    # A metric column commonly carries both declarations; the colour-scale
    # validator must not trip over the ratio one.
    options = grid_options({"scheme": "neutral"})
    options["columnDefs"][1]["context"]["stRatio"] = {"num": ["cost"], "den": ["installs"]}
    validate_color_scale_columns(options)


def test_non_dict_grid_options_is_a_no_op():
    validate_color_scale_columns(None)
    validate_color_scale_columns("not grid options")


# `_merge_declaration` implements the column-over-grid-defaults rule that
# `validate_color_scale_columns` relies on. That rule is invisible to the
# raise/no-raise tests above: every case they cover pre-validates both
# operands individually before the merge, and the only post-merge check is a
# set-membership test on 'scheme' that cannot tell which operand supplied the
# winning value. So the precedence itself is asserted directly here, against
# the helper's return value.


def test_merge_a_column_value_beats_the_grid_value_for_the_same_key():
    assert _merge_declaration({"scheme": "positive"}, {"scheme": "neutral"}) == {
        "scheme": "neutral"
    }


def test_merge_a_grid_only_key_survives():
    assert _merge_declaration({"scheme": "positive", "mode": "zscore"}, {"scheme": "neutral"}) == {
        "scheme": "neutral",
        "mode": "zscore",
    }


def test_merge_a_column_only_key_survives():
    assert _merge_declaration({"scheme": "positive"}, {"skip_non_positive": True}) == {
        "scheme": "positive",
        "skip_non_positive": True,
    }


def test_merge_an_empty_column_declaration_yields_the_grid_defaults_unchanged():
    # This is the `color_scale=True` case: `own` is `{}`.
    grid_declaration = {"scheme": "positive", "mode": "minmax"}
    assert _merge_declaration(grid_declaration, {}) == grid_declaration


def test_merge_a_none_grid_declaration_yields_the_column_s_own_dict():
    own = {"scheme": "neutral"}
    assert _merge_declaration(None, own) == own
