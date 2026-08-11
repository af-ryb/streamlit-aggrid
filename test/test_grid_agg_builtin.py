"""`stRatio`'s `den_const`, exercised through the built-in aggregator.

`grid_agg_builtin.py` is the new home for every aggregator this coverage plan
adds; this suite covers only what Task 3 adds to it — the `share` column,
whose denominator is `SHARE_SPEC.den_const` (a window-wide constant) rather
than a summed field, and `mixed_den`, which proves that constant *combines*
with a real summed `den` field rather than one silently replacing the other.
`stRatio`'s base semantics already have their regression baseline in
`test_grid_ratio_builtin.py`, which stays frozen and green.

Row indices for the row-group grid mirror `test_grid_ratio_builtin.py`
exactly: same fixture, same two-level grouping (campaign then country), same
eight leaf rows, so a broken `den_const` cannot hide behind a different tree
shape.
"""

from pathlib import Path

import pytest
from playwright.sync_api import Page

from e2e_utils import StreamlitRunner
from grid_dom import assert_number, grand_total_row, read_rows
from ratio_fixture import RATIO_ROWS, RatioSpec, SHARE_SPEC, evaluate, rows_where

ROOT_DIRECTORY = Path(__file__).parent.parent.absolute()
BUILTIN_FILE = ROOT_DIRECTORY / "test" / "grid_agg_builtin.py"

ROWGROUP_GRID = 0
PIVOT_GRID = 1

SHARE_COL = SHARE_SPEC.col_id

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


@pytest.fixture(autouse=True, scope="module")
def streamlit_app():
    with StreamlitRunner(BUILTIN_FILE) as runner:
        yield runner


@pytest.fixture(autouse=True, scope="function")
def go_to_app(page: Page, streamlit_app: StreamlitRunner):
    page.goto(streamlit_app.server_url)
    page.get_by_role("img", name="Running...").is_hidden()
    page.wait_for_selector(".ag-root-wrapper", timeout=60000)
    page.wait_for_function(
        "() => document.querySelectorAll('.ag-root-wrapper').length >= 2",
        timeout=60000,
    )
    page.wait_for_selector('[row-index="14"]', timeout=60000)


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
# Pivot
# --------------------------------------------------------------------------


def pivot_col(country: str) -> str:
    return f"pivot_country_{country}_{SHARE_COL}"


def pivot_total_col() -> str:
    return f"PivotRowTotal_pivot_country__{SHARE_COL}"


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
