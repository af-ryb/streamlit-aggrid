from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

from e2e_utils import StreamlitRunner

ROOT_DIRECTORY = Path(__file__).parent.parent.absolute()
APP_FILE = ROOT_DIRECTORY / "test" / "grid_rowgroup_interactive.py"


@pytest.fixture(autouse=True, scope="module")
def streamlit_app():
    with StreamlitRunner(APP_FILE) as runner:
        yield runner


@pytest.fixture(autouse=True, scope="function")
def go_to_app(page: Page, streamlit_app: StreamlitRunner):
    page.goto(streamlit_app.server_url)
    page.get_by_role("img", name="Running...").is_hidden()


def _group_col_order(frame):
    ids = frame.locator(".ag-header-cell").evaluate_all(
        "els => els.map(e => e.getAttribute('col-id'))"
    )
    return [c for c in ids if c and c.startswith("ag-Grid-AutoColumn")]


def test_interactive_rowgroup_reorder_syncs_group_columns(page: Page):
    """Reordering the row groups interactively (here via the exposed grid API,
    mimicking a Row Groups panel drag) must re-sync the displayed
    multipleColumns auto-group columns to the new row-group order."""
    frame = page.locator(".st-key-grid_rowgroup_interactive")
    expect(frame.locator(".ag-root")).to_be_visible()
    expect(
        frame.locator(".ag-header-cell[col-id^='ag-Grid-AutoColumn']")
    ).to_have_count(3)

    assert _group_col_order(frame) == [
        "ag-Grid-AutoColumn-day",
        "ag-Grid-AutoColumn-network",
        "ag-Grid-AutoColumn-ad_unit",
    ]

    # Reorder row groups to ad_unit -> day -> network (as a panel drag would).
    page.evaluate(
        "window.__gridApi.setRowGroupColumns(['ad_unit','day','network'])"
    )
    page.wait_for_timeout(800)

    assert _group_col_order(frame) == [
        "ag-Grid-AutoColumn-ad_unit",
        "ag-Grid-AutoColumn-day",
        "ag-Grid-AutoColumn-network",
    ]
