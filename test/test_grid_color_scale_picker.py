"""The reader's colour-scale picker, driven through a real grid.

Every expected colour comes from `color_scale_fixture.expected_rgba`, never
from a number typed here. Rows are addressed by `row-index`, never by document
order (`grid_dom.py` says why).
"""

import json
import re
import time
from pathlib import Path

import pytest
from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from color_scale_dom import assert_painted, assert_unpainted
from color_scale_fixture import RANK_RGBA, column_values, expected_rgba, region_values
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


MENU_ITEM = "Colour scale"


def grid_locator(page: Page, grid: int):
    return page.locator(".ag-root-wrapper").nth(grid)


def open_header_menu(page: Page, grid: int, col_id: str) -> None:
    header = grid_locator(page, grid).locator(f'.ag-header-cell[col-id="{col_id}"]')
    header.scroll_into_view_if_needed()
    header.hover()
    header.locator(".ag-header-cell-menu-button").first.click()
    page.locator(".ag-menu-option").first.wait_for(state="visible")


def open_cell_menu(page: Page, grid: int, col_id: str, row_index: int = 1) -> None:
    cell = grid_locator(page, grid).locator(
        f'.ag-row[row-index="{row_index}"] .ag-cell[col-id="{col_id}"]'
    )
    cell.scroll_into_view_if_needed()
    cell.click(button="right")
    page.locator(".ag-menu-option").first.wait_for(state="visible")


def open_panel_menu(page: Page, grid: int, label: str) -> None:
    """Right-click a column's row in the Columns tool panel.

    The right-click target is the virtual-list item, not the
    `.ag-column-select-column` inside it: on a pivot grid that inner element
    renders `…-readonly` and takes no pointer events, so a click aimed at its
    centre is hit-tested to its parent and Playwright refuses it.
    """
    row = (
        grid_locator(page, grid)
        .locator(".ag-column-select-virtual-list-item", has_text=label)
        .first
    )
    row.scroll_into_view_if_needed()
    row.click(button="right")
    page.locator(".ag-menu-option").first.wait_for(state="visible")


def option(page: Page, name: str):
    return page.locator(
        ".ag-menu-option", has=page.locator(f'.ag-menu-option-text:text-is("{name}")')
    ).last


def has_option(page: Page, name: str) -> bool:
    return page.locator(f'.ag-menu-option-text:text-is("{name}")').count() > 0


def hover_submenu(page: Page, name: str) -> None:
    """Hover a sub-menu parent and wait until its sub menu is really open.

    AG-Grid opens a sub menu a beat after the pointer lands, so anything read
    straight after `hover()` — the ticks, above all — is read off a menu that
    is not on screen yet. `aria-expanded` is the item's own record of its sub
    menu being open, so the wait is on state rather than on a sleep.
    """
    option(page, name).hover()
    page.locator(
        f'.ag-menu-option[aria-expanded="true"]:has(.ag-menu-option-text:text-is("{name}"))'
    ).wait_for(state="visible")


def pick(page: Page, *path: str) -> None:
    """Walk an open menu by visible names; hovering opens a sub menu, the
    last name is clicked."""
    for index, name in enumerate(path):
        target = option(page, name)
        target.wait_for(state="visible")
        if index < len(path) - 1:
            target.hover()
        else:
            target.click()


def ticked(page: Page) -> list[str]:
    return page.evaluate(
        """() => [...document.querySelectorAll('.ag-menu-option')]
             .filter(o => o.querySelector('.ag-menu-option-icon .ag-icon-tick'))
             .map(o => o.querySelector('.ag-menu-option-text').textContent.trim())"""
    )


