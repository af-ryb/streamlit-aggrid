"""Guard the ratio fixture's arithmetic and its discriminating power.

The browser suites assert that a grid matches these numbers. If the numbers
themselves drift, every one of those assertions still passes while measuring
the wrong thing, so the reference arithmetic is pinned here in pure Python.

The important property is *discrimination*: at every level under test,
``Σnum/Σden`` must differ from the average of that node's children. Data where
the two coincide cannot distinguish a correct aggregator from one that averages
its children, and a suite built on it passes against a broken implementation.
"""

from math import isclose

import pytest

from ratio_fixture import (
    DEGENERATE_NODES,
    GROWTH_SPECS,
    GROWTH_SPECS_BY_ID,
    PIVOT_BLIND_CELLS,
    RATIO_ROWS,
    RATIO_SPECS,
    RATIO_SPECS_BY_ID,
    SHARE_SPEC,
    WEIGHTED_SPECS,
    WEIGHTED_SPECS_BY_ID,
    evaluate,
    evaluate_avg_of,
    evaluate_legacy,
    evaluate_ratio_of_ratios,
    evaluate_ratio_of_ratios_legacy,
    evaluate_weighted_avg,
    expected,
    expected_legacy,
    expected_ratio_of_ratios,
    expected_weighted_avg,
    ratio_dataframe,
    rows_where,
)

CAMPAIGNS = ("A", "B")
COUNTRIES = ("US", "DE")
CELLS = tuple((c, k) for c in CAMPAIGNS for k in COUNTRIES)


# --------------------------------------------------------------------------
# The reference numbers from the design spec
# --------------------------------------------------------------------------


def test_row_data_reproduces_the_specs_reference_fixture():
    assert sum(r["cost"] for r in rows_where(campaign="A", country="US")) == 900
    assert sum(r["installs"] for r in rows_where(campaign="A", country="US")) == 10
    assert sum(r["cost"] for r in rows_where(campaign="A", country="DE")) == 100
    assert sum(r["installs"] for r in rows_where(campaign="A", country="DE")) == 90
    assert sum(r["cost"] for r in rows_where(campaign="B", country="US")) == 10
    assert sum(r["installs"] for r in rows_where(campaign="B", country="US")) == 100
    assert sum(r["cost"] for r in rows_where(campaign="B", country="DE")) == 10
    assert sum(r["installs"] for r in rows_where(campaign="B", country="DE")) == 100


def test_cpi_matches_the_specs_worked_example():
    assert expected("cpi", campaign="A") == pytest.approx(10.00)
    assert expected("cpi", campaign="B") == pytest.approx(0.10)
    assert expected("cpi") == pytest.approx(3.40)


# --------------------------------------------------------------------------
# Discrimination
# --------------------------------------------------------------------------


@pytest.mark.parametrize("spec", RATIO_SPECS, ids=lambda s: s.col_id)
def test_grand_total_differs_from_the_average_of_the_campaign_ratios(spec):
    """The multi-level trap: a node whose children are themselves groups."""
    correct = evaluate(spec, rows_where())
    averaged = evaluate_avg_of(
        evaluate(spec, rows_where(campaign=c)) for c in CAMPAIGNS
    )
    assert correct != pytest.approx(averaged), (
        f"{spec.col_id}: Σnum/Σden coincides with avg(children) at the grand "
        "total, so this column cannot detect an averaging aggregator there"
    )


def _same(left, right) -> bool:
    if left is None or right is None:
        return left is right
    return isclose(left, right, rel_tol=1e-9, abs_tol=1e-12)


def _ratio_value_at(spec):
    """A ``**dims -> value`` closure for a `RatioSpec` (`evaluate`'s
    ``(spec, rows)`` argument order)."""
    return lambda **dims: evaluate(spec, rows_where(**dims))


def _rows_first_value_at(spec, evaluate_fn):
    """Same, for `evaluate_ratio_of_ratios`/`evaluate_weighted_avg`, whose
    argument order is ``(rows, spec)``."""
    return lambda **dims: evaluate_fn(rows_where(**dims), spec)


