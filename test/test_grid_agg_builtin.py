"""`stRatio`'s `den_const`/fallback-to-`sum` behaviour, the
`stRatioOfRatios` aggregator, and the `stWeightedAvg` aggregator, exercised
through the built-in aggregators.

`grid_agg_builtin.py` is the new home for every aggregator this coverage plan
adds; this suite covers what Task 3, Task 4, Task 5 and Task 6 add to it.
Task 3's `share` column has a denominator that is `SHARE_SPEC.den_const` (a
window-wide constant) rather than a summed field, and `mixed_den` proves that
constant *combines* with a real summed `den` field rather than one silently
replacing the other. Task 4 covers grid index 2 — a grid with no ratio
columns at all, proving `stRatio` degrades to a plain `sum` instead of
blanking a column that carries `aggFunc: "stRatio"` with no
`context["stRatio"]` declaration, acquired at runtime through two different
mechanisms (`cost` via `columns_state` merge, `installs` via `initial_state`
— see the "Fallback" section below for why both are runtime-acquired rather
than one being parse-time-declared, as originally scoped). `stRatio`'s base
semantics already have their regression baseline in
`test_grid_ratio_builtin.py`, which stays frozen and green.

Task 5 adds `growth`/`growth_neg` (`stRatioOfRatios`, `GROWTH_SPECS`) to grids
0 and 1, and a fourth grid (index 3, `agg_builtin_grouped_cols`) nesting them
in a column group. The single test that carries the feature is
`test_growth_pivot_cell_direction_diverges_from_its_row_total`: it is the only
assertion in this module that cannot pass against an aggregator reading
`rowNode.allLeafChildren` under pivot mode — the exact defect the retired
marketing JavaScript has and this aggregator exists to remove.

Task 6 adds `wavg`/`wavg_blank`/`wavg_zero` (`stWeightedAvg`, `WEIGHTED_SPECS`)
to grids 0, 1 and 3. `wavg` carries two independent skip rules — a NaN value
(`test_wavg_nan_value_is_skipped_not_treated_as_zero`) and a non-positive
weight (`test_wavg_gate_excludes_the_negative_weight_row`) — plus the
not-the-average-of-children anchor at campaign A
(`test_wavg_group_average_is_not_the_average_of_its_children`); `wavg_blank`/
`wavg_zero` share the `fill_null`-both-ways pair `arpp`/`arpp_blank` already
established for `stRatio`.

Row indices for the row-group grid (index 0) and the fallback grid (index 2)
mirror `test_grid_ratio_builtin.py` exactly: same fixture, same two-level
grouping (campaign then country), same eight leaf rows, so a broken
`den_const` — or a broken fallback — cannot hide behind a different tree
shape.
"""

from pathlib import Path

import pytest
from playwright.sync_api import Page

from e2e_utils import StreamlitRunner
from grid_dom import assert_number, campaign_order, click_header, grand_total_row, read_rows
from ratio_fixture import (
    GROWTH_SPECS,
    GROWTH_SPECS_BY_ID,
    RATIO_ROWS,
    RatioOfRatiosSpec,
    RatioSpec,
    SHARE_SPEC,
    WEIGHTED_SPECS,
    evaluate,
    evaluate_avg_of,
    evaluate_ratio_of_ratios,
    evaluate_ratio_of_ratios_legacy,
    evaluate_weighted_avg,
    expected_ratio_of_ratios,
    expected_weighted_avg,
    rows_where,
)

ROOT_DIRECTORY = Path(__file__).parent.parent.absolute()
BUILTIN_FILE = ROOT_DIRECTORY / "test" / "grid_agg_builtin.py"

ROWGROUP_GRID = 0
PIVOT_GRID = 1
FALLBACK_GRID = 2
GROUPED_COLS_GRID = 3

SHARE_COL = SHARE_SPEC.col_id
GROWTH_COL_IDS = tuple(spec.col_id for spec in GROWTH_SPECS)
WAVG_COL_IDS = tuple(spec.col_id for spec in WEIGHTED_SPECS)

# Body row indices of the fully expanded row-group grid — identical to
# `test_grid_ratio_builtin.py`'s RAW_GRID, same fixture and grouping:
#   0 A            4 A/DE          8  B/US        12 B/DE row 0
#   1 A/US         5 A/DE row 0    9  B/US row 0  13 B/DE row 1
#   2 A/US row 0   6 A/DE row 1    10 B/US row 1
#   3 A/US row 1   7 B            11 B/DE
# The grand total follows at row-index 14; find it with `grand_total_row`.
GROUP_ROW_DIMS = {
    0: {"campaign": "A"},
    1: {"campaign": "A", "country": "US"},
    4: {"campaign": "A", "country": "DE"},
    7: {"campaign": "B"},
    8: {"campaign": "B", "country": "US"},
    11: {"campaign": "B", "country": "DE"},
}
LEAF_ROW_SOURCE = {2: 0, 3: 1, 5: 2, 6: 3, 9: 4, 10: 5, 12: 6, 13: 7}

# Mirrors `grid_agg_builtin.MIXED_DEN_SPEC` exactly — same col_id, same
# fields, same constant. Apps in this repo run via `streamlit
# run`/`StreamlitRunner`, never as an imported module: importing one directly
# executes its top-level `AgGrid()` calls outside a Streamlit run context and
# raises. So the spec is declared independently here rather than shared by
# import, the same way `GROUP_ROW_DIMS` above independently encodes the app's
# grouping structure rather than importing it.
MIXED_DEN_SPEC = RatioSpec(
    col_id="mixed_den",
    header="Cost / (rebate + const)",
    num=("cost",),
    den=("rebate",),
    den_const=200.0,
)

