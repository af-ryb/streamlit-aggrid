from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

from e2e_utils import StreamlitRunner


ROOT_DIRECTORY = Path(__file__).parent.parent.absolute()
BASIC_EXAMPLE_FILE = ROOT_DIRECTORY / "test" / "grid_drag_and_drop_example.py"


@pytest.fixture(autouse=True, scope="module")
def streamlit_app():
    with StreamlitRunner(BASIC_EXAMPLE_FILE) as runner:
        yield runner


@pytest.fixture(autouse=True, scope="function")
def go_to_app(page: Page, streamlit_app: StreamlitRunner):
    page.goto(streamlit_app.server_url)
    page.get_by_role("img", name="Running...").is_hidden()


def test_drag_grid_configures_row_drag_handles(page: Page):
    """Verify row drag is wired up: handles exist and rows render in order."""
    frame = page.locator(".st-key-drag_grid")
    expect(frame.locator(".ag-root")).to_be_visible()

    rows = frame.locator(".ag-center-cols-container .ag-row")
    expect(rows).to_have_count(4)

    # rowDrag + rowDragManaged → .ag-row-drag handle per row
    expect(frame.locator(".ag-row-drag")).to_have_count(4)

    # Initial row order is stable
    ids = [rows.nth(i).locator('[col-id="id"]').inner_text() for i in range(4)]
    row_indices = [int(rows.nth(i).get_attribute("aria-rowindex")) for i in range(4)]
    ordered_ids = [rid for _, rid in sorted(zip(row_indices, ids))]
    assert ordered_ids == ["1", "2", "3", "4"]


@pytest.mark.skip(
    reason=(
        "AG-Grid's DragService does not respond to Playwright's synthesised "
        "pointer/mouse events. Row reordering cannot be reliably simulated in "
        "a headless browser. The companion test above verifies that row drag "
        "is configured and handles are rendered."
    )
)
def test_drag_first_row_to_last(page: Page):
    frame = page.locator(".st-key-drag_grid")
    first_row_handle = (
        frame.locator(".ag-center-cols-container .ag-row")
        .nth(0)
        .locator(".ag-row-drag")
    )
    last_row = frame.locator(".ag-center-cols-container .ag-row").nth(-1)
    first_row_handle.drag_to(last_row)
    page.wait_for_timeout(500)
    rows = frame.locator(".ag-center-cols-container .ag-row")
    ids = [rows.nth(i).locator('[col-id="id"]').inner_text() for i in range(rows.count())]
    row_indices = [int(rows.nth(i).get_attribute("aria-rowindex")) for i in range(rows.count())]
    sorted_ids = [rid for _, rid in sorted(zip(row_indices, ids))]
    assert sorted_ids == ["2", "3", "1", "4"]
    for i in range(rows.count()):
        if rows.nth(i).locator('[col-id="id"]').inner_text() == "1":
            assert rows.nth(i).get_attribute("aria-rowindex") == "4"