#: Every column this fixture can evaluate, paired with a ``**dims -> value``
#: accessor. ``RATIO_SPECS`` plus :data:`SHARE_SPEC` (a `RatioSpec` kept out
#: of ``RATIO_SPECS`` on purpose — see its own comment) share ``evaluate``;
#: :data:`GROWTH_SPECS` and :data:`WEIGHTED_SPECS` bring their own evaluator.
#: The two-directional degeneracy tests below measure over *all* of these, so
#: a fixture column that is quietly blind somewhere fails loudly regardless
#: of which aggregator family it belongs to.
ALL_COLUMNS = (
    *((spec.col_id, _ratio_value_at(spec)) for spec in RATIO_SPECS),
    (SHARE_SPEC.col_id, _ratio_value_at(SHARE_SPEC)),
    *(
        (spec.col_id, _rows_first_value_at(spec, evaluate_ratio_of_ratios))
        for spec in GROWTH_SPECS
    ),
    *(
        (spec.col_id, _rows_first_value_at(spec, evaluate_weighted_avg))
        for spec in WEIGHTED_SPECS
    ),
)


def test_campaign_totals_differ_from_the_average_of_their_country_ratios():
    """Which (column, campaign) nodes are blind to an averaging aggregator is
    a property of the data, so measure it and compare against the declared
    set. Asserting both directions means the constant cannot rot: a fixture
    edit that creates a new blind spot fails, and so does one that removes a
    listed spot without updating the list. Covers every column family this
    fixture defines, not just `RatioSpec` — `wavg` at campaign B turned out
    to be degenerate for a genuinely different reason than `cpi`/`arpp`
    (see `DEGENERATE_NODES`), found by exactly this measurement."""
    measured = {
        (col_id, campaign)
        for col_id, value_at in ALL_COLUMNS
        for campaign in CAMPAIGNS
        if _same(
            value_at(campaign=campaign),
            evaluate_avg_of(value_at(campaign=campaign, country=k) for k in COUNTRIES),
        )
    }
    assert measured == set(DEGENERATE_NODES)


def test_every_campaign_a_column_discriminates():
    """The blind spots are all on campaign B, whose components the design
    spec's reference fixture fixes at 10/100 in both countries. Campaign A is
    the one that has to catch an averaging aggregator, on every column."""
    assert not any(campaign == "A" for _, campaign in DEGENERATE_NODES)


def test_grand_total_differs_from_the_average_of_the_campaign_ratios_for_every_column():
    """No column is blind at the grand-total row — the level every grid shows."""
    for spec in RATIO_SPECS:
        assert not _same(
            evaluate(spec, rows_where()),
            evaluate_avg_of(evaluate(spec, rows_where(campaign=c)) for c in CAMPAIGNS),
        ), spec.col_id


def test_pivot_cells_differ_from_their_row_totals():
    """The pivot trap. An aggregator that ignores the pivot key returns the
    row's total in every cell, so a cell that already equals its row total
    cannot detect that. Same two-directional check as the averaging trap,
    over every column family in :data:`ALL_COLUMNS`."""
    measured = {
        (col_id, campaign, country)
        for col_id, value_at in ALL_COLUMNS
        for campaign, country in CELLS
        if _same(value_at(campaign=campaign, country=country), value_at(campaign=campaign))
    }
    assert measured == set(PIVOT_BLIND_CELLS)


def test_country_totals_differ_from_the_grand_total_for_every_column():
    """The pivot grid's total row: each country column must be distinguishable
    from the overall ratio, on every column, with no exemptions."""
    for spec in RATIO_SPECS:
        for country in COUNTRIES:
            assert not _same(
                evaluate(spec, rows_where(country=country)),
                evaluate(spec, rows_where()),
            ), f"{spec.col_id} / {country}"


#: `ALL_COLUMNS` minus the `RATIO_SPECS` columns already covered by the two
#: tests above — `share`, `growth`, `growth_neg` and the `wavg` family.
NEW_COLUMNS = tuple(
    (col_id, value_at) for col_id, value_at in ALL_COLUMNS if col_id not in RATIO_SPECS_BY_ID
)

#: The one column where the grand total *does* coincide with the average of
#: the campaign totals — see the test below for why.
GRAND_TOTAL_EXEMPT = frozenset({"wavg_blank"})