# Mirrors `grid_agg_builtin.GROWTH_BLANK_SPEC` exactly, for the same reason
# `MIXED_DEN_SPEC` above is redeclared rather than imported.
GROWTH_BLANK_SPEC = RatioOfRatiosSpec(
    col_id="growth_blank",
    header="Growth (blank)",
    from_leg={"num": ("ads_d0",), "den": ("inst_d0",)},
    to_leg={"num": ("revenue",), "den": ("payers",)},
)


@pytest.fixture(autouse=True, scope="module")
def streamlit_app():
    with StreamlitRunner(BUILTIN_FILE) as runner:
        yield runner


@pytest.fixture(autouse=True, scope="function")
def go_to_app(page: Page, streamlit_app: StreamlitRunner):
    page.goto(streamlit_app.server_url)
    page.get_by_role("img", name="Running...").is_hidden()
    page.wait_for_selector(".ag-root-wrapper", timeout=60000)
    # Four grids: row-group, pivot, the fallback grid (Task 4), and the
    # grouped-columns grid (Task 5).
    page.wait_for_function(
        "() => document.querySelectorAll('.ag-root-wrapper').length >= 4",
        timeout=60000,
    )
    page.wait_for_selector('[row-index="14"]', timeout=60000)
    # The row-group grid (index 0) and the fallback grid (index 2) share the
    # same two-level grouping, so both reach row-index 14 — the selector
    # above is unscoped and could be satisfied by grid 0 alone while grid 2 is
    # still mounting. Wait on grid 2 specifically so its tests never read a
    # half-rendered tree.
    page.wait_for_function(
        """() => {
             const grid = document.querySelectorAll('.ag-root-wrapper')[2];
             return grid !== undefined && grid.querySelector('[row-index="14"]') !== null;
           }""",
        timeout=60000,
    )
    # Grid 3 (`agg_builtin_grouped_cols`) row-groups by campaign only, so it
    # never reaches row-index 14 — wait on its own last row (the grand total,
    # row-index 2) instead.
    page.wait_for_function(
        """() => {
             const grid = document.querySelectorAll('.ag-root-wrapper')[3];
             return grid !== undefined && grid.querySelector('[row-index="2"]') !== null;
           }""",
        timeout=60000,
    )


def test_share_group_rows_match_the_fixture_at_both_levels(page: Page):
    rows = read_rows(page, ROWGROUP_GRID)

    for row_index, dims in GROUP_ROW_DIMS.items():
        assert_number(
            rows[f"body:{row_index}"][SHARE_COL],
            evaluate(SHARE_SPEC, rows_where(**dims)),
            f"row {row_index} {dims} share",
        )


def test_share_leaf_rows_show_the_per_row_share(page: Page):
    rows = read_rows(page, ROWGROUP_GRID)

    for row_index, source_index in LEAF_ROW_SOURCE.items():
        source_row = RATIO_ROWS[source_index]
        assert_number(
            rows[f"body:{row_index}"][SHARE_COL],
            evaluate(SHARE_SPEC, [source_row]),
            f"leaf {row_index} share",
        )


def test_share_grand_total_is_exactly_100(page: Page):
    """The anchor: `den_const` is added once for the whole grid, not once per
    leaf. `Σcost` across all eight rows is exactly `1020` — the same number
    declared as `den_const` — so the grand total must equal exactly `100.0`.
    An aggregator that folded `den_const` per leaf (multiplying it by the
    child count) would blow this number far past 100, not land close to it.
    """
    total = grand_total_row(read_rows(page, ROWGROUP_GRID))
    assert float(total[SHARE_COL]) == 100.0


def test_den_const_combines_with_a_summed_den_rather_than_replacing_it(page: Page):
    """`share`'s `den` is empty, so nothing above proves `denominator =
    den_const + Σden` actually adds both terms instead of one silently
    overriding the other. `mixed_den` (`cost / (rebate + 200)`) has both:
    checked at a folded group row (campaign A, two levels of children folded
    through `sums`) and at the grand total (every leaf folded), so a `+` that
    quietly became a `den_const`-only or `den`-only computation would show up
    at both.
    """
    rows = read_rows(page, ROWGROUP_GRID)

    assert_number(
        rows["body:0"][MIXED_DEN_SPEC.col_id],
        evaluate(MIXED_DEN_SPEC, rows_where(campaign="A")),
        "campaign A mixed_den",
    )
    assert_number(
        grand_total_row(rows)[MIXED_DEN_SPEC.col_id],
        evaluate(MIXED_DEN_SPEC, rows_where()),
        "grand total mixed_den",
    )


# --------------------------------------------------------------------------
# stRatioOfRatios (Task 5): growth / growth_neg, row grouping
# --------------------------------------------------------------------------


def test_growth_group_rows_match_the_fixture_at_both_levels(page: Page):
    rows = read_rows(page, ROWGROUP_GRID)

    for row_index, dims in GROUP_ROW_DIMS.items():
        cells = rows[f"body:{row_index}"]
        for col_id in GROWTH_COL_IDS:
            assert_number(
                cells[col_id],
                expected_ratio_of_ratios(col_id, **dims),
                f"row {row_index} {dims} {col_id}",
            )


