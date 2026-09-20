"""The reader's colour-scale picker, driven through a real grid.

Every expected colour comes from `color_scale_fixture.expected_rgba`, never
from a number typed here. Rows are addressed by `row-index`, never by document
order (`grid_dom.py` says why).
"""

import re
import time
from pathlib import Path

import pytest
from playwright.sync_api import Page

from color_scale_dom import assert_painted, assert_unpainted
from color_scale_fixture import column_values, expected_rgba, region_values
from e2e_utils import StreamlitRunner
from grid_dom import cell_backgrounds

ROOT_DIRECTORY = Path(__file__).parent.parent.absolute()
APP_FILE = ROOT_DIRECTORY / "test" / "grid_color_scale_picker.py"

FLAT_GRID = 0
PIVOT_GRID = 1
OFF_GRID = 2
CALLER_GRID = 3
STATE_GRID = 4
PIVOT_SAVED_GRID = 5
GRID_COUNT = 6

#: Body rows in fixture order: DE, FR, IT (EU) then CA, NY, TX (US). The pivot
#: grids group by country, so they have the same six rows in the same order.
ROWS = tuple(f"body:{index}" for index in range(6))


def flat_values(field: str) -> dict[str, float]:
    return dict(zip(ROWS, column_values(field)))


def pivot_values(region: str, field: str) -> dict[str, float | None]:
    """One pivot result column: a region's countries carry a value, every
    other row is an empty cell."""
    values = region_values(region, field)
    offset = 0 if region == "EU" else 3
    return {
        row: (values[index - offset] if offset <= index < offset + 3 else None)
        for index, row in enumerate(ROWS)
    }


def eventually(check, timeout: float = 5.0) -> None:
    """Re-run `check` until it stops raising. A menu action repaints on the
    next frame and a rerun lands later still; polling beats a fixed sleep."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            return check()
        except (AssertionError, KeyError):
            if time.monotonic() > deadline:
                raise
            time.sleep(0.1)


def assert_column(
    page: Page,
    grid: int,
    col_id: str,
    scheme: str,
    values_by_row: dict,
    population=None,
    **expected_kwargs,
) -> None:
    """Every cell of one column is painted exactly as `scheme` dictates over
    `population` (default: the column's own non-empty values)."""
    if population is None:
        population = [v for v in values_by_row.values() if v is not None]

    def check():
        backgrounds = cell_backgrounds(page, grid)
        for row, value in values_by_row.items():
            where = f"grid {grid} {col_id} {row}"
            actual = backgrounds[row][col_id]
            expected = expected_rgba(scheme, population, value, **expected_kwargs)
            if expected is None:
                assert_unpainted(actual, scheme, where)
            else:
                assert_painted(actual, expected, where)

    eventually(check)


def assert_column_unpainted(page: Page, grid: int, col_id: str, *schemes: str) -> None:
    def check():
        backgrounds = cell_backgrounds(page, grid)
        for row in ROWS:
            for scheme in schemes:
                assert_unpainted(backgrounds[row][col_id], scheme, f"grid {grid} {col_id} {row}")

    eventually(check)


def marker(page: Page, prefix: str) -> str:
    """The value of one `st.text("<prefix>=<value>")` line of the app."""
    text = page.get_by_text(re.compile(rf"^{prefix}=")).first.inner_text()
    return text.split("=", 1)[1]


@pytest.fixture(autouse=True, scope="module")
def streamlit_app():
    with StreamlitRunner(APP_FILE) as runner:
        yield runner


@pytest.fixture(autouse=True, scope="function")
def go_to_app(page: Page, streamlit_app: StreamlitRunner):
    page.set_viewport_size({"width": 1400, "height": 1000})
    page.goto(streamlit_app.server_url)
    page.wait_for_function(
        f"() => document.querySelectorAll('.ag-root-wrapper').length >= {GRID_COUNT}",
        timeout=60000,
    )
    # The last grid is a pivot: wait until it has rendered its six group rows.
    page.wait_for_function(
        f"""() => {{
             const grid = document.querySelectorAll('.ag-root-wrapper')[{PIVOT_SAVED_GRID}];
             return !!grid && grid.querySelectorAll('.ag-cell[col-id^="pivot_"]').length >= 6;
           }}""",
        timeout=60000,
    )


# ---------------------------------------------------------------------------
# Restore: the saved choice is a resolution layer, present before first paint
# ---------------------------------------------------------------------------


def test_a_saved_choice_activates_an_undeclared_column(page: Page):
    assert_column(page, STATE_GRID, "metric_b", "diverging", flat_values("metric_b"))
    # The declared neighbour is untouched by someone else's entry.
    assert_column(page, STATE_GRID, "metric_a", "neutral", flat_values("metric_a"))


def test_a_saved_choice_reaches_every_pivot_result_column(page: Page):
    for region in ("EU", "US"):
        assert_column(
            page,
            PIVOT_SAVED_GRID,
            f"pivot_region_{region}_metric_a",
            "diverging",
            pivot_values(region, "metric_a"),
        )
        assert_column(
            page,
            PIVOT_SAVED_GRID,
            f"pivot_region_{region}_metric_b",
            "positive",
            pivot_values(region, "metric_b"),
        )


def test_an_interactive_grid_paints_its_declarations_as_before(page: Page):
    assert_column(page, FLAT_GRID, "metric_a", "neutral", flat_values("metric_a"))
    assert_column_unpainted(page, FLAT_GRID, "metric_b", "neutral", "positive", "diverging")


def test_a_grid_without_the_opt_in_is_unchanged(page: Page):
    assert_column(page, OFF_GRID, "metric_a", "neutral", flat_values("metric_a"))
    assert_column_unpainted(page, OFF_GRID, "metric_b", "neutral", "positive", "diverging")