def test_new_columns_grand_total_differs_from_the_average_of_the_campaign_ratios():
    """The grand-total counterpart of
    `test_grand_total_differs_from_the_average_of_the_campaign_ratios_for_every_column`,
    extended to `share`, `growth`, `growth_neg` and the `wavg` family — with
    one documented exception.

    `wavg_blank`'s campaign B is `None` throughout (zero payers, so the
    surviving weight never reaches campaign B at any level), and
    `evaluate_avg_of` drops `None` children rather than averaging them in.
    `avg(campaign A, None)` therefore reduces to campaign A's own ratio,
    which is then trivially the grand total too, since campaign B never
    contributes to `wavg_blank` anywhere. `wavg_zero`'s `fill_null=0.0` does
    not collapse the same way — `0.0` survives `evaluate_avg_of`'s filter and
    pulls the average away from the grand total — so it is not exempt.
    """
    for col_id, value_at in NEW_COLUMNS:
        grand = value_at()
        averaged = evaluate_avg_of(value_at(campaign=c) for c in CAMPAIGNS)
        if col_id in GRAND_TOTAL_EXEMPT:
            assert _same(grand, averaged), (
                f"{col_id}: expected the documented grand-total exemption to "
                "still hold"
            )
        else:
            assert not _same(grand, averaged), col_id


def test_new_columns_country_totals_differ_from_the_grand_total():
    """The country-total counterpart, extended the same way — no exemptions
    here: even `wavg_blank`/`wavg_zero`'s grand total pools both countries,
    so a single country's total always differs from it."""
    for col_id, value_at in NEW_COLUMNS:
        grand = value_at()
        for country in COUNTRIES:
            assert not _same(value_at(country=country), grand), f"{col_id} / {country}"


# --------------------------------------------------------------------------
# Parameter surface
# --------------------------------------------------------------------------


def test_multiplier_is_applied_inside_the_numerator():
    # 1000 cost / 30000 impressions * 1000 = 33.333…
    assert expected("cpm", campaign="A") == pytest.approx(1000 / 30000 * 1000)


def test_scale_is_applied_to_the_final_value():
    # 2400 seconds / 50 sessions / 60 = 0.8 minutes
    assert expected("sess_min", campaign="A") == pytest.approx(0.8)


def test_num_signs_subtracts_the_second_numerator_term():
    # (1000 cost - 120 rebate) / 100 installs
    assert expected("net_cpi", campaign="A") == pytest.approx(8.8)


def test_fill_null_zero_and_none_differ_only_where_the_denominator_collapses():
    assert expected("arpp", campaign="A") == expected("arpp_blank", campaign="A")
    assert expected("arpp", campaign="B") == 0.0
    assert expected("arpp_blank", campaign="B") is None


# --------------------------------------------------------------------------
# The legacy evaluator mirrors the JavaScript's documented gaps
# --------------------------------------------------------------------------


def test_legacy_adds_the_second_numerator_term_instead_of_subtracting_it():
    assert expected_legacy("net_cpi", campaign="A") == pytest.approx(11.2)
    assert expected("net_cpi", campaign="A") == pytest.approx(8.8)


def test_legacy_ignores_fill_null_and_always_blanks_a_collapsed_denominator():
    assert expected_legacy("arpp", campaign="B") is None
    assert expected("arpp", campaign="B") == 0.0


@pytest.mark.parametrize("col_id", ["cpi", "cpm", "sess_min", "arpp_blank"])
def test_legacy_and_specified_semantics_agree_everywhere_else(col_id):
    """Only `num_signs` and `fill_null` may differ. Any other divergence would
    be an unintended behaviour change hiding inside the migration."""
    spec = RATIO_SPECS_BY_ID[col_id]
    for dims in ({}, *({"campaign": c} for c in CAMPAIGNS),
                 *({"campaign": c, "country": k} for c, k in CELLS)):
        assert evaluate(spec, rows_where(**dims)) == pytest.approx(
            evaluate_legacy(spec, rows_where(**dims))
        ), f"{col_id} {dims}"


# --------------------------------------------------------------------------
# DataFrame
# --------------------------------------------------------------------------


