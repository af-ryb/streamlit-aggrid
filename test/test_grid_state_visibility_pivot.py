from pathlib import Path

import pytest

from playwright.sync_api import Page, expect

from e2e_utils import StreamlitRunner

ROOT_DIRECTORY = Path(__file__).parent.parent.absolute()
APP_FILE = ROOT_DIRECTORY / "test" / "grid_state_visibility_pivot.py"


@pytest.fixture(autouse=True, scope="module")
def streamlit_app():
    with StreamlitRunner(APP_FILE) as runner:
        yield runner


@pytest.fixture(autouse=True, scope="function")
def go_to_app(page: Page, streamlit_app: StreamlitRunner):
    page.goto(streamlit_app.server_url)
    page.get_by_role("img", name="Running...").is_hidden()


def test_value_toggle_keeps_row_group(page: Page):
    """In pivot mode, toggling a value column via a merge-mode delta (aggFunc
    set/cleared) must not clear the row group — the merge apply only touches
    grouping when the delta carries row-group entries, which a value-only
    delta does not."""
    container = page.locator(".st-key-grid_pivot_vis")
    expect(container.locator(".ag-root")).to_be_visible()

    auto_group_headers = container.locator(
        '.ag-header-cell[col-id^="ag-Grid-AutoColumn"]'
    )
    top_level_rows = container.locator(".ag-row.ag-row-level-0")

    def header(col_id: str):
        return container.locator(f'.ag-header-cell[col-id="{col_id}"]')

    # Row group active (one auto column, two groups g1/g2); all values shown.
    expect(auto_group_headers).to_have_count(1)
    expect(top_level_rows).to_have_count(2)
    for col in ["x", "y", "z"]:
        expect(header(col)).to_have_count(1)

    # Exclude value column y -> its column disappears (aggFunc cleared)...
    page.get_by_text("val_y", exact=True).click()
    expect(header("y")).to_have_count(0)
    expect(header("x")).to_have_count(1)
    expect(header("z")).to_have_count(1)
    # ...and the row group is untouched (the clobber guard).
    expect(auto_group_headers).to_have_count(1)
    expect(top_level_rows).to_have_count(2)

    # Re-include y -> reappears, row group still intact.
    page.get_by_text("val_y", exact=True).click()
    expect(header("y")).to_have_count(1)
    expect(auto_group_headers).to_have_count(1)
    expect(top_level_rows).to_have_count(2)
