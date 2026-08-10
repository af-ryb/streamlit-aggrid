"""Pin what the consumer's JavaScript `ratioSum` renders, level by level.

This suite is the **baseline** the declarative aggregator will be measured
against. It does not assert that the JavaScript is right — it asserts what the
JavaScript *does*, including where that is wrong, so the replacement's
behaviour changes are a diff against a recorded fact instead of a memory.

Three groups of assertions:

1. Row grouping reproduces ``ratio_fixture.evaluate_legacy`` exactly at every
   grouping level and at the grand-total row.
2. Leaf rows render the precomputed dataframe scalar, which follows the
   *specified* semantics — so a spec/legacy divergence is visible as a leaf row
   disagreeing with the group row directly above it.
3. Pivot cells ignore the pivot key. ``ratioSum`` sums
   ``rowNode.allLeafChildren``, which returns every leaf under the row node
   regardless of pivot column, so each pivot cell shows the row's total. This
   is recorded as a defect-in-place, with the correct value alongside it.

Row addressing goes through ``row-index``: AG-Grid positions rows absolutely,
so DOM order does not track visual order and reading in DOM order produces
false results.
"""

from pathlib import Path

import pytest
from playwright.sync_api import Page

from e2e_utils import StreamlitRunner
from ratio_fixture import (
    RATIO_ROWS,
    RATIO_SPECS,
    as_text,
    evaluate,
    expected,
    expected_legacy,
)

ROOT_DIRECTORY = Path(__file__).parent.parent.absolute()
RATIO_JS_FILE = ROOT_DIRECTORY / "test" / "grid_ratio_js.py"

RATIO_COL_IDS = tuple(spec.col_id for spec in RATIO_SPECS)

# Body row indices of the row-group grid, which renders fully expanded:
#   0 A            4 A/DE          8  B/US        12 B/DE row 0
#   1 A/US         5 A/DE row 0    9  B/US row 0  13 B/DE row 1
#   2 A/US row 0   6 A/DE row 1    10 B/US row 1
#   3 A/US row 1   7 B            11 B/DE
# The grand total follows at index 14; locate it with `grand_total_row`, which
# does not assume which container AG-Grid renders it into.
GROUP_ROW_DIMS = {
    0: {"campaign": "A"},
    1: {"campaign": "A", "country": "US"},
    4: {"campaign": "A", "country": "DE"},
    7: {"campaign": "B"},
    8: {"campaign": "B", "country": "US"},
    11: {"campaign": "B", "country": "DE"},
}
LEAF_ROW_SOURCE = {2: 0, 3: 1, 5: 2, 6: 3, 9: 4, 10: 5, 12: 6, 13: 7}

ROWGROUP_GRID = 0
PIVOT_GRID = 1

_READ_ROWS = """
(gridIndex) => {
  const grid = document.querySelectorAll('.ag-root-wrapper')[gridIndex];
  const rows = {};
  for (const row of grid.querySelectorAll('.ag-row')) {
    const section = row.closest('.ag-floating-bottom') ? 'bottom'
                  : row.closest('.ag-floating-top') ? 'top' : 'body';
    const key = section + ':' + row.getAttribute('row-index');
    // A row is split across pinned/centre containers; merge the fragments.
    const cells = rows[key] || (rows[key] = {});
    for (const cell of row.querySelectorAll('.ag-cell')) {
      cells[cell.getAttribute('col-id')] = cell.textContent.trim();
    }
  }
  return rows;
}
"""


def read_rows(page: Page, grid_index: int) -> dict[str, dict[str, str]]:
    """Every rendered cell, keyed ``"<section>:<row-index>"`` then col-id.

    Both grids run with virtualisation suppressed, so this returns the whole
    grid rather than the visible window.
    """
    return page.evaluate(_READ_ROWS, grid_index)