def test_growth_leaf_rows_show_the_per_row_ratio(page: Page):
    """Not aggregator coverage: a leaf row is a raw data row, so its cell is
    `ratio_dataframe()`'s precomputed value, never `stRatioOfRatiosAggFunc`'s
    output — `stRatioOfRatios` only runs on group rows. This checks that the
    precomputed column and the rendered cell agree with `evaluate_ratio_of_
    ratios` computed independently here, the same leaf/group agreement check
    `test_grid_ratio_builtin.py`'s own leaf-row test makes for `stRatio`."""
    rows = read_rows(page, ROWGROUP_GRID)

    for row_index, source_index in LEAF_ROW_SOURCE.items():
        source_row = RATIO_ROWS[source_index]
        cells = rows[f"body:{row_index}"]
        for spec in GROWTH_SPECS:
            assert_number(
                cells[spec.col_id],
                evaluate_ratio_of_ratios([source_row], spec),
                f"leaf {row_index} {spec.col_id}",
            )


def test_growth_grand_total_matches_the_fixture(page: Page):
    cells = grand_total_row(read_rows(page, ROWGROUP_GRID))

    for col_id in GROWTH_COL_IDS:
        assert_number(cells[col_id], expected_ratio_of_ratios(col_id), f"total {col_id}")


def test_growth_neg_pins_the_gt_zero_to_ne_zero_delta(page: Page):
    """The Global Constraints' deliberate behaviour change: `growth_neg`'s
    `from` leg (`credits_d0`/`inst_d0`) is negative for campaign B, so
    `ratio_fixture.evaluate_ratio_of_ratios_legacy` — the retired JavaScript's
    `> 0` gate — renders B/US and B/DE blank. The declarative aggregator's
    `!== 0` gate divides anyway: -1.0000 at B/US, -2.0000 at B/DE.
    """
    rows = read_rows(page, ROWGROUP_GRID)

    b_us = rows["body:8"]["growth_neg"]
    b_de = rows["body:11"]["growth_neg"]

    assert_number(
        b_us,
        expected_ratio_of_ratios("growth_neg", campaign="B", country="US"),
        "B/US growth_neg",
    )
    assert_number(
        b_de,
        expected_ratio_of_ratios("growth_neg", campaign="B", country="DE"),
        "B/DE growth_neg",
    )

    # Anchors: hand-verified against the fixture (Σcredits_d0/Σinst_d0 is
    # exactly -0.1 at B/US and -0.2 at B/DE; Σads_d1/Σinst_d1, the `to` leg,
    # is 0.1 and 0.4 respectively).
    assert float(b_us) == pytest.approx(-1.0)
    assert float(b_de) == pytest.approx(-2.0)

    # What the retired JavaScript rendered instead of those two numbers.
    growth_neg_spec = GROWTH_SPECS_BY_ID["growth_neg"]
    assert evaluate_ratio_of_ratios_legacy(
        rows_where(campaign="B", country="US"), growth_neg_spec
    ) is None
    assert evaluate_ratio_of_ratios_legacy(
        rows_where(campaign="B", country="DE"), growth_neg_spec
    ) is None


# --------------------------------------------------------------------------
# stWeightedAvg (Task 6): wavg / wavg_blank / wavg_zero, row grouping
# --------------------------------------------------------------------------


def test_wavg_group_rows_match_the_fixture_at_both_levels(page: Page):
    rows = read_rows(page, ROWGROUP_GRID)

    for row_index, dims in GROUP_ROW_DIMS.items():
        cells = rows[f"body:{row_index}"]
        for col_id in WAVG_COL_IDS:
            assert_number(
                cells[col_id],
                expected_weighted_avg(col_id, **dims),
                f"row {row_index} {dims} {col_id}",
            )


def test_wavg_leaf_rows_show_the_per_row_value(page: Page):
    """Not aggregator coverage: a leaf row is a raw data row, so its cell is
    `ratio_dataframe()`'s precomputed value, never `stWeightedAvgAggFunc`'s
    output — `stWeightedAvg` only runs on group rows. This checks that the
    precomputed column and the rendered cell agree with `evaluate_weighted_avg`
    computed independently here, the same leaf/group agreement check
    `test_grid_ratio_builtin.py`'s own leaf-row test makes for `stRatio`."""
    rows = read_rows(page, ROWGROUP_GRID)

    for row_index, source_index in LEAF_ROW_SOURCE.items():
        source_row = RATIO_ROWS[source_index]
        cells = rows[f"body:{row_index}"]
        for spec in WEIGHTED_SPECS:
            assert_number(
                cells[spec.col_id],
                evaluate_weighted_avg([source_row], spec),
                f"leaf {row_index} {spec.col_id}",
            )


def test_wavg_grand_total_matches_the_fixture(page: Page):
    cells = grand_total_row(read_rows(page, ROWGROUP_GRID))

    for col_id in WAVG_COL_IDS:
        assert_number(cells[col_id], expected_weighted_avg(col_id), f"total {col_id}")


