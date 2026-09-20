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
ANCHOR_GRID = 6
LIVE_GRID = 7
GRID_COUNT = 8

#: Grid 6's anchor reference, for `expected_rgba`. Written out here rather than
#: imported from the app: importing that module would run a Streamlit script.
ANCHOR_1 = dict(anchor=1.0, span=1.0)

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


def option_names(page: Page) -> list[str]:
    """Every visible menu item's label, in order. Separators carry no text
    element and so do not appear."""
    return [text.strip() for text in page.locator(".ag-menu-option-text").all_inner_texts()]


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


def toggle(page: Page, label: str) -> None:
    """Click a checkbox and wait until the rerun it triggers has landed."""
    runs = int(marker(page, "runs"))
    page.get_by_text(label).click()
    eventually(lambda: _assert_greater(int(marker(page, "runs")), runs))


def header_menu_offers_the_item(page: Page, grid: int, col_id: str) -> bool:
    open_header_menu(page, grid, col_id)
    found = has_option(page, MENU_ITEM)
    close_menu(page)
    return found


def cell_menu_offers_the_item(page: Page, grid: int, col_id: str) -> bool:
    open_cell_menu(page, grid, col_id)
    found = has_option(page, MENU_ITEM)
    close_menu(page)
    return found


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
    # Grid 5 is a pivot: wait until it has rendered its six group rows.
    page.wait_for_function(
        f"""() => {{
             const grid = document.querySelectorAll('.ag-root-wrapper')[{PIVOT_SAVED_GRID}];
             return !!grid && grid.querySelectorAll('.ag-cell[col-id^="pivot_"]').length >= 6;
           }}""",
        timeout=60000,
    )
    # …and the last grid until its body is up, so a test that opens a menu
    # there is not racing the mount.
    page.wait_for_function(
        f"""() => {{
             const grid = document.querySelectorAll('.ag-root-wrapper')[{LIVE_GRID}];
             return !!grid && grid.querySelectorAll('.ag-cell[col-id="metric_b"]').length >= 6;
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


def test_a_mode_choice_keeps_an_anchor_only_scheme(page: Page):
    """Grid 6 declares `mode="anchor"` and no scheme at all — a complete
    default set, and the shape a dashboard's ratio columns take. Its scheme
    exists only as `resolveMerged`'s implicit `diverging` for `mode="anchor"`,
    so a choice that stored the mode alone would resolve to nothing and the
    declaration-only fallback would repaint the column exactly as it was.
    """
    values = flat_values("ratio")
    assert_column(page, ANCHOR_GRID, "ratio", "diverging", values, mode="anchor", **ANCHOR_1)

    open_header_menu(page, ANCHOR_GRID, "ratio")
    hover_submenu(page, MENU_ITEM)
    hover_submenu(page, "Mode")
    assert set(ticked(page)) == {"Diverging", "Anchor"}
    pick(page, "Z-score")
    assert_column(page, ANCHOR_GRID, "ratio", "diverging", values, mode="zscore")

    open_header_menu(page, ANCHOR_GRID, "ratio")
    hover_submenu(page, MENU_ITEM)
    hover_submenu(page, "Mode")
    assert set(ticked(page)) == {"Diverging", "Z-score"}
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


def test_a_caller_hook_that_returns_nothing_keeps_the_defaults(page: Page):
    """Grid 3's `getContextMenuItems` returns `undefined`, which AG-Grid reads
    as "show the defaults". The wrapper has to read it the same way, or the
    column is left with the picker alone behind a leading separator."""
    open_cell_menu(page, CALLER_GRID, "metric_a")
    names = option_names(page)
    assert "Copy" in names  # AG-Grid's own defaults, still there
    assert names[-1] == MENU_ITEM  # …with the picker appended after them
    close_menu(page)


def test_a_col_def_main_menu_replaces_the_column_menu_picker_included(page: Page):
    """A per-column `mainMenuItems` owns its column's menu outright.

    AG-Grid's own resolver reaches `colDef.mainMenuItems` only when no
    grid-level `getColumnMenuItems` is installed (`_resolveColumnMenuItems`,
    `node_modules/ag-grid-enterprise/dist/package/main.cjs.js:18249`) — and the
    picker always installs one, so the wrapper has to take that step itself.
    The column is eligible in every other respect: on this interactive grid a
    wrapper that simply appended would show the full defaults plus the picker
    instead of the one item the page asked for.
    """
    open_header_menu(page, CALLER_GRID, "metric_b_own_menu")
    assert option_names(page) == ["Autosize This Column"]
    close_menu(page)


def test_interactive_takes_effect_on_a_live_grid_in_both_directions(page: Page):
    """The opt-in is not creation-only.

    `getColumnMenuItems` carries an `@initial` tag in AG-Grid's typings, and
    this branch first documented an asymmetry from it: the cell menu live, the
    column menu only after a remount. The tag is typings-only — the key is not
    in the runtime's `INITIAL_GRID_OPTION_KEYS`
    (`ag-grid-community/dist/package/main.cjs.js:59993-60081`),
    `updateGridOptions` writes every key it is handed (`:28000`), and
    `_resolveColumnMenuItems` reads the callback through `gos.getCallback` on
    every open (`ag-grid-enterprise/.../main.cjs.js:18259`). This test is the
    measurement that settles it; the docs were rewritten from its result.
    """
    open_header_menu(page, LIVE_GRID, "metric_b")
    assert has_option(page, "Sort Ascending")  # it is the real menu
    assert not has_option(page, MENU_ITEM)
    close_menu(page)
    assert not cell_menu_offers_the_item(page, LIVE_GRID, "metric_b")

    def offered():
        assert header_menu_offers_the_item(page, LIVE_GRID, "metric_b")

    def gone():
        assert not header_menu_offers_the_item(page, LIVE_GRID, "metric_b")

    toggle(page, "interactive on")
    # The config update lands a beat after the rerun's DOM, so the first look
    # can be early — but no remount happens, which is the whole point.
    eventually(offered)
    assert cell_menu_offers_the_item(page, LIVE_GRID, "metric_b")

    # Offered and working, not merely rendered.
    open_header_menu(page, LIVE_GRID, "metric_b")
    pick(page, MENU_ITEM, "Positive")
    assert_column(page, LIVE_GRID, "metric_b", "positive", flat_values("metric_b"))

    toggle(page, "interactive on")
    eventually(gone)
    assert not cell_menu_offers_the_item(page, LIVE_GRID, "metric_b")
    # The reader's layer goes with the opt-in; the page's own declaration stays.
    assert_column_unpainted(page, LIVE_GRID, "metric_b", "positive")
    assert_column(page, LIVE_GRID, "metric_a", "neutral", flat_values("metric_a"))


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


def header_row_height(page: Page, grid: int) -> float:
    return page.evaluate(
        """(grid) => document.querySelectorAll('.ag-root-wrapper')[grid]
             .querySelector('.ag-header-row').getBoundingClientRect().height""",
        grid,
    )


def test_a_choice_survives_a_config_update(page: Page):
    """Every wait here is on something the update itself changed.

    This grid reruns on `stColorScaleChanged`, so the pick has a rerun of its
    own. Sampling `runs` straight after the immediate repaint and then waiting
    for it to grow would be satisfied by that rerun, and the colour assertions
    would run on pre-update pixels — the test would pass without a config
    update ever having landed. So: wait for the reported state to show the
    pick, then for the new `headerHeight` to reach the DOM, and only then look
    at the colours.
    """
    open_header_menu(page, STATE_GRID, "metric_a")
    pick(page, MENU_ITEM, "Positive")

    def reported():
        assert saved_state(page) == {
            "metric_a": {"scheme": "positive"},
            "metric_b": {"scheme": "diverging"},
        }

    eventually(reported)
    assert_column(page, STATE_GRID, "metric_a", "positive", flat_values("metric_a"))

    before = header_row_height(page, STATE_GRID)
    toggle(page, "taller header")
    page.wait_for_function(
        """({grid, before}) => {
             const row = document.querySelectorAll('.ag-root-wrapper')[grid]
                           ?.querySelector('.ag-header-row');
             return !!row && Math.abs(row.getBoundingClientRect().height - before) > 1;
           }""",
        arg={"grid": STATE_GRID, "before": before},
        timeout=15000,
    )
    # `updateGridOptions` installed fresh colDefs and a fresh `context`; the
    # same map rode along.
    assert_column(page, STATE_GRID, "metric_a", "positive", flat_values("metric_a"))
    assert_column(page, STATE_GRID, "metric_b", "diverging", flat_values("metric_b"))


def _assert_greater(actual: int, floor: int) -> None:
    assert actual > floor
