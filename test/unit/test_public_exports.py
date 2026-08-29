"""`validate_ratio_columns` and the name constants for all three built-in
aggregators are re-exported from the package root (Task 8, P4 in
`2026-08-11-stratio-followups-small.md`) so a consumer can validate its own
grid options, or reference an aggregator's name/context key, without
importing `st_aggrid.ratio` directly. This pins that the re-export exists and
that each constant still equals the literal the frontend registers under —
`st_aggrid/ratio.py` and every `aggFuncs/*.ts` module agree by construction
(same string used for `aggFunc` and for the `context` key), but nothing
mechanical stops the Python and TypeScript sides from drifting apart, so the
literals are pinned here by hand.

`stRatio` alone has two names for the same pair of strings: `AGG_FUNC_NAME`/
`CONTEXT_KEY` (the original, unprefixed names from `st_aggrid.ratio`) and
`RATIO_AGG_FUNC`/`RATIO_CONTEXT_KEY` (the preferred, prefixed names added
here — final review, fix 4 — so `stRatio` reads the same way its two
siblings already do). Both pairs must keep resolving to the same object.
"""

import st_aggrid
from st_aggrid import (
    AGG_FUNC_NAME,
    CONTEXT_KEY,
    RATIO_AGG_FUNC,
    RATIO_CONTEXT_KEY,
    RATIO_OF_RATIOS_AGG_FUNC,
    RATIO_OF_RATIOS_CONTEXT_KEY,
    WEIGHTED_AVG_AGG_FUNC,
    WEIGHTED_AVG_CONTEXT_KEY,
    validate_ratio_columns,
)


def test_validate_ratio_columns_is_importable_from_the_package_root():
    assert st_aggrid.validate_ratio_columns is validate_ratio_columns
    assert callable(validate_ratio_columns)


def test_name_constants_are_importable_from_the_package_root():
    # Same objects as `st_aggrid.ratio`'s, not copies re-typed here — a
    # re-export that silently forked the value would defeat the point of
    # having one.
    from st_aggrid import ratio as ratio_module

    assert st_aggrid.AGG_FUNC_NAME is ratio_module.AGG_FUNC_NAME
    assert st_aggrid.CONTEXT_KEY is ratio_module.CONTEXT_KEY
    assert st_aggrid.RATIO_AGG_FUNC is ratio_module.AGG_FUNC_NAME
    assert st_aggrid.RATIO_CONTEXT_KEY is ratio_module.CONTEXT_KEY
    assert st_aggrid.RATIO_OF_RATIOS_AGG_FUNC is ratio_module.RATIO_OF_RATIOS_AGG_FUNC
    assert (
        st_aggrid.RATIO_OF_RATIOS_CONTEXT_KEY
        is ratio_module.RATIO_OF_RATIOS_CONTEXT_KEY
    )
    assert st_aggrid.WEIGHTED_AVG_AGG_FUNC is ratio_module.WEIGHTED_AVG_AGG_FUNC
    assert st_aggrid.WEIGHTED_AVG_CONTEXT_KEY is ratio_module.WEIGHTED_AVG_CONTEXT_KEY


def test_name_constants_equal_the_literals_the_frontend_registers_under():
    # Aggregator name and context key are always the same string (Global
    # Constraints), and these are the exact literals `colDef.aggFunc` /
    # `colDef.context[...]` must use from Python or JavaScript alike.
    assert AGG_FUNC_NAME == "stRatio"
    assert CONTEXT_KEY == "stRatio"
    assert RATIO_AGG_FUNC == "stRatio"
    assert RATIO_CONTEXT_KEY == "stRatio"
    assert RATIO_OF_RATIOS_AGG_FUNC == "stRatioOfRatios"
    assert RATIO_OF_RATIOS_CONTEXT_KEY == "stRatioOfRatios"
    assert WEIGHTED_AVG_AGG_FUNC == "stWeightedAvg"
    assert WEIGHTED_AVG_CONTEXT_KEY == "stWeightedAvg"


def test_every_re_exported_name_is_in_all():
    for name in (
        "AGG_FUNC_NAME",
        "CONTEXT_KEY",
        "RATIO_AGG_FUNC",
        "RATIO_CONTEXT_KEY",
        "RATIO_OF_RATIOS_AGG_FUNC",
        "RATIO_OF_RATIOS_CONTEXT_KEY",
        "WEIGHTED_AVG_AGG_FUNC",
        "WEIGHTED_AVG_CONTEXT_KEY",
        "validate_ratio_columns",
    ):
        assert name in st_aggrid.__all__, f"{name!r} missing from st_aggrid.__all__"
        assert hasattr(st_aggrid, name), f"{name!r} not actually importable from st_aggrid"


def test_color_scale_names_are_importable_from_the_package_root():
    from st_aggrid import (
        COLOR_SCALE_CONTEXT_KEY,
        COLOR_SCALE_MODES,
        COLOR_SCALE_SCHEMES,
        validate_color_scale_columns,
    )
    from st_aggrid import color_scale as color_scale_module

    assert st_aggrid.COLOR_SCALE_CONTEXT_KEY is color_scale_module.COLOR_SCALE_CONTEXT_KEY
    assert st_aggrid.COLOR_SCALE_SCHEMES is color_scale_module.COLOR_SCALE_SCHEMES
    assert st_aggrid.COLOR_SCALE_MODES is color_scale_module.COLOR_SCALE_MODES
    assert st_aggrid.validate_color_scale_columns is validate_color_scale_columns


def test_color_scale_literals_match_what_the_frontend_registers_under():
    # `colorScales/index.ts` uses "stColorScale" as its context key and
    # `colorScales/schemes.ts` keys `SCHEMES` by these exact names. Nothing
    # mechanical keeps the two languages in step, so the literals are pinned
    # here by hand.
    assert st_aggrid.COLOR_SCALE_CONTEXT_KEY == "stColorScale"
    assert st_aggrid.COLOR_SCALE_SCHEMES == ("neutral", "positive", "diverging")
    assert st_aggrid.COLOR_SCALE_MODES == ("minmax", "zscore")


def test_every_public_name_is_in_dunder_all():
    for name in (
        "COLOR_SCALE_CONTEXT_KEY",
        "COLOR_SCALE_MODES",
        "COLOR_SCALE_SCHEMES",
        "validate_color_scale_columns",
    ):
        assert name in st_aggrid.__all__
