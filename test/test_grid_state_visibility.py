from pathlib import Path

import pytest

from playwright.sync_api import Page, expect

from e2e_utils import StreamlitRunner

ROOT_DIRECTORY = Path(__file__).parent.parent.absolute()
APP_FILE = ROOT_DIRECTORY / "test" / "grid_state_visibility.py"


@pytest.fixture(autouse=True, scope="module")
def streamlit_app():
    with StreamlitRunner(APP_FILE) as runner:
        yield runner


@pytest.fixture(autouse=True, scope="function")
def go_to_app(page: Page, streamlit_app: StreamlitRunner):
    page.goto(streamlit_app.server_url)
    page.get_by_role("img", name="Running...").is_hidden()


def test_merge_mode_toggles_visibility_preserving_others(page: Page):
    """A merge-mode columns_state delta shows/hides only the governed columns it
    lists; the structural `id` column and the existing column order are
    untouched (applyOrder:false)."""
    container = page.locator(".st-key-grid_visibility")
    expect(container.locator(".ag-root")).to_be_visible()

    def header(col_id: str):
        return container.locator(f'.ag-header-cell[col-id="{col_id}"]')

    # All columns visible initially.
    for col in ["id", "a", "b", "c", "d"]:
        expect(header(col)).to_have_count(1)

    # Exclude b via the inline control — the merge delta hides only b.
    page.get_by_text("show_b", exact=True).click()
    expect(header("b")).to_have_count(0)
    for col in ["id", "a", "c", "d"]:
        expect(header(col)).to_have_count(1)

    # Exclude d too.
    page.get_by_text("show_d", exact=True).click()
    expect(header("d")).to_have_count(0)
    for col in ["id", "a", "c"]:
        expect(header(col)).to_have_count(1)

    # Order preserved (merge uses applyOrder:false): id first, a before c.
    col_ids = container.locator(".ag-header-cell").evaluate_all(
        "els => els.map(e => e.getAttribute('col-id'))"
    )
    visible_known = [c for c in col_ids if c in ("id", "a", "c")]
    assert visible_known == ["id", "a", "c"]

    # Re-include b — a previously hidden column comes back.
    page.get_by_text("show_b", exact=True).click()
    expect(header("b")).to_have_count(1)
    expect(header("d")).to_have_count(0)
