from pathlib import Path

import pytest

from playwright.sync_api import Page, expect

from e2e_utils import StreamlitRunner

ROOT_DIRECTORY = Path(__file__).parent.parent.absolute()
APP_FILE = ROOT_DIRECTORY / "test" / "grid_35_3_features.py"


@pytest.fixture(autouse=True, scope="module")
def streamlit_app():
    with StreamlitRunner(APP_FILE) as runner:
        yield runner


@pytest.fixture(autouse=True, scope="function")
def go_to_app(page: Page, streamlit_app: StreamlitRunner):
    page.goto(streamlit_app.server_url)
    page.get_by_role("img", name="Running...").is_hidden()


def _select(page: Page, n: int):
    page.get_by_test_id("stRadio").get_by_text(str(n), exact=True).click()
    page.wait_for_timeout(1500)


def test_find_highlights_and_widget(page: Page):
    """findSearchValue passthrough highlights matches; the show_find toolbar
    widget is wired into the DOM."""
    _select(page, 1)
    c = page.locator(".st-key-find_grid")
    expect(c.locator(".ag-root")).to_be_visible()
    # "apple" matches "apple" and "pineapple" → at least one highlighted match.
    expect(c.locator(".ag-find-match").first).to_be_visible(timeout=10000)
    # The toolbar Find input is present (hover-revealed, but always in the DOM).
    expect(c.locator(".toolbar-find input")).to_have_count(1)


def test_native_toolbar_renders(page: Page):
    """The `toolbar` convenience param renders AG-Grid's native Quick Access
    Toolbar in the grid chrome."""
    _select(page, 2)
    c = page.locator(".st-key-toolbar_grid")
    expect(c.locator(".ag-root")).to_be_visible()
    expect(c.locator(".ag-toolbar")).to_be_visible()
    expect(c.locator(".ag-toolbar-item").first).to_be_visible()


def test_readonly_notes_indicator(page: Page):
    """A host-seeded read-only note marks its cell with the has-notes class."""
    _select(page, 3)
    c = page.locator(".st-key-notes_ro_grid")
    expect(c.locator(".ag-root")).to_be_visible()
    expect(c.locator(".ag-has-cell-notes")).to_have_count(1)


def test_editable_notes_render_without_spurious_writeback(page: Page):
    """An editable-notes grid renders the seeded note and does NOT post a
    write-back until the user actually edits a note (result.notes stays None)."""
    _select(page, 4)
    c = page.locator(".st-key-notes_edit_grid")
    expect(c.locator(".ag-root")).to_be_visible()
    expect(c.locator(".ag-has-cell-notes")).to_have_count(1)
    expect(page.get_by_test_id("notes-writeback")).to_have_text("None")
