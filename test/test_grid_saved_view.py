from pathlib import Path

import pytest

from playwright.sync_api import Page, expect

from e2e_utils import StreamlitRunner

ROOT_DIRECTORY = Path(__file__).parent.parent.absolute()
APP_FILE = ROOT_DIRECTORY / "test" / "grid_saved_view.py"


@pytest.fixture(autouse=True, scope="module")
def streamlit_app():
    with StreamlitRunner(APP_FILE) as runner:
        yield runner


@pytest.fixture(autouse=True, scope="function")
def go_to_app(page: Page, streamlit_app: StreamlitRunner):
    page.goto(streamlit_app.server_url)
    page.get_by_role("img", name="Running...").is_hidden()


def test_initial_state_restore_and_remount(page: Page):
    """A raw `initial_state` (GridState) is applied at creation; switching views
    changes the grid key, which remounts the component so AG-Grid re-reads it."""
    # Default view hides b.
    c1 = page.locator(".st-key-grid_view_view_hide_b")
    expect(c1.locator(".ag-root")).to_be_visible()
    expect(c1.locator('.ag-header-cell[col-id="a"]')).to_have_count(1)
    expect(c1.locator('.ag-header-cell[col-id="b"]')).to_have_count(0)
    expect(c1.locator('.ag-header-cell[col-id="c"]')).to_have_count(1)

    # Switch view -> remount -> re-read initialState (hides c, sorts a desc).
    page.get_by_text("view_hide_c_sort_a", exact=True).click()
    c2 = page.locator(".st-key-grid_view_view_hide_c_sort_a")
    expect(c2.locator(".ag-root")).to_be_visible()
    expect(c2.locator('.ag-header-cell[col-id="a"]')).to_have_count(1)
    expect(c2.locator('.ag-header-cell[col-id="b"]')).to_have_count(1)
    expect(c2.locator('.ag-header-cell[col-id="c"]')).to_have_count(0)
    # Sort from the saved view is applied.
    expect(c2.locator('.ag-header-cell[col-id="a"]')).to_have_attribute(
        "aria-sort", "descending"
    )
