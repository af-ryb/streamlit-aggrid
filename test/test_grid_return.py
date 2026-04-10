from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

from e2e_utils import StreamlitRunner


ROOT_DIRECTORY = Path(__file__).parent.parent.absolute()
GRID_RETURN_FILE = ROOT_DIRECTORY / "test" / "grid_return.py"
SCREENSHOT_DIRECTORY = ROOT_DIRECTORY / "test" / "screen_shots"


@pytest.fixture(autouse=True, scope="module")
def streamlit_app():
    with StreamlitRunner(GRID_RETURN_FILE) as runner:
        yield runner


@pytest.fixture(autouse=True, scope="function")
def go_to_app(page: Page, streamlit_app: StreamlitRunner):
    page.goto(streamlit_app.server_url)
    # Wait for app to load
    page.get_by_role("img", name="Running...").is_hidden()


# --- Test 1: basic selection + event_return_grid ---------------------------


def test_grid_return_test_1(page: Page):
    """Verify the basic event_return grid renders data and returns data."""
    radio_option_1 = page.get_by_test_id("stRadio").get_by_text("1")
    radio_option_1.click()

    frame0 = page.locator(".st-key-event_return_grid")
    expect(frame0.locator(".ag-root")).to_be_visible()

    # Column headers
    expect(frame0.locator(".ag-header-cell-text").nth(1)).to_have_text("First Name")
    expect(frame0.locator(".ag-header-cell-text").nth(2)).to_have_text("ages")

    # Click header to sort — triggers a grid event
    frame0.locator(".ag-header-cell-text").nth(1).click()

    # Rows present
    expect(frame0.locator(".ag-row")).not_to_have_count(0)

    # First data row: alice / 25
    first_row = frame0.locator(".ag-row").nth(0)
    expect(first_row.locator(".ag-cell").nth(1)).to_have_text("alice")
    expect(first_row.locator(".ag-cell").nth(2)).to_have_text("25")

    # Returned data echo (r.data.to_string())
    returned_grid_data = page.get_by_test_id("returned-grid-data")
    expect(returned_grid_data).to_be_visible()
    expect(returned_grid_data).to_contain_text("alice")
    expect(returned_grid_data).to_contain_text("bob")
    expect(returned_grid_data).to_contain_text("charlie")

    # Event echo — present as a <pre> even if nothing triggered yet
    event_return_data = page.get_by_test_id("event-return-data")
    expect(event_return_data).to_be_visible()

    # Selected data — starts as "No rows selected"
    selected_data = page.get_by_test_id("selected-data")
    expect(selected_data).to_be_visible()
    expect(selected_data).to_contain_text("No rows selected")

    # Full grid response echoes event name and collected state keys
    full_grid_response = page.get_by_test_id("full-grid-response")
    expect(full_grid_response).to_be_visible()


def test_grid_return_third_row_checkbox(page: Page):
    """Click the 3rd row checkbox; verify selected_rows contains charlie."""
    radio_option_1 = page.get_by_test_id("stRadio").get_by_text("1")
    radio_option_1.click()

    frame0 = page.locator(".st-key-event_return_grid")
    expect(frame0.locator(".ag-root")).to_be_visible()
    expect(frame0.locator(".ag-row")).not_to_have_count(0)

    # Click the 3rd row checkbox (index 2)
    third_row = frame0.locator(".ag-row").nth(2)
    checkbox = third_row.locator(".ag-selection-checkbox input[type='checkbox']")
    checkbox.click()
    expect(checkbox).to_be_checked()

    # selectionChanged flows through collect=['getSelectedRows']
    selected_data = page.get_by_test_id("selected-data")
    expect(selected_data).to_contain_text("charlie")
    expect(selected_data).to_contain_text("35")
    expect(selected_data).not_to_contain_text("alice")
    expect(selected_data).not_to_contain_text("bob")

    # Event name is surfaced
    event_return_data = page.get_by_test_id("event-return-data")
    expect(event_return_data).to_contain_text("selectionChanged")


# --- Test 2: column order tracking via getColumnState ----------------------


def test_grid_return_test_2_custom_return(page: Page):
    """columnMoved / sortChanged → collect=['getColumnState'] → column order."""
    radio_option_2 = page.get_by_test_id("stRadio").get_by_text("2")
    radio_option_2.click()

    frame1 = page.locator(".st-key-custom_event_return_grid")
    expect(frame1.locator(".ag-root")).to_be_visible()
    expect(frame1.locator(".ag-row")).not_to_have_count(0)

    # Initially — no event fired, column state is None
    custom_grid_return_data = page.get_by_test_id("custom-grid-return-data")
    expect(custom_grid_return_data).to_be_visible()
    expect(custom_grid_return_data).to_contain_text("None")

    # Click a header to trigger sortChanged → getColumnState materialises
    first_column = frame1.get_by_role("columnheader", name="employee_id")
    first_column.click()
    expect(custom_grid_return_data).to_contain_text("employee_id")
    expect(custom_grid_return_data).to_contain_text("first_name")
    expect(custom_grid_return_data).to_contain_text("last_name")
    expect(custom_grid_return_data).to_contain_text("email")