def test_wavg_nan_value_is_skipped_not_treated_as_zero(page: Page):
    """`wavg`'s skip rule, value half: row 2 (A/DE's first leaf) has
    `wa_value = None` (NaN once in a DataFrame). A/DE must reduce to row 3
    alone — `2·90/90 = 2.0000` — not treat the missing value as `0`, which
    would instead count the leaf's weight (10) with a value of 0 and give
    `(0·10 + 2·90)/(10+90) = 1.8000`.
    """
    rows = read_rows(page, ROWGROUP_GRID)
    a_de = rows["body:4"]["wavg"]

    assert_number(
        a_de, expected_weighted_avg("wavg", campaign="A", country="DE"), "A/DE wavg"
    )
    assert float(a_de) == pytest.approx(2.0)

    # What treating the missing value as 0 instead of skipping the leaf
    # entirely would produce: the leaf's weight still counted, its value
    # silently zeroed.
    value_uncounted = (0 * 10 + 2 * 90) / (10 + 90)
    assert value_uncounted == pytest.approx(1.8)
    assert float(a_de) != pytest.approx(value_uncounted)


def test_wavg_gate_excludes_the_negative_weight_row(page: Page):
    """`wavg`'s skip rule, weight half — the `weight > 0` gate. Row 4 (B/US's
    first leaf) carries `wa_weight = -100`, deliberately chosen to *cancel*
    row 5's `+100` rather than being `0`: a `0`-weight leaf contributes `0` to
    both accumulators whether or not it is skipped, so no test built on a
    zero could ever discriminate a missing gate (see the `WEIGHTED_SPECS`
    doc comment and `DEGENERATE_NODES` in `ratio_fixture.py`). `-100` makes a
    missing gate observable at three levels:

    - B/US reduces to row 5 alone: `3·100/100 = 3.0000`. Summing weights
      regardless of sign gets `-100 + 100 = 0` and *blanks* the cell instead
      — division by zero, not merely a wrong number.
    - Campaign B (rows 5-7, row 4 skipped) reads `4.0000`. Without the gate,
      row 4's `wa_value=5` at weight `-100` survives: `(5·-100 + 3·100 +
      4·50 + 6·50)/(-100+100+50+50) = 300/100 = 3.0000`.
    - The grand total reads `3.3600`. Without the gate:
      `(208 + 300)/(100 + 100) = 508/200 = 2.5400` (the `208`/`100` from
      campaign A is unaffected — its own skip rule only ever discards row 2's
      NaN value, never a weight).
    """
    rows = read_rows(page, ROWGROUP_GRID)

    b_us = rows["body:8"]["wavg"]
    b_total = rows["body:7"]["wavg"]
    total = grand_total_row(rows)["wavg"]

    assert_number(
        b_us, expected_weighted_avg("wavg", campaign="B", country="US"), "B/US wavg"
    )
    assert_number(b_total, expected_weighted_avg("wavg", campaign="B"), "campaign B wavg")
    assert_number(total, expected_weighted_avg("wavg"), "grand total wavg")

    assert float(b_us) == pytest.approx(3.0)
    assert float(b_total) == pytest.approx(4.0)
    assert float(total) == pytest.approx(3.36)

    # What each would read with the weight sign left ungated instead.
    weight_ungated_b_total = (5 * -100 + 3 * 100 + 4 * 50 + 6 * 50) / (-100 + 100 + 50 + 50)
    weight_ungated_total = (208 + 300) / (100 + 100)
    assert weight_ungated_b_total == pytest.approx(3.0)
    assert weight_ungated_total == pytest.approx(2.54)
    assert float(b_total) != pytest.approx(weight_ungated_b_total)
    assert float(total) != pytest.approx(weight_ungated_total)


def test_wavg_group_average_is_not_the_average_of_its_children(page: Page):
    """Campaign A's total (`2.0800`) is not the mean of its two countries'
    values (`2.8000` and `2.0000`, which average to `2.4000`) — proof the
    aggregator re-derives `Σ(vᵢ·wᵢ)/Σwᵢ` at the parent rather than averaging
    already-computed child ratios. Campaign B cannot make this point: it is a
    declared degenerate node (`DEGENERATE_NODES` in `ratio_fixture.py`) where
    the two coincide by construction.
    """
    rows = read_rows(page, ROWGROUP_GRID)

    campaign_a = rows["body:0"]["wavg"]
    a_us = rows["body:1"]["wavg"]
    a_de = rows["body:4"]["wavg"]

    assert_number(campaign_a, expected_weighted_avg("wavg", campaign="A"), "campaign A wavg")

    avg_of_children = evaluate_avg_of(
        [
            expected_weighted_avg("wavg", campaign="A", country="US"),
            expected_weighted_avg("wavg", campaign="A", country="DE"),
        ]
    )

    assert float(campaign_a) == pytest.approx(2.08)
    assert float(a_us) == pytest.approx(2.8)
    assert float(a_de) == pytest.approx(2.0)
    assert avg_of_children == pytest.approx(2.4)
    assert float(campaign_a) != pytest.approx(avg_of_children)


def test_wavg_fill_null_both_ways(page: Page):
    """`wavg_blank`/`wavg_zero` weight by `payers`, zero throughout campaign
    B (the same fact `arpp`/`arpp_blank` already exploit for `stRatio`), so
    the surviving weight collapses to `0` at every level within campaign B —
    the campaign total and both pivot cells — and each column falls back to
    its own `fill_null`: an empty cell for `wavg_blank`, `0.0000` for
    `wavg_zero`.
    """
    rows = read_rows(page, ROWGROUP_GRID)

    for row_index in (7, 8, 11):  # campaign B, B/US, B/DE
        assert rows[f"body:{row_index}"]["wavg_blank"] == ""
        assert float(rows[f"body:{row_index}"]["wavg_zero"]) == pytest.approx(0.0)