def close_menu(page: Page) -> None:
    """Close whatever menu is open, and wait until it is really gone.

    Escape alone is not enough: a menu opened with the mouse does not always
    hold keyboard focus, and the key then goes to the document, which leaves
    the menu standing. A click outside every popup is what AG-Grid always
    honours, so it is the fallback — and both waits are on the menu's own
    state, never on a sleep.
    """
    menu = page.locator(".ag-menu").first
    page.keyboard.press("Escape")
    try:
        menu.wait_for(state="hidden", timeout=1000)
        return
    except PlaywrightTimeoutError:
        pass
    # Top-left of the viewport: the Streamlit header's empty side, outside
    # every grid and every popup.
    page.mouse.click(2, 2)
    menu.wait_for(state="hidden", timeout=5000)


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


# ---------------------------------------------------------------------------
# The menu
# ---------------------------------------------------------------------------


def test_header_menu_paints_an_undeclared_column_without_a_rerun(page: Page):
    runs = marker(page, "runs")
    open_header_menu(page, FLAT_GRID, "metric_b")
    pick(page, MENU_ITEM, "Diverging")
    assert_column(page, FLAT_GRID, "metric_b", "diverging", flat_values("metric_b"))
    # `stColorScaleChanged` is not in this grid's `update_on`.
    assert marker(page, "runs") == runs


def test_cell_menu_ticks_the_current_value_and_changes_mode_and_direction(page: Page):
    values = flat_values("metric_a")

    open_cell_menu(page, FLAT_GRID, "metric_a")
    hover_submenu(page, MENU_ITEM)
    hover_submenu(page, "Mode")
    assert set(ticked(page)) == {"Neutral", "Z-score"}
    pick(page, "Min–max")
    assert_column(page, FLAT_GRID, "metric_a", "neutral", values, mode="minmax")

    open_cell_menu(page, FLAT_GRID, "metric_a")
    pick(page, MENU_ITEM, "Reverse")
    assert_column(page, FLAT_GRID, "metric_a", "neutral", values, mode="minmax", reverse=True)

    open_cell_menu(page, FLAT_GRID, "metric_a")
    hover_submenu(page, MENU_ITEM)
    hover_submenu(page, "Mode")
    assert set(ticked(page)) == {"Neutral", "Min–max", "Reverse"}
    close_menu(page)


def test_rank_is_offered_and_disables_mode(page: Page):
    open_header_menu(page, FLAT_GRID, "metric_a")
    pick(page, MENU_ITEM, "Rank")

    def best_is_marked():
        backgrounds = cell_backgrounds(page, FLAT_GRID)
        assert_painted(backgrounds["body:5"]["metric_a"], RANK_RGBA, "rank winner")
        assert_unpainted(backgrounds["body:0"]["metric_a"], "neutral", "rank loser")

    eventually(best_is_marked)

    open_header_menu(page, FLAT_GRID, "metric_a")
    hover_submenu(page, MENU_ITEM)
    assert "ag-menu-option-disabled" in (option(page, "Mode").get_attribute("class") or "")
    close_menu(page)


def test_none_clears_the_colour_and_reset_restores_the_declaration(page: Page):
    open_header_menu(page, FLAT_GRID, "metric_a")
    pick(page, MENU_ITEM, "None")
    # The regression this guards: `cellStyle` returning `null` would leave the
    # old colour on the cell.
    assert_column_unpainted(page, FLAT_GRID, "metric_a", "neutral")

    open_header_menu(page, FLAT_GRID, "metric_a")
    hover_submenu(page, MENU_ITEM)
    assert ticked(page) == ["None"]
    pick(page, "Reset to default")
    assert_column(page, FLAT_GRID, "metric_a", "neutral", flat_values("metric_a"))

    open_header_menu(page, FLAT_GRID, "metric_a")
    hover_submenu(page, MENU_ITEM)
    assert not has_option(page, "Reset to default")
    close_menu(page)


@pytest.mark.parametrize("col_id", ["region", "metric_c", "ratio_own", "ratio_off"])
def test_ineligible_columns_offer_no_item(page: Page, col_id: str):
    """Text, `fill`, a caller's `cellStyle`, and the page author's `False`."""
    open_header_menu(page, FLAT_GRID, col_id)
    assert not has_option(page, MENU_ITEM)
    close_menu(page)
    open_cell_menu(page, FLAT_GRID, col_id)
    assert not has_option(page, MENU_ITEM)
    close_menu(page)