# --- Test 3: grouped data (Enterprise) -------------------------------------


def test_grid_return_test_3_grouped_data(page: Page):
    """Grouped data grid renders and exposes sort events."""
    radio_option_3 = page.get_by_test_id("stRadio").get_by_text("3")
    radio_option_3.click()

    frame2 = page.locator(".st-key-grouped_data_grid")
    expect(frame2.locator(".ag-root")).to_be_visible()
    page.wait_for_timeout(1500)

    # Sort on "Sport" header triggers an event
    sport_col = frame2.get_by_role("columnheader", name="Sport")
    sport_col.click()

    grouped_grid_response = page.get_by_test_id("grouped-grid-response")
    expect(grouped_grid_response).to_be_visible()


def test_grid_return_test_3_grouped_data_selection(page: Page):
    """Selecting a leaf row in grouped data surfaces it in selected_rows."""
    radio_option_3 = page.get_by_test_id("stRadio").get_by_text("3")
    radio_option_3.click()

    frame2 = page.locator(".st-key-grouped_data_grid")
    expect(frame2.locator(".ag-root")).to_be_visible()
    page.wait_for_timeout(1500)

    grouped_selection_count = page.get_by_test_id("grouped-selection-count")
    expect(grouped_selection_count).to_contain_text("0")

    # Expand top-level groups
    contracted = frame2.locator(".ag-group-contracted > .ag-icon")
    if contracted.count() > 0:
        contracted.first.click()
        page.wait_for_timeout(500)
    # and a second level if any
    contracted = frame2.locator(".ag-group-contracted > .ag-icon")
    if contracted.count() > 0:
        contracted.first.click()
        page.wait_for_timeout(500)

    # Click the first available checkbox anywhere in the tree
    first_checkbox = frame2.locator(
        ".ag-selection-checkbox input[type='checkbox']"
    ).first
    if first_checkbox.count() == 0:
        first_checkbox = frame2.locator("input[type='checkbox']").first
    first_checkbox.click()
    page.wait_for_timeout(1500)

    expect(grouped_selection_count).not_to_contain_text("0")
    grouped_selected_data = page.get_by_test_id("grouped-selected-data")
    expect(grouped_selected_data).not_to_contain_text("No rows selected")


def test_grid_return_test_3_grouped_data_header_checkbox(page: Page):
    """Header checkbox toggles bulk selection in grouped grid."""
    radio_option_3 = page.get_by_test_id("stRadio").get_by_text("3")
    radio_option_3.click()

    frame2 = page.locator(".st-key-grouped_data_grid")
    expect(frame2.locator(".ag-root")).to_be_visible()
    page.wait_for_timeout(1500)

    grouped_selection_count = page.get_by_test_id("grouped-selection-count")
    expect(grouped_selection_count).to_contain_text("0")

    # Expand a couple of levels so leaf rows materialise
    for _ in range(2):
        contracted = frame2.locator(".ag-group-contracted > .ag-icon")
        if contracted.count() > 0:
            contracted.first.click()
            page.wait_for_timeout(500)

    header_checkbox = frame2.locator(
        ".ag-header-row .ag-selection-checkbox input[type='checkbox']"
    ).first
    if header_checkbox.count() == 0:
        header_checkbox = frame2.locator(
            ".ag-header-container input[type='checkbox']"
        ).first
    header_checkbox.click()
    page.wait_for_timeout(1500)

    expect(header_checkbox).to_be_checked()
    expect(grouped_selection_count).not_to_contain_text("0")
    grouped_selected_data = page.get_by_test_id("grouped-selected-data")
    expect(grouped_selected_data).not_to_contain_text("No rows selected")

    # Toggle off
    header_checkbox.click()
    page.wait_for_timeout(1500)
    expect(header_checkbox).not_to_be_checked()
    expect(grouped_selection_count).to_contain_text("0")
    expect(grouped_selected_data).to_contain_text("No rows selected")


# --- Test 4: comprehensive selection + pagination --------------------------