def test_dataframe_carries_components_and_a_precomputed_scalar_per_ratio():
    frame = ratio_dataframe()

    assert len(frame) == len(RATIO_ROWS)
    for spec in RATIO_SPECS:
        assert spec.col_id in frame.columns

    first = frame.iloc[0]
    assert first["cpi"] == pytest.approx(400.0)  # 800 cost / 2 installs
    assert first["net_cpi"] == pytest.approx(350.0)  # (800 - 100) / 2


def test_precomputed_leaf_values_follow_the_specified_semantics():
    """Leaf cells come from the dataframe, not from the aggregator. They use
    the signed numerator, so a leaf can legitimately disagree with the legacy
    group row above it."""
    frame = ratio_dataframe()
    for position, row in enumerate(RATIO_ROWS):
        for spec in RATIO_SPECS:
            reference = evaluate(spec, [row])
            actual = frame.iloc[position][spec.col_id]
            if reference is None:
                assert actual != actual, f"{spec.col_id} row {position} should be NaN"
            else:
                assert actual == pytest.approx(reference)


# --------------------------------------------------------------------------
# Context payloads
# --------------------------------------------------------------------------


def test_declarative_context_carries_lists_and_omits_defaults():
    assert RATIO_SPECS_BY_ID["cpi"].to_context() == {
        "num": ["cost"],
        "den": ["installs"],
    }
    assert RATIO_SPECS_BY_ID["net_cpi"].to_context() == {
        "num": ["cost", "rebate"],
        "den": ["installs"],
        "num_signs": [1, -1],
    }
    assert RATIO_SPECS_BY_ID["cpm"].to_context()["multiplier"] == 1000.0

    # `fill_null` defaults to None (an empty cell), so it is emitted only when
    # a spec asks for a concrete filler.
    assert RATIO_SPECS_BY_ID["arpp"].to_context()["fill_null"] == 0.0
    assert "fill_null" not in RATIO_SPECS_BY_ID["arpp_blank"].to_context()


def test_legacy_context_flattens_to_num_num2_den():
    assert RATIO_SPECS_BY_ID["net_cpi"].to_legacy_context() == {
        "num": "cost",
        "num2": "rebate",
        "den": "installs",
    }
    assert "num_signs" not in RATIO_SPECS_BY_ID["net_cpi"].to_legacy_context()
    assert "fill_null" not in RATIO_SPECS_BY_ID["arpp_blank"].to_legacy_context()


def test_share_context_emits_den_const_and_scale():
    assert SHARE_SPEC.to_context() == {
        "num": ["cost"],
        "den": [],
        "scale": 100.0,
        "den_const": 1020.0,
    }
    assert "den_const" not in RATIO_SPECS_BY_ID["cpi"].to_context()


def test_ratio_of_ratios_context_emits_from_and_to_legs():
    assert GROWTH_SPECS_BY_ID["growth"].to_context() == {
        "from": {"num": ["ads_d0"], "den": ["inst_d0"]},
        "to": {"num": ["ads_d1"], "den": ["inst_d1"]},
    }
    assert "fill_null" not in GROWTH_SPECS_BY_ID["growth"].to_context()


def test_weighted_avg_context_emits_value_weight_and_non_default_fields():
    assert WEIGHTED_SPECS_BY_ID["wavg"].to_context() == {
        "value": "wa_value",
        "weight": "wa_weight",
    }
    assert WEIGHTED_SPECS_BY_ID["wavg_zero"].to_context() == {
        "value": "wa_value",
        "weight": "payers",
        "fill_null": 0.0,
    }
    assert "fill_null" not in WEIGHTED_SPECS_BY_ID["wavg_blank"].to_context()


# --------------------------------------------------------------------------
# Growth (ratio-of-ratios)
# --------------------------------------------------------------------------


