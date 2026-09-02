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
    COLOR_SCALE_SCOPES,
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
    assert COLOR_SCALE_SCHEMES == ("neutral", "positive", "diverging", "rank", "fill")
    assert COLOR_SCALE_MODES == ("minmax", "zscore", "anchor")
    assert COLOR_SCALE_SCOPES == ("level", "parent")


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


def test_reverse_is_accepted_as_a_bool():
    validate_color_scale_columns(grid_options({"scheme": "neutral", "reverse": True}))
    validate_color_scale_columns(grid_options({"scheme": "neutral", "reverse": False}))


def test_reverse_must_be_a_bool_not_an_int():
    with pytest.raises(ValueError, match="reverse"):
        validate_color_scale_columns(grid_options({"scheme": "neutral", "reverse": 1}))


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


# --- Phase 2 keys -----------------------------------------------------------


def test_scope_accepts_level_and_parent():
    validate_color_scale_columns(grid_options({"scheme": "neutral", "scope": "level"}))
    validate_color_scale_columns(grid_options({"scheme": "neutral", "scope": "parent"}))


def test_unknown_scope_is_rejected():
    with pytest.raises(ValueError, match="scope"):
        validate_color_scale_columns(grid_options({"scheme": "neutral", "scope": "depth"}))


def test_anchor_mode_with_both_keys_passes():
    validate_color_scale_columns(
        grid_options({"scheme": "diverging", "mode": "anchor", "anchor": 1.0, "span": 1.0})
    )


def test_anchor_mode_defaults_the_scheme_to_diverging():
    # No scheme at either level: the one asymmetry in resolution.
    validate_color_scale_columns(grid_options({"mode": "anchor", "anchor": 1.0, "span": 1.0}))


def test_anchor_mode_without_anchor_is_rejected():
    with pytest.raises(ValueError, match="anchor"):
        validate_color_scale_columns(grid_options({"scheme": "diverging", "mode": "anchor", "span": 1.0}))


def test_anchor_mode_without_span_is_rejected():
    with pytest.raises(ValueError, match="span"):
        validate_color_scale_columns(grid_options({"scheme": "diverging", "mode": "anchor", "anchor": 1.0}))


def test_anchor_mode_resolved_through_the_grid_default_still_needs_its_keys():
    # `mode` comes from the grid level, the keys from nowhere: still an error,
    # because the *merged* declaration is what has to be complete.
    with pytest.raises(ValueError, match="anchor"):
        validate_color_scale_columns(grid_options(True, {"scheme": "diverging", "mode": "anchor"}))


def test_anchor_keys_can_come_from_the_grid_default():
    validate_color_scale_columns(
        grid_options({"scheme": "positive"}, {"mode": "anchor", "anchor": 100, "span": 40})
    )


@pytest.mark.parametrize("anchor", [True, "1", None, float("nan"), float("inf")])
def test_anchor_must_be_a_finite_number(anchor):
    with pytest.raises(ValueError, match="anchor"):
        validate_color_scale_columns(
            grid_options({"scheme": "diverging", "mode": "anchor", "anchor": anchor, "span": 1.0})
        )


@pytest.mark.parametrize("span", [0, -1, True, "1", float("nan")])
def test_span_must_be_a_positive_finite_number(span):
    with pytest.raises(ValueError, match="span"):
        validate_color_scale_columns(
            grid_options({"scheme": "diverging", "mode": "anchor", "anchor": 1.0, "span": span})
        )


def test_anchor_keys_are_type_checked_even_when_the_mode_is_not_anchor():
    # Present keys are always type-checked, at both levels; only *relevance*
    # is lenient.
    with pytest.raises(ValueError, match="span"):
        validate_color_scale_columns(grid_options({"scheme": "positive", "span": -3}))


def test_rank_scheme_passes_with_and_without_direction():
    validate_color_scale_columns(grid_options({"scheme": "rank"}))
    validate_color_scale_columns(grid_options({"scheme": "rank", "reverse": True, "scope": "parent"}))


def test_rank_ignores_an_explicit_mode():
    # `rank` reads no mode. An explicit one validates and is ignored — a
    # grid-level `mode` default must not break a rank column.
    validate_color_scale_columns(grid_options({"scheme": "rank"}, {"mode": "minmax"}))
    validate_color_scale_columns(grid_options({"scheme": "rank", "mode": "anchor"}))


def test_fill_with_a_colour_passes():
    validate_color_scale_columns(grid_options({"scheme": "fill", "color": "rgb(4, 5, 6)"}))
    validate_color_scale_columns(
        grid_options({"scheme": "fill", "color": "var(--secondary-background-color)"})
    )


def test_fill_without_a_colour_is_rejected():
    with pytest.raises(ValueError, match="color"):
        validate_color_scale_columns(grid_options({"scheme": "fill"}))


def test_fill_colour_can_come_from_the_grid_default():
    validate_color_scale_columns(grid_options({"scheme": "fill"}, {"color": "rgb(1, 2, 3)"}))


@pytest.mark.parametrize("color", ["", "   ", 7, None, ["rgb(1, 2, 3)"]])
def test_fill_colour_must_be_a_non_empty_string(color):
    with pytest.raises(ValueError, match="color"):
        validate_color_scale_columns(grid_options({"scheme": "fill", "color": color}))


def test_fill_ignores_every_population_key_from_the_grid_default():
    # The rule that keeps grid-level defaults harmless: a fill column under a
    # ramp-shaped grid default must validate.
    validate_color_scale_columns(
        grid_options(
            {"scheme": "fill", "color": "rgb(1, 2, 3)"},
            {"scheme": "diverging", "mode": "zscore", "scope": "parent",
             "skip_non_positive": True, "reverse": True},
        )
    )


def test_a_grid_level_default_may_carry_every_new_key():
    validate_color_scale_columns(
        {
            "columnDefs": [{"field": "a"}],
            "context": {
                COLOR_SCALE_CONTEXT_KEY: {
                    "scheme": "diverging", "mode": "anchor", "scope": "parent",
                    "reverse": False, "skip_non_positive": False,
                    "anchor": 1.0, "span": 1.0, "color": "rgb(0, 0, 0)",
                }
            },
        }
    )


def test_true_with_a_defaults_only_grid_entry_and_no_scheme_is_still_rejected():
    # `configure_color_scale()` with no arguments writes `{}`; a bare opt-in
    # under it resolves to nothing, exactly as with no grid entry at all.
    with pytest.raises(ValueError, match="scheme"):
        validate_color_scale_columns(grid_options(True, {}))


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