def test_grid_return_test_4_selection_functionality(page: Page):
    """Multi-row selection via row checkboxes."""
    radio_option_4 = page.get_by_test_id("stRadio").get_by_text("4")
    radio_option_4.click()

    frame3 = page.locator(".st-key-selection_test_grid")
    expect(frame3.locator(".ag-root")).to_be_visible()
    expect(frame3.locator(".ag-row")).not_to_have_count(0)

    # Column headers — the auto-added selection column occupies index 0 with
    # empty header text, so real columns start at nth(1).
    expect(frame3.locator(".ag-header-cell-text").nth(1)).to_have_text("ID")
    expect(frame3.locator(".ag-header-cell-text").nth(2)).to_have_text("Name")
    expect(frame3.locator(".ag-header-cell-text").nth(3)).to_have_text("Category")
    expect(frame3.locator(".ag-header-cell-text").nth(4)).to_have_text("Value")
    expect(frame3.locator(".ag-header-cell-text").nth(5)).to_have_text("Active")

    selection_count = page.get_by_test_id("selection-count")
    expect(selection_count).to_contain_text("0")

    selected_rows_data = page.get_by_test_id("selected-rows-data")
    expect(selected_rows_data).to_contain_text("No rows selected")

    # Select first row
    first_row = frame3.locator(".ag-row").nth(0)
    first_checkbox = first_row.locator(".ag-selection-checkbox input[type='checkbox']")
    first_checkbox.click()
    page.wait_for_timeout(1000)
    expect(first_checkbox).to_be_checked()
    expect(selection_count).to_contain_text("1")
    expect(selected_rows_data).to_contain_text("User1")

    # Select third row as well
    third_row = frame3.locator(".ag-row").nth(2)
    third_checkbox = third_row.locator(".ag-selection-checkbox input[type='checkbox']")
    third_checkbox.click()
    page.wait_for_timeout(1000)
    expect(first_checkbox).to_be_checked()
    expect(third_checkbox).to_be_checked()
    expect(selection_count).to_contain_text("2")
    expect(selected_rows_data).to_contain_text("User1")
    expect(selected_rows_data).to_contain_text("User3")

    # Event name is surfaced
    selection_event_data = page.get_by_test_id("selection-event-data")
    expect(selection_event_data).to_contain_text("selectionChanged")


def test_grid_return_test_4_header_checkbox_select_all(page: Page):
    """Header checkbox selects every row on the current page."""
    radio_option_4 = page.get_by_test_id("stRadio").get_by_text("4")
    radio_option_4.click()

    frame3 = page.locator(".st-key-selection_test_grid")
    expect(frame3.locator(".ag-root")).to_be_visible()
    expect(frame3.locator(".ag-row")).not_to_have_count(0)

    header_checkbox = frame3.locator(
        ".ag-header-row .ag-selection-checkbox input[type='checkbox']"
    ).first
    if header_checkbox.count() == 0:
        header_checkbox = frame3.locator(
            ".ag-header-container input[type='checkbox']"
        ).first
    header_checkbox.click()
    page.wait_for_timeout(1500)
    expect(header_checkbox).to_be_checked()

    selection_count = page.get_by_test_id("selection-count")
    count_text = selection_count.inner_text()
    assert count_text.strip() != "0", f"expected a non-zero selection, got {count_text!r}"

    selected_rows_data = page.get_by_test_id("selected-rows-data")
    expect(selected_rows_data).to_contain_text("User1")

    # Toggle off
    header_checkbox.click()
    page.wait_for_timeout(1500)
    expect(header_checkbox).not_to_be_checked()
    expect(selection_count).to_contain_text("0")
    expect(selected_rows_data).to_contain_text("No rows selected")


def test_grid_return_test_4_pagination_selection(page: Page):
    """Selection persists across pagination."""
    radio_option_4 = page.get_by_test_id("stRadio").get_by_text("4")
    radio_option_4.click()

    frame3 = page.locator(".st-key-selection_test_grid")
    expect(frame3.locator(".ag-root")).to_be_visible()
    expect(frame3.locator(".ag-row")).not_to_have_count(0)

    # First row on page 1
    first_row = frame3.locator(".ag-row").nth(0)
    first_checkbox = first_row.locator(".ag-selection-checkbox input[type='checkbox']")
    first_checkbox.click()
    page.wait_for_timeout(1000)

    selection_count = page.get_by_test_id("selection-count")
    expect(selection_count).to_contain_text("1")

    # Go to page 2
    next_page_button = frame3.get_by_role("button", name="Next Page")
    next_page_button.click()
    page.wait_for_timeout(1000)

    # First row on page 2
    first_row_page2 = frame3.locator(".ag-row").nth(0)
    first_checkbox_page2 = first_row_page2.locator(
        ".ag-selection-checkbox input[type='checkbox']"
    )
    first_checkbox_page2.click()
    page.wait_for_timeout(1000)

    expect(selection_count).to_contain_text("2")

    selected_rows_data = page.get_by_test_id("selected-rows-data")
    expect(selected_rows_data).to_contain_text("User1")
    expect(selected_rows_data).to_contain_text("User11")