def test_growth_matches_the_briefs_reference_table():
    assert expected_ratio_of_ratios("growth", campaign="A", country="US") == pytest.approx(0.9)
    assert expected_ratio_of_ratios("growth", campaign="A", country="DE") == pytest.approx(4.0)
    assert expected_ratio_of_ratios("growth", campaign="A") == pytest.approx(13 / 11)  # 1.181818…
    assert expected_ratio_of_ratios("growth", campaign="B", country="US") == pytest.approx(1.0)
    assert expected_ratio_of_ratios("growth", campaign="B", country="DE") == pytest.approx(2.0)
    assert expected_ratio_of_ratios("growth", campaign="B") == pytest.approx(5 / 3)  # 1.666666…
    assert expected_ratio_of_ratios("growth") == pytest.approx(9 / 7)  # 1.285714…, the grand total


def test_growth_neg_matches_the_briefs_reference_table():
    assert expected_ratio_of_ratios("growth_neg", campaign="A", country="US") == pytest.approx(0.9)
    assert expected_ratio_of_ratios("growth_neg", campaign="A", country="DE") == pytest.approx(4.0)
    assert expected_ratio_of_ratios("growth_neg", campaign="A") == pytest.approx(13 / 11)
    assert expected_ratio_of_ratios("growth_neg", campaign="B", country="US") == pytest.approx(-1.0)
    assert expected_ratio_of_ratios("growth_neg", campaign="B", country="DE") == pytest.approx(-2.0)
    assert expected_ratio_of_ratios("growth_neg", campaign="B") == pytest.approx(-5 / 3)
    assert expected_ratio_of_ratios("growth_neg") == pytest.approx(2.25)


def test_growth_is_direction_discriminating():
    """The property the P1 spec asks for and the pre-existing fixture lacks:
    `growth` at A/US is 0.9 — *below* 1 — while campaign A's row total is
    1.1818… — *above* 1. They differ in direction, not just magnitude, so a
    pivot test that accidentally reads the row total instead of the pivot
    cell fails on sign, which no `pytest.approx` tolerance can paper over."""
    a_us = expected_ratio_of_ratios("growth", campaign="A", country="US")
    a_total = expected_ratio_of_ratios("growth", campaign="A")
    assert a_us < 1.0
    assert a_total > 1.0


def test_growth_neg_pins_the_gt_zero_to_ne_zero_gate_change():
    """The Global Constraints' `> 0` -> `!= 0` behaviour change, pinned as a
    fixture number instead of a production surprise: campaign B's *from*-
    period ratio (`credits_d0`/`inst_d0`) is negative, so the declarative
    `evaluate_ratio_of_ratios` computes a real negative growth number while
    the retired JavaScript's `evaluate_ratio_of_ratios_legacy` — gated on
    `from_ratio > 0` — blanks the cell."""
    for dims in (
        {"campaign": "B", "country": "US"},
        {"campaign": "B", "country": "DE"},
        {"campaign": "B"},
    ):
        assert (
            evaluate_ratio_of_ratios_legacy(rows_where(**dims), GROWTH_SPECS_BY_ID["growth_neg"])
            is None
        ), dims

    assert expected_ratio_of_ratios("growth_neg", campaign="B", country="US") == pytest.approx(-1.0)
    assert expected_ratio_of_ratios("growth_neg", campaign="B", country="DE") == pytest.approx(-2.0)
    assert expected_ratio_of_ratios("growth_neg", campaign="B") == pytest.approx(-5 / 3)


# --------------------------------------------------------------------------
# Weighted average
# --------------------------------------------------------------------------


def test_wavg_matches_the_briefs_reference_table():
    assert expected_weighted_avg("wavg", campaign="A", country="US") == pytest.approx(2.8)
    assert expected_weighted_avg("wavg", campaign="A", country="DE") == pytest.approx(2.0)
    assert expected_weighted_avg("wavg", campaign="A") == pytest.approx(2.08)
    assert expected_weighted_avg("wavg", campaign="B", country="US") == pytest.approx(3.0)
    assert expected_weighted_avg("wavg", campaign="B", country="DE") == pytest.approx(5.0)
    assert expected_weighted_avg("wavg", campaign="B") == pytest.approx(4.0)
    assert expected_weighted_avg("wavg") == pytest.approx(3.36)