def grand_total_row(rows: dict[str, dict[str, str]]) -> dict[str, str]:
    """The ``grandTotalRow: "bottom"`` row.

    AG-Grid renders it either in the pinned-bottom container or as the last
    body row depending on whether the grid is scrolled, so locate it by its
    group label rather than by a fixed key.
    """
    for key, cells in rows.items():
        if cells.get("ag-Grid-AutoColumn-campaign") == "Total":
            return cells
    raise AssertionError(f"no grand-total row among {sorted(rows)}")


@pytest.fixture(autouse=True, scope="module")
def streamlit_app():
    with StreamlitRunner(RATIO_JS_FILE) as runner:
        yield runner


@pytest.fixture(autouse=True, scope="function")
def go_to_app(page: Page, streamlit_app: StreamlitRunner):
    page.goto(streamlit_app.server_url)
    page.get_by_role("img", name="Running...").is_hidden()
    page.wait_for_selector(".ag-root-wrapper", timeout=60000)
    # Two grids and the reference table have to finish painting before any read.
    page.wait_for_function(
        "() => document.querySelectorAll('.ag-root-wrapper').length === 2",
        timeout=60000,
    )
    page.wait_for_selector('[row-index="14"]', timeout=60000)


# --------------------------------------------------------------------------
# Row grouping
# --------------------------------------------------------------------------


def test_group_rows_match_the_legacy_javascript(page: Page):
    """Every group row, at both grouping levels, equals `evaluate_legacy`."""
    rows = read_rows(page, ROWGROUP_GRID)

    for row_index, dims in GROUP_ROW_DIMS.items():
        cells = rows[f"body:{row_index}"]
        for col_id in RATIO_COL_IDS:
            assert cells[col_id] == as_text(expected_legacy(col_id, **dims)), (
                f"row {row_index} ({dims}) column {col_id}"
            )


def test_grand_total_row_matches_the_legacy_javascript(page: Page):
    rows = read_rows(page, ROWGROUP_GRID)
    cells = grand_total_row(rows)

    for col_id in RATIO_COL_IDS:
        assert cells[col_id] == as_text(expected_legacy(col_id)), f"total {col_id}"


def test_group_ratios_are_not_the_average_of_their_children(page: Page):
    """The fixture's whole purpose: data where `Σnum/Σden` and `avg(ratio)`
    coincide cannot tell a correct implementation from a broken one, so a test
    built on it passes against either. Assert the separation is real."""
    rows = read_rows(page, ROWGROUP_GRID)

    campaign_a = float(rows["body:0"]["cpi"])
    leaf_average = sum(
        evaluate(RATIO_SPECS[0], [row]) for row in RATIO_ROWS if row["campaign"] == "A"
    ) / 4
    child_average = (
        float(rows["body:1"]["cpi"]) + float(rows["body:4"]["cpi"])
    ) / 2

    assert campaign_a == pytest.approx(10.0)
    assert leaf_average == pytest.approx(105.40625)
    assert child_average == pytest.approx(45.5555, rel=1e-4)


def test_leaf_rows_render_the_precomputed_dataframe_value(page: Page):
    """Leaves never run the aggregator — they show the scalar the dataframe
    carries, which follows the *specified* semantics. On `net_cpi` that puts a
    signed leaf value directly under an unsigned group value."""
    rows = read_rows(page, ROWGROUP_GRID)

    for row_index, source_index in LEAF_ROW_SOURCE.items():
        source_row = RATIO_ROWS[source_index]
        cells = rows[f"body:{row_index}"]
        for spec in RATIO_SPECS:
            assert cells[spec.col_id] == as_text(evaluate(spec, [source_row])), (
                f"leaf row {row_index} column {spec.col_id}"
            )


def test_signed_numerator_is_the_documented_javascript_gap(page: Page):
    """`ratioSum` adds every numerator term, so `net_cpi` rolls up as
    (cost + rebate)/installs. The leaf directly below shows the signed value,
    which is what makes the gap visible on screen rather than only in a test."""
    rows = read_rows(page, ROWGROUP_GRID)

    assert rows["body:0"]["net_cpi"] == as_text(expected_legacy("net_cpi", campaign="A"))
    assert rows["body:0"]["net_cpi"] == "11.2000"
    assert expected("net_cpi", campaign="A") == pytest.approx(8.8)


