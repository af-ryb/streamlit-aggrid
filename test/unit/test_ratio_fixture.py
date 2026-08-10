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
    PIVOT_BLIND_CELLS,
    RATIO_ROWS,
    RATIO_SPECS,
    RATIO_SPECS_BY_ID,
    evaluate,
    evaluate_avg_of,
    evaluate_legacy,
    expected,
    expected_legacy,
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


def test_campaign_totals_differ_from_the_average_of_their_country_ratios():
    """Which (column, campaign) nodes are blind to an averaging aggregator is
    a property of the data, so measure it and compare against the declared
    set. Asserting both directions means the constant cannot rot: a fixture
    edit that creates a new blind spot fails, and so does one that removes a
    listed spot without updating the list."""
    measured = {
        (spec.col_id, campaign)
        for spec in RATIO_SPECS
        for campaign in CAMPAIGNS
        if _same(
            evaluate(spec, rows_where(campaign=campaign)),
            evaluate_avg_of(
                evaluate(spec, rows_where(campaign=campaign, country=k))
                for k in COUNTRIES
            ),
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
    cannot detect that. Same two-directional check as the averaging trap."""
    measured = {
        (spec.col_id, campaign, country)
        for spec in RATIO_SPECS
        for campaign, country in CELLS
        if _same(
            evaluate(spec, rows_where(campaign=campaign, country=country)),
            evaluate(spec, rows_where(campaign=campaign)),
        )
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