def test_wavg_blank_and_wavg_zero_match_the_briefs_reference_table():
    """The `fill_null` pair: campaign B has zero `payers` throughout, so the
    surviving weight collapses to 0 in both countries and at the campaign
    total. Everywhere else the two columns agree exactly."""
    for col_id in ("wavg_blank", "wavg_zero"):
        assert expected_weighted_avg(col_id, campaign="A", country="US") == pytest.approx(5.5)
        assert expected_weighted_avg(col_id, campaign="A", country="DE") == pytest.approx(2.0)
        assert expected_weighted_avg(col_id, campaign="A") == pytest.approx(61 / 13)  # 4.692307…
        assert expected_weighted_avg(col_id) == pytest.approx(61 / 13)

    assert expected_weighted_avg("wavg_blank", campaign="B", country="US") is None
    assert expected_weighted_avg("wavg_blank", campaign="B", country="DE") is None
    assert expected_weighted_avg("wavg_blank", campaign="B") is None

    assert expected_weighted_avg("wavg_zero", campaign="B", country="US") == 0.0
    assert expected_weighted_avg("wavg_zero", campaign="B", country="DE") == 0.0
    assert expected_weighted_avg("wavg_zero", campaign="B") == 0.0


def test_wavg_skips_the_nan_leaf_at_a_de():
    """A/DE's two leaves are row 2 (`wa_value=None`) and row 3 (`wa_value=2`,
    `wa_weight=90`). Skipping row 2 gives 2.0; a `fillna(0)`-style bug that
    treated the missing value as 0 instead would give `(0·10 + 2·90)/(10+90)
    = 1.8` — a different, wrong number, not just a slightly-off one."""
    correct = expected_weighted_avg("wavg", campaign="A", country="DE")
    assert correct == pytest.approx(2.0)

    naive_treats_none_as_zero = (0 * 10 + 2 * 90) / (10 + 90)
    assert naive_treats_none_as_zero == pytest.approx(1.8)
    assert correct != pytest.approx(naive_treats_none_as_zero)


def test_wavg_skips_the_zero_weight_leaf_at_b_us():
    """B/US's two leaves are row 4 (`wa_weight=0`) and row 5 (`wa_value=3`,
    `wa_weight=100`). Skipping row 4 leaves only row 5, so the correct value
    is exactly row 5's own value, 3.0. A naive *unweighted* average of both
    leaves' raw values (5 and 3) — the mistake of averaging instead of
    weighting — would instead give 4.0."""
    correct = expected_weighted_avg("wavg", campaign="B", country="US")
    assert correct == pytest.approx(3.0)

    naive_unweighted_average = (5 + 3) / 2
    assert naive_unweighted_average == pytest.approx(4.0)
    assert correct != pytest.approx(naive_unweighted_average)


# --------------------------------------------------------------------------
# Share
# --------------------------------------------------------------------------


def test_share_matches_the_briefs_reference_table():
    assert evaluate(SHARE_SPEC, rows_where(campaign="A", country="US")) == pytest.approx(900 / 1020 * 100)
    assert evaluate(SHARE_SPEC, rows_where(campaign="A", country="DE")) == pytest.approx(100 / 1020 * 100)
    assert evaluate(SHARE_SPEC, rows_where(campaign="A")) == pytest.approx(1000 / 1020 * 100)
    assert evaluate(SHARE_SPEC, rows_where(campaign="B", country="US")) == pytest.approx(10 / 1020 * 100)
    assert evaluate(SHARE_SPEC, rows_where(campaign="B", country="DE")) == pytest.approx(10 / 1020 * 100)
    assert evaluate(SHARE_SPEC, rows_where(campaign="B")) == pytest.approx(20 / 1020 * 100)
    assert evaluate(SHARE_SPEC, rows_where()) == pytest.approx(100.0)


def test_share_grand_total_is_exactly_100_because_cost_sums_to_the_constant():
    """The anchor that proves `den_const` is a window-wide constant and not
    something summed once per leaf: `Σcost` over all eight rows is exactly
    `1020`, the same number declared as `den_const`, so the grand total lands
    on exactly `100.0`. An aggregator that added `1020` once per leaf instead
    of once for the whole window would blow this number far past 100."""
    assert sum(row["cost"] for row in RATIO_ROWS) == 1020
    assert evaluate(SHARE_SPEC, rows_where()) == 100.0