# --------------------------------------------------------------------------
# Pivot
# --------------------------------------------------------------------------


def pivot_col(country: str, col_id: str = SHARE_COL) -> str:
    return f"pivot_country_{country}_{col_id}"


def pivot_total_col(col_id: str = SHARE_COL) -> str:
    return f"PivotRowTotal_pivot_country__{col_id}"


def test_share_pivot_cells_compute_their_own_share(page: Page):
    """`share` has no `den` field to fold — only `den_const` — so a pivot cell
    that dropped the constant per pivot key would render blank instead of
    wrong. This proves the constant reaches every pivot cell, and that each
    cell computes its own (campaign, country) share rather than leaking its
    row's total."""
    rows = read_rows(page, PIVOT_GRID)

    for row_index, campaign in ((0, "A"), (1, "B")):
        cells = rows[f"body:{row_index}"]
        for country in ("US", "DE"):
            assert_number(
                cells[pivot_col(country)],
                evaluate(SHARE_SPEC, rows_where(campaign=campaign, country=country)),
                f"{campaign}/{country} share",
            )


def test_share_pivot_row_totals_match_the_fixture(page: Page):
    rows = read_rows(page, PIVOT_GRID)

    for row_index, campaign in ((0, "A"), (1, "B")):
        assert_number(
            rows[f"body:{row_index}"][pivot_total_col()],
            evaluate(SHARE_SPEC, rows_where(campaign=campaign)),
            f"{campaign} row total share",
        )


def test_share_pivot_grand_total_is_exactly_100(page: Page):
    """Same anchor as the row-group grid's, reached through the pivot's row
    total instead: `den_const` added once for the grid, not once per pivot
    key."""
    total = grand_total_row(read_rows(page, PIVOT_GRID))
    assert float(total[pivot_total_col()]) == 100.0


# --------------------------------------------------------------------------
# stRatioOfRatios (Task 5): growth / growth_neg, pivot
# --------------------------------------------------------------------------


def test_growth_pivot_cells_match_the_fixture(page: Page):
    """Every pivot cell re-derives both inner ratios at its own (campaign,
    country) node — the defect the retired marketing JavaScript has (it sums
    over `rowNode.allLeafChildren`, the whole row, regardless of pivot key) is
    what this whole aggregator exists to fix. See
    `test_growth_pivot_cell_direction_diverges_from_its_row_total` for the one
    assertion that cannot pass while that defect is still present."""
    rows = read_rows(page, PIVOT_GRID)

    for row_index, campaign in ((0, "A"), (1, "B")):
        cells = rows[f"body:{row_index}"]
        for country in ("US", "DE"):
            for col_id in GROWTH_COL_IDS:
                assert_number(
                    cells[pivot_col(country, col_id)],
                    expected_ratio_of_ratios(col_id, campaign=campaign, country=country),
                    f"{campaign}/{country} {col_id}",
                )


def test_growth_pivot_row_totals_match_the_fixture(page: Page):
    rows = read_rows(page, PIVOT_GRID)

    for row_index, campaign in ((0, "A"), (1, "B")):
        for col_id in GROWTH_COL_IDS:
            assert_number(
                rows[f"body:{row_index}"][pivot_total_col(col_id)],
                expected_ratio_of_ratios(col_id, campaign=campaign),
                f"{campaign} row total {col_id}",
            )


def test_growth_pivot_grand_total_row_matches_the_fixture(page: Page):
    """One level up: each country column of the total row carries that
    country's ratio across both campaigns, and the row total carries the
    overall one."""
    total = grand_total_row(read_rows(page, PIVOT_GRID))

    for country in ("US", "DE"):
        for col_id in GROWTH_COL_IDS:
            assert_number(
                total[pivot_col(country, col_id)],
                expected_ratio_of_ratios(col_id, country=country),
                f"total/{country} {col_id}",
            )
    for col_id in GROWTH_COL_IDS:
        assert_number(
            total[pivot_total_col(col_id)],
            expected_ratio_of_ratios(col_id),
            f"grand total {col_id}",
        )


def test_growth_pivot_cell_direction_diverges_from_its_row_total(page: Page):
    """The test that carries the feature. Campaign A's overall `growth` is
    above 1 (its `to`-period ARPU grew relative to `from`), but the A/US
    pivot cell alone is below 1 (it shrank) — the two diverge in *direction*,
    not just magnitude. An aggregator that summed over
    `params.rowNode.allLeafChildren` under pivot mode — the exact bug the
    retired marketing JavaScript has — would show campaign A's row total in
    the A/US cell too, so both numbers would read "above 1" and this
    assertion would fail. Every other pivot assertion in this module can pass
    against that broken aggregator (each pivot key happens to land on the
    same side of 1 as its row); this one cannot, which is why the fixture's
    `ads_d0`/`ads_d1` values were chosen the way they were (see
    `GROWTH_SPECS`'s docstring in `ratio_fixture.py`).
    """
    rows = read_rows(page, PIVOT_GRID)
    campaign_a = rows["body:0"]

    cell = float(campaign_a[pivot_col("US", "growth")])
    row_total = float(campaign_a[pivot_total_col("growth")])

    assert_number(
        campaign_a[pivot_col("US", "growth")],
        expected_ratio_of_ratios("growth", campaign="A", country="US"),
        "A/US growth",
    )
    assert_number(
        campaign_a[pivot_total_col("growth")],
        expected_ratio_of_ratios("growth", campaign="A"),
        "campaign A growth total",
    )

    assert cell < 1, f"A/US growth should be below 1, got {cell}"
    assert row_total > 1, f"campaign A growth total should be above 1, got {row_total}"

    # Anchors, hand-verified against the fixture: A/US is Σads_d1/Σads_d0 =
    # 90/100 = 0.9 (inst_d0 == inst_d1 on every row, so both denominators
    # cancel — see GROWTH_SPECS's docstring); campaign A overall is
    # Σads_d1/Σads_d0 = 130/110.
    assert cell == pytest.approx(0.9)
    assert row_total == pytest.approx(130 / 110)


