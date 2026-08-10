"""The built-in `stRatio` aggregator, measured against the reference arithmetic.

Where `test_grid_ratio_js.py` pins what the JavaScript *does*, this suite
asserts what the replacement *should* do: `ratio_fixture.evaluate`, at every
level, with no exemptions.

Two grids, two reading styles. Grid 0 has no valueFormatter, so its cells carry
the value object's own `toString()` — parsed back to a float, which sidesteps
the difference between JavaScript's number-to-string and Python's. Grid 1 uses
the consumer's four-decimal formatter, so its cells compare literally against
`as_text()` and line up with the JavaScript baseline's assertions.

Bulk assertions derive their expectations from `ratio_fixture`. The handful of
literal numbers are deliberate anchors: a suite that only checks grid against
`evaluate()` passes just as happily when both are wrong.
"""

from pathlib import Path

import pytest
from playwright.sync_api import Page

from e2e_utils import StreamlitRunner
from grid_dom import grand_total_row, read_rows
from ratio_fixture import RATIO_ROWS, RATIO_SPECS, as_text, evaluate, expected

ROOT_DIRECTORY = Path(__file__).parent.parent.absolute()
BUILTIN_FILE = ROOT_DIRECTORY / "test" / "grid_ratio_builtin.py"

RATIO_COL_IDS = tuple(spec.col_id for spec in RATIO_SPECS)

RAW_GRID = 0
FORMATTED_GRID = 1
OVERRIDE_GRID = 2

# Body row indices of the fully expanded row-group grids:
#   0 A            4 A/DE          8  B/US        12 B/DE row 0
#   1 A/US         5 A/DE row 0    9  B/US row 0  13 B/DE row 1
#   2 A/US row 0   6 A/DE row 1    10 B/US row 1
#   3 A/US row 1   7 B            11 B/DE
# The grand total follows; find it with `grand_total_row`.
GROUP_ROW_DIMS = {
    0: {"campaign": "A"},
    1: {"campaign": "A", "country": "US"},
    4: {"campaign": "A", "country": "DE"},
    7: {"campaign": "B"},
    8: {"campaign": "B", "country": "US"},
    11: {"campaign": "B", "country": "DE"},
}
LEAF_ROW_SOURCE = {2: 0, 3: 1, 5: 2, 6: 3, 9: 4, 10: 5, 12: 6, 13: 7}

def assert_number(text: str, reference: float | None, where: str) -> None:
    """Compare an unformatted cell against a reference number."""
    if reference is None:
        assert text == "", f"{where}: expected an empty cell, got {text!r}"
    else:
        assert text != "", f"{where}: expected {reference}, got an empty cell"
        assert float(text) == pytest.approx(reference), where


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
        "() => document.querySelectorAll('.ag-root-wrapper').length >= 4",
        timeout=60000,
    )
    page.wait_for_selector('[row-index="14"]', timeout=60000)


def test_group_rows_are_the_sum_ratio_at_both_levels(page: Page):
    rows = read_rows(page, RAW_GRID)

    for row_index, dims in GROUP_ROW_DIMS.items():
        cells = rows[f"body:{row_index}"]
        for col_id in RATIO_COL_IDS:
            assert_number(
                cells[col_id], expected(col_id, **dims), f"row {row_index} {dims} {col_id}"
            )


def test_grand_total_row_is_the_sum_ratio(page: Page):
    cells = grand_total_row(read_rows(page, RAW_GRID))

    for col_id in RATIO_COL_IDS:
        assert_number(cells[col_id], expected(col_id), f"total {col_id}")


def test_leaf_rows_still_show_the_per_row_ratio(page: Page):
    rows = read_rows(page, RAW_GRID)

    for row_index, source_index in LEAF_ROW_SOURCE.items():
        source_row = RATIO_ROWS[source_index]
        cells = rows[f"body:{row_index}"]
        for spec in RATIO_SPECS:
            assert_number(
                cells[spec.col_id],
                evaluate(spec, [source_row]),
                f"leaf {row_index} {spec.col_id}",
            )


def test_signed_numerator_subtracts_its_negative_term(page: Page):
    """The gap the flat `{num, num2, den}` shape could not express. The
    JavaScript baseline reads 11.2000 here."""
    rows = read_rows(page, RAW_GRID)

    assert float(rows["body:0"]["net_cpi"]) == pytest.approx(8.8)
    assert float(rows["body:1"]["net_cpi"]) == pytest.approx(79.0)
    assert float(grand_total_row(rows)["net_cpi"]) == pytest.approx(2.99)


def test_multiplier_and_scale_are_applied(page: Page):
    rows = read_rows(page, RAW_GRID)

    assert float(rows["body:0"]["cpm"]) == pytest.approx(1000 / 30000 * 1000)
    assert float(rows["body:0"]["sess_min"]) == pytest.approx(0.8)