def test_a_grid_without_the_opt_in_offers_no_item(page: Page):
    open_header_menu(page, OFF_GRID, "metric_a")
    assert has_option(page, "Sort Ascending")  # it is the real menu
    assert not has_option(page, MENU_ITEM)
    close_menu(page)
    open_cell_menu(page, OFF_GRID, "metric_a")
    assert not has_option(page, MENU_ITEM)
    close_menu(page)


def test_a_header_choice_repaints_every_pivot_result_column(page: Page):
    open_header_menu(page, PIVOT_GRID, "pivot_region_EU_metric_a")
    pick(page, MENU_ITEM, "Diverging")
    for region in ("EU", "US"):
        assert_column(
            page,
            PIVOT_GRID,
            f"pivot_region_{region}_metric_a",
            "diverging",
            pivot_values(region, "metric_a"),
        )


def test_the_columns_panel_offers_the_same_menu(page: Page):
    open_panel_menu(page, PIVOT_GRID, "Metric_b")
    pick(page, MENU_ITEM, "Positive")
    for region in ("EU", "US"):
        assert_column(
            page,
            PIVOT_GRID,
            f"pivot_region_{region}_metric_b",
            "positive",
            pivot_values(region, "metric_b"),
        )
    # Reopened from the panel, the tick reflects the choice just made.
    open_panel_menu(page, PIVOT_GRID, "Metric_b")
    hover_submenu(page, MENU_ITEM)
    assert ticked(page) == ["Positive"]
    close_menu(page)


def test_a_caller_supplied_main_menu_is_kept(page: Page):
    open_header_menu(page, CALLER_GRID, "metric_a")
    assert has_option(page, "Caller item")
    assert has_option(page, MENU_ITEM)
    close_menu(page)


# ---------------------------------------------------------------------------
# State out, and back in
# ---------------------------------------------------------------------------


def saved_state(page: Page) -> dict | None:
    return json.loads(marker(page, "state"))


def test_a_choice_is_reported_and_survives_a_remount(page: Page):
    open_header_menu(page, STATE_GRID, "metric_a")
    pick(page, MENU_ITEM, "Positive")

    def reported():
        assert saved_state(page) == {
            "metric_a": {"scheme": "positive"},
            "metric_b": {"scheme": "diverging"},
        }

    eventually(reported)
    # The rerun that reported it must not have disturbed the picture.
    assert_column(page, STATE_GRID, "metric_a", "positive", flat_values("metric_a"))

    page.get_by_role("button", name="remount").click()
    # A fresh grid instance, fed only from what Python saved.
    assert_column(page, STATE_GRID, "metric_a", "positive", flat_values("metric_a"))
    assert_column(page, STATE_GRID, "metric_b", "diverging", flat_values("metric_b"))


def test_none_on_a_declared_column_is_reported_as_false(page: Page):
    open_header_menu(page, STATE_GRID, "metric_a")
    pick(page, MENU_ITEM, "None")

    def reported():
        assert saved_state(page) == {"metric_a": False, "metric_b": {"scheme": "diverging"}}

    eventually(reported)


def test_a_choice_survives_a_config_update(page: Page):
    open_header_menu(page, STATE_GRID, "metric_a")
    pick(page, MENU_ITEM, "Positive")
    assert_column(page, STATE_GRID, "metric_a", "positive", flat_values("metric_a"))

    runs = int(marker(page, "runs"))
    page.get_by_text("flip option").click()
    eventually(lambda: _assert_greater(int(marker(page, "runs")), runs))
    # `updateGridOptions` installed fresh colDefs and a fresh `context`; the
    # same map rode along.
    assert_column(page, STATE_GRID, "metric_a", "positive", flat_values("metric_a"))
    assert_column(page, STATE_GRID, "metric_b", "diverging", flat_values("metric_b"))


def _assert_greater(actual: int, floor: int) -> None:
    assert actual > floor