# --------------------------------------------------------------------------
# stWeightedAvg (Task 6): wavg / wavg_blank / wavg_zero, pivot
# --------------------------------------------------------------------------


def test_wavg_pivot_cells_match_the_fixture(page: Page):
    """Every pivot cell re-derives `Σ(vᵢ·wᵢ)/Σwᵢ` at its own (campaign,
    country) node. `wavg` is not one of `ratio_fixture.PIVOT_BLIND_CELLS`'
    entries for campaign B — B/US is `3.0000`, B/DE is `5.0000`, and
    campaign B's row total is `4.0000`, all three different — so this also
    proves the pivot key reaches `stWeightedAvg`, not just
    `stRatio`/`stRatioOfRatios`.
    """
    rows = read_rows(page, PIVOT_GRID)

    for row_index, campaign in ((0, "A"), (1, "B")):
        cells = rows[f"body:{row_index}"]
        for country in ("US", "DE"):
            for col_id in WAVG_COL_IDS:
                assert_number(
                    cells[pivot_col(country, col_id)],
                    expected_weighted_avg(col_id, campaign=campaign, country=country),
                    f"{campaign}/{country} {col_id}",
                )


def test_wavg_pivot_row_totals_match_the_fixture(page: Page):
    rows = read_rows(page, PIVOT_GRID)

    for row_index, campaign in ((0, "A"), (1, "B")):
        for col_id in WAVG_COL_IDS:
            assert_number(
                rows[f"body:{row_index}"][pivot_total_col(col_id)],
                expected_weighted_avg(col_id, campaign=campaign),
                f"{campaign} row total {col_id}",
            )


def test_wavg_pivot_grand_total_row_matches_the_fixture(page: Page):
    total = grand_total_row(read_rows(page, PIVOT_GRID))

    for country in ("US", "DE"):
        for col_id in WAVG_COL_IDS:
            assert_number(
                total[pivot_col(country, col_id)],
                expected_weighted_avg(col_id, country=country),
                f"total/{country} {col_id}",
            )
    for col_id in WAVG_COL_IDS:
        assert_number(
            total[pivot_total_col(col_id)],
            expected_weighted_avg(col_id),
            f"grand total {col_id}",
        )


# --------------------------------------------------------------------------
# Fallback (Task 4): stRatio degrades to sum without a declaration
# --------------------------------------------------------------------------
#
# `grid_agg_builtin.fallback_grid_options()` declares no `RATIO_COLUMNS` at
# all: both `cost` and `installs` carry `aggFunc: "sum"` in `columnDefs`.
#
# The brief's original framing called for one column declaring
# `aggFunc: "stRatio"` directly in `columnDefs` with no `context` — the
# "parse-time" path. That construction is unreachable through a colDef that
# Python validated: `validate_ratio_columns` (`ratio.py`) rejects *any*
# colDef declaring `aggFunc: "stRatio"` with no `context["stRatio"]`,
# unconditionally, before the grid options ever leave Python — pinned by
# `test/unit/test_ratio_validation.py::test_agg_func_without_a_context_is_rejected`.
# That guard runs over every column in the *original* `columnDefs`
# regardless of DataFrame/rowData mode: any column that reaches
# `stRatioAggFunc` with `aggFunc === "stRatio"` because it was named that
# way in the colDef Python built is therefore also guaranteed a structurally
# valid `context`, meaning `readStRatioConfig` cannot return `null` for it.
# `null` is only reachable for a column whose `aggFunc` became `"stRatio"`
# *after* Python validated it — runtime acquisition, unconditionally. That
# is also exactly the real-world bug this task exists to fix: the columns
# tool panel's aggregation picker is itself a runtime mutation Python never
# sees.
#
# `cost` and `installs` each exercise a different, genuine runtime-mutation
# route — both existing, documented `AgGrid()` features, both entirely
# outside `columnDefs` so `validate_ratio_columns` never inspects either and
# `registerStRatio`'s `columnDefs` walk never attaches a comparator to
# either:
#
# - `installs` is switched to `stRatio` via the raw `initial_state` prop
#   (`GridState.aggregation.aggregationModel`), applied pre-paint, before
#   the grid is created.
# - `cost` is switched to `stRatio` via `columns_state` in `"merge"` mode
#   (a `ColumnState[]` overlay), applied post-creation in `onGridReady`.
#
# Neither ever carries a comparator, so both sort assertions below prove the
# missing comparator doesn't leave the column unsorted: a regression back to
# the old blanking behaviour would make every group cell empty text, which
# does not sort by magnitude at all.
#
# They do NOT, on their own, discriminate a fallback that wrongly returned an
# `StAggValue` instead of a plain number — measured, not assumed: AG-Grid
# 36's own default comparator (`ag-grid-community.js`'s `_defaultComparator`,
# used whenever no column comparator is configured, exactly the case here)
# already unwraps a `toNumber()`-bearing object before comparing, the same
# way `stAggComparator` does. So an `StAggValue` sorts identically to a plain
# number under the *default* comparator too, for a non-null result. The
# `stRatioAggFunc` docstring covers why the fallback returns a plain number
# regardless (a `valueFormatter` written for a raw number, on a column that
# started life as `aggFunc: "sum"`, must keep working when the column is
# switched to `stRatio` purely at runtime) — that reason alone is decisive
# and does not depend on this sorting behaviour.