def test_a_collapsed_denominator_uses_fill_null(page: Page):
    """Campaign B has no payers at all. The explicit `fill_null=0.0` column
    renders a zero; the column that leaves `fill_null` at its default renders
    an empty cell, which is what the JavaScript renders today."""
    rows = read_rows(page, RAW_GRID)

    assert float(rows["body:7"]["arpp"]) == pytest.approx(0.0)
    assert float(rows["body:8"]["arpp"]) == pytest.approx(0.0)
    assert rows["body:7"]["arpp_blank"] == ""
    assert rows["body:8"]["arpp_blank"] == ""


def test_group_values_are_not_the_average_of_their_children(page: Page):
    """Campaign A's children are 90.0000 and 1.1111; their average is 45.5556
    and the correct rollup is 10.0000. The fixture separates the two at every
    level so this cannot pass by coincidence."""
    rows = read_rows(page, RAW_GRID)

    assert float(rows["body:0"]["cpi"]) == pytest.approx(10.0)
    assert float(rows["body:1"]["cpi"]) == pytest.approx(90.0)
    assert float(rows["body:4"]["cpi"]) == pytest.approx(1.1111, rel=1e-4)


def test_existing_value_formatters_keep_working_unchanged(page: Page):
    """The consumer's formatter branches on `typeof v === 'object'` and reads
    `v.value`. It was copied over with no edit; every cell must render."""
    rows = read_rows(page, FORMATTED_GRID)

    for row_index, dims in GROUP_ROW_DIMS.items():
        cells = rows[f"body:{row_index}"]
        for col_id in RATIO_COL_IDS:
            assert cells[col_id] == as_text(expected(col_id, **dims)), (
                f"row {row_index} {dims} {col_id}"
            )

    total = grand_total_row(rows)
    assert total["cpi"] == "3.4000"
    assert total["net_cpi"] == "2.9900"


def test_the_unformatted_grid_needs_no_unsafe_jscode(page: Page):
    """Grid 0 is built without `allow_unsafe_jscode`. If the ratio still
    renders, no JavaScript crossed the boundary to produce it."""
    rows = read_rows(page, RAW_GRID)

    assert rows["body:0"]["cpi"] != ""
    assert float(rows["body:0"]["cpi"]) == pytest.approx(10.0)


def test_a_caller_supplied_aggfunc_of_the_same_name_wins(page: Page):
    """The built-in is a default, not a reservation. Grid 2 registers its own
    `stRatio` returning a constant; every group row must show it."""
    rows = read_rows(page, OVERRIDE_GRID)

    assert rows["body:0"]["cpi"] == "42"
    assert rows["body:1"]["cpi"] == "42"
    assert rows["body:0"]["net_cpi"] == "42"
    # Leaf rows read the dataframe, so the override touches group rows only.
    assert float(rows["body:2"]["cpi"]) == pytest.approx(400.0)


# --------------------------------------------------------------------------
# Pivot
# --------------------------------------------------------------------------

PIVOT_GRID = 3


def pivot_col(country: str, col_id: str) -> str:
    return f"pivot_country_{country}_{col_id}"


def pivot_total_col(col_id: str) -> str:
    return f"PivotRowTotal_pivot_country__{col_id}"


def test_pivot_cells_are_split_by_the_pivot_key(page: Page):
    """The defect that motivates the feature. The JavaScript shows the row's
    total in both country columns; each cell must show its own ratio."""
    rows = read_rows(page, PIVOT_GRID)
    campaign_a = rows["body:0"]

    for country in ("US", "DE"):
        for col_id in RATIO_COL_IDS:
            assert_number(
                campaign_a[pivot_col(country, col_id)],
                expected(col_id, campaign="A", country=country),
                f"A/{country} {col_id}",
            )

    assert float(campaign_a[pivot_col("US", "cpi")]) == pytest.approx(90.0)
    assert float(campaign_a[pivot_col("DE", "cpi")]) == pytest.approx(1.1111, rel=1e-4)


def test_pivot_row_totals_are_the_ratio_across_all_pivot_keys(page: Page):
    rows = read_rows(page, PIVOT_GRID)

    for row_index, campaign in ((0, "A"), (1, "B")):
        for col_id in RATIO_COL_IDS:
            assert_number(
                rows[f"body:{row_index}"][pivot_total_col(col_id)],
                expected(col_id, campaign=campaign),
                f"{campaign} row total {col_id}",
            )


def test_pivot_grand_total_row_is_split_by_the_pivot_key(page: Page):
    """One level up: each country column of the total row carries that
    country's ratio, and the row total carries the overall one."""
    rows = read_rows(page, PIVOT_GRID)
    total = rows["body:2"]

    for country in ("US", "DE"):
        for col_id in RATIO_COL_IDS:
            assert_number(
                total[pivot_col(country, col_id)],
                expected(col_id, country=country),
                f"total/{country} {col_id}",
            )

    assert float(total[pivot_col("US", "cpi")]) == pytest.approx(8.2727, rel=1e-4)
    assert float(total[pivot_col("DE", "cpi")]) == pytest.approx(0.5789, rel=1e-4)
    assert float(total[pivot_total_col("cpi")]) == pytest.approx(3.4)