def test_zero_denominator_group_is_blank_while_its_leaves_show_zero(page: Page):
    """A live inconsistency in the system being replaced: `ratioSum` always
    emits null when the denominator collapses, so campaign B's group rows are
    empty, while its leaves render the dataframe's `fill_null=0.0`."""
    rows = read_rows(page, ROWGROUP_GRID)

    assert rows["body:7"]["arpp"] == ""
    assert rows["body:8"]["arpp"] == ""
    assert rows["body:9"]["arpp"] == "0.0000"
    assert rows["body:10"]["arpp"] == "0.0000"

    # The `fill_null=None` twin is blank on both, which is the only place the
    # two paths currently agree.
    assert rows["body:7"]["arpp_blank"] == ""
    assert rows["body:9"]["arpp_blank"] == ""


# --------------------------------------------------------------------------
# Pivot
# --------------------------------------------------------------------------


def pivot_col(country: str, col_id: str) -> str:
    return f"pivot_country_{country}_{col_id}"


def pivot_total_col(col_id: str) -> str:
    return f"PivotRowTotal_pivot_country__{col_id}"


def test_pivot_cells_ignore_the_pivot_key(page: Page):
    """The defect that motivates the replacement.

    `ratioSum` reads `rowNode.allLeafChildren`, which is not pivot-aware, so
    both country cells of a campaign row show that campaign's total. AG-Grid's
    own `sum` is pivot-aware, so the component columns in the same cells are
    correct — the ratio is the only thing that is wrong.
    """
    rows = read_rows(page, PIVOT_GRID)
    campaign_a = rows["body:0"]

    assert campaign_a[pivot_col("US", "cpi")] == "10.0000"
    assert campaign_a[pivot_col("DE", "cpi")] == "10.0000"
    assert campaign_a[pivot_col("US", "cpi")] == campaign_a[pivot_col("DE", "cpi")]

    # What those cells should read.
    assert expected("cpi", campaign="A", country="US") == pytest.approx(90.0)
    assert expected("cpi", campaign="A", country="DE") == pytest.approx(1.1111, rel=1e-4)

    # The components underneath are split by pivot key correctly.
    assert campaign_a[pivot_col("US", "cost")] == "900"
    assert campaign_a[pivot_col("DE", "cost")] == "100"
    assert campaign_a[pivot_col("US", "installs")] == "10"
    assert campaign_a[pivot_col("DE", "installs")] == "90"


def test_pivot_grand_total_row_cells_ignore_the_pivot_key(page: Page):
    """Same defect one level up: the pivot grid's total row shows the overall
    ratio in each country column instead of that country's ratio."""
    rows = read_rows(page, PIVOT_GRID)
    total = rows["body:2"]

    assert total[pivot_col("US", "cpi")] == "3.4000"
    assert total[pivot_col("DE", "cpi")] == "3.4000"

    assert expected("cpi", country="US") == pytest.approx(8.2727, rel=1e-4)
    assert expected("cpi", country="DE") == pytest.approx(0.5789, rel=1e-4)


def test_pivot_row_totals_are_correct(page: Page):
    """The one pivot number `ratioSum` gets right, and only by accident:
    a row total is exactly the sum over `allLeafChildren`, which is what it
    reads. The replacement must keep these values unchanged."""
    rows = read_rows(page, PIVOT_GRID)

    assert rows["body:0"][pivot_total_col("cpi")] == as_text(expected("cpi", campaign="A"))
    assert rows["body:1"][pivot_total_col("cpi")] == as_text(expected("cpi", campaign="B"))
    assert rows["body:2"][pivot_total_col("cpi")] == as_text(expected("cpi"))