def test_fallback_cost_group_and_grand_total_sum_rather_than_blank(page: Page):
    """`cost` acquires `aggFunc: "stRatio"` only through
    `FALLBACK_COLUMNS_STATE` (`columns_state_mode="merge"`), applied after
    the grid is created — `registerStRatio`'s `columnDefs` walk never saw it,
    since `columnDefs` declares `aggFunc: "sum"` for this column. Before this
    task, a column that reached the aggregator this way rendered blank; the
    fallback must show the plain `Σcost` instead: campaign A =
    800+100+90+10 = 1000, campaign B = 9+1+8+2 = 20 (the same eight
    `RATIO_ROWS`, and the same grand total `SHARE_SPEC`'s `den_const` anchor
    uses)."""
    rows = read_rows(page, FALLBACK_GRID)
    assert_number(rows["body:0"]["cost"], 1000.0, "campaign A cost")
    assert_number(rows["body:7"]["cost"], 20.0, "campaign B cost")
    assert float(grand_total_row(rows)["cost"]) == pytest.approx(1020.0)


def test_fallback_installs_acquired_at_runtime_sums_rather_than_blanks(page: Page):
    """`installs` acquires `aggFunc: "stRatio"` only through
    `FALLBACK_INITIAL_STATE` (`GridState.aggregation.aggregationModel`),
    applied pre-paint — `registerStRatio`'s `columnDefs` walk never saw it
    either, since `columnDefs` declares `aggFunc: "sum"` for this column too.
    `Σinstalls`: campaign A = 2+8+10+80 = 100, campaign B = 10+90+20+80 =
    200, grand total = 300."""
    rows = read_rows(page, FALLBACK_GRID)
    assert_number(rows["body:0"]["installs"], 100.0, "campaign A installs")
    assert_number(rows["body:7"]["installs"], 200.0, "campaign B installs")
    assert float(grand_total_row(rows)["installs"]) == pytest.approx(300.0)


def test_fallback_cost_sorts_numerically_with_no_comparator(page: Page):
    """`cost` (1000 for A, 20 for B) never carries a comparator: it was
    `aggFunc: "sum"` at parse time, and only became `stRatio` through
    `columns_state` (merge mode) — a path `registerStRatio`'s `columnDefs`
    walk cannot see, so this column sorts entirely under AG-Grid's own
    default comparator. Proves the fallback produces genuinely-sortable
    numeric group values rather than the old blank cells (which do not order
    by magnitude at all); see the "Fallback" section note above for why this
    does not additionally discriminate a plain `number` from an `StAggValue`
    on AG-Grid 36 specifically."""
    click_header(page, FALLBACK_GRID, "cost", "ascending")
    assert campaign_order(page, FALLBACK_GRID) == ["B", "A"]

    click_header(page, FALLBACK_GRID, "cost", "descending")
    assert campaign_order(page, FALLBACK_GRID) == ["A", "B"]


def test_fallback_installs_sorts_numerically_with_no_comparator(page: Page):
    """Same claim as `test_fallback_cost_sorts_numerically_with_no_comparator`,
    through the other runtime-mutation route: `installs` (100 for A, 200 for
    B) was `aggFunc: "sum"` at parse time and only became `stRatio` through
    the raw `initial_state` prop, also invisible to `registerStRatio`'s
    `columnDefs` walk, so it too sorts entirely under AG-Grid's default
    comparator with no comparator of its own."""
    click_header(page, FALLBACK_GRID, "installs", "ascending")
    assert campaign_order(page, FALLBACK_GRID) == ["A", "B"]

    click_header(page, FALLBACK_GRID, "installs", "descending")
    assert campaign_order(page, FALLBACK_GRID) == ["B", "A"]


# --------------------------------------------------------------------------
# stRatioOfRatios (Task 5): sorting
# --------------------------------------------------------------------------


def test_growth_nulls_sort_last_in_both_directions(page: Page):
    """`growth_blank` (declared locally in this suite and in
    `grid_agg_builtin.py`, not in `ratio_fixture.py` — its `to` leg
    denominator is `payers`, zero throughout campaign B, the same fact
    `arpp`/`arpp_blank` already exploit for `stRatio`) is a real number for
    campaign A and blank for campaign B. It is the only column in this module
    that can demonstrate nulls-last for `stRatioOfRatios`: every leg
    `growth`/`growth_neg` use (`ads_d0`/`inst_d0`/`ads_d1`/`inst_d1`/
    `credits_d0`) is nonzero on every row of this fixture, so neither ever
    collapses.
    """
    click_header(page, ROWGROUP_GRID, "growth_blank", "ascending")
    assert campaign_order(page, ROWGROUP_GRID) == ["A", "B"], "ascending: nulls last"

    click_header(page, ROWGROUP_GRID, "growth_blank", "descending")
    assert campaign_order(page, ROWGROUP_GRID) == ["A", "B"], "descending: nulls last"


def test_growth_caller_supplied_comparator_is_left_alone(page: Page):
    """`growth` on the row-group grid carries a reversed JsCode comparator
    (campaign A totals 1.1818..., campaign B totals 1.6667...); both
    directions are the opposite of what the fork's own comparator produces,
    so this cannot pass if `registerAggFunc` overwrote it."""
    click_header(page, ROWGROUP_GRID, "growth", "ascending")
    assert campaign_order(page, ROWGROUP_GRID) == ["B", "A"]

    click_header(page, ROWGROUP_GRID, "growth", "descending")
    assert campaign_order(page, ROWGROUP_GRID) == ["A", "B"]


def test_wavg_blank_nulls_sort_last_in_both_directions(page: Page):
    """`wavg_blank` is a real number for campaign A and blank for campaign B
    (its weight, `payers`, is `0` throughout B) — the same nulls-last role
    `arpp_blank` plays for `stRatio` and `growth_blank` plays for
    `stRatioOfRatios`. `wavg`/`wavg_zero` never blank on this fixture, so
    `wavg_blank` is the only `stWeightedAvg` column here that can demonstrate
    this.
    """
    click_header(page, ROWGROUP_GRID, "wavg_blank", "ascending")
    assert campaign_order(page, ROWGROUP_GRID) == ["A", "B"], "ascending: nulls last"

    click_header(page, ROWGROUP_GRID, "wavg_blank", "descending")
    assert campaign_order(page, ROWGROUP_GRID) == ["A", "B"], "descending: nulls last"


# --------------------------------------------------------------------------
# stRatioOfRatios (Task 5): columns nested in a column group
# --------------------------------------------------------------------------


def test_the_comparator_reaches_growth_columns_nested_in_a_column_group(page: Page):
    """A walk that stopped at the top level would install no comparator on a
    `stRatioOfRatios` column nested inside `columnDefs[*].children`, and
    ascending would fall back to AG-Grid's native nulls-first order —
    ["B", "A"] instead of ["A", "B"]. `growth_blank` is nested here too
    (unlike on the pivot grid) specifically so this discriminates: `growth`/
    `growth_neg` never null in this fixture, so sorting by either would pass
    under AG-Grid's own default comparator too and prove nothing about the
    descent into `children`."""
    click_header(page, GROUPED_COLS_GRID, "growth_blank", "ascending")
    assert campaign_order(page, GROUPED_COLS_GRID) == ["A", "B"], "ascending: nulls last"

    click_header(page, GROUPED_COLS_GRID, "growth_blank", "descending")
    assert campaign_order(page, GROUPED_COLS_GRID) == ["A", "B"], "descending: nulls last"


def test_growth_columns_still_aggregate_when_nested_in_a_column_group(page: Page):
    """Nesting must not disturb the aggregation itself — spot-checked at
    campaign A, the grid's only row-group level here."""
    rows = read_rows(page, GROUPED_COLS_GRID)
    campaign_a = rows["body:0"]

    for col_id in GROWTH_COL_IDS:
        assert_number(
            campaign_a[col_id],
            expected_ratio_of_ratios(col_id, campaign="A"),
            f"grouped-cols campaign A {col_id}",
        )
    assert_number(
        campaign_a["growth_blank"],
        evaluate_ratio_of_ratios(rows_where(campaign="A"), GROWTH_BLANK_SPEC),
        "grouped-cols campaign A growth_blank",
    )


# --------------------------------------------------------------------------
# stWeightedAvg (Task 6): columns nested in a column group
# --------------------------------------------------------------------------


def test_the_comparator_reaches_wavg_columns_nested_in_a_column_group(page: Page):
    """Same descent-into-`children` proof as
    `test_the_comparator_reaches_growth_columns_nested_in_a_column_group`,
    for the `stWeightedAvg` group (`weightedAvgMetrics`) instead: `wavg`/
    `wavg_zero` never null in this fixture, so `wavg_blank` is the only
    column here that can discriminate a comparator that failed to reach a
    nested `stWeightedAvg` column — `eachColDef`'s descent is a shared
    utility, but this is what proves it actually ran for this aggregator's
    own `registerAggFunc` call, not just `stRatioOfRatios`'s.
    """
    click_header(page, GROUPED_COLS_GRID, "wavg_blank", "ascending")
    assert campaign_order(page, GROUPED_COLS_GRID) == ["A", "B"], "ascending: nulls last"

    click_header(page, GROUPED_COLS_GRID, "wavg_blank", "descending")
    assert campaign_order(page, GROUPED_COLS_GRID) == ["A", "B"], "descending: nulls last"


def test_wavg_columns_still_aggregate_when_nested_in_a_column_group(page: Page):
    """Nesting must not disturb the aggregation itself — spot-checked at
    campaign A, the grid's only row-group level here."""
    rows = read_rows(page, GROUPED_COLS_GRID)
    campaign_a = rows["body:0"]

    for col_id in WAVG_COL_IDS:
        assert_number(
            campaign_a[col_id],
            expected_weighted_avg(col_id, campaign="A"),
            f"grouped-cols campaign A {col_id}",
        )
