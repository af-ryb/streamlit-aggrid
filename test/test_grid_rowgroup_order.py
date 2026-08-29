from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

from e2e_utils import StreamlitRunner

ROOT_DIRECTORY = Path(__file__).parent.parent.absolute()
APP_FILE = ROOT_DIRECTORY / "test" / "grid_rowgroup_order.py"


@pytest.fixture(autouse=True, scope="module")
def streamlit_app():
    with StreamlitRunner(APP_FILE) as runner:
        yield runner


@pytest.fixture(autouse=True, scope="function")
def go_to_app(page: Page, streamlit_app: StreamlitRunner):
    page.goto(streamlit_app.server_url)
    page.get_by_role("img", name="Running...").is_hidden()


def _group_col_order(frame):
    """Displayed left-to-right colIds of the multipleColumns auto-group columns."""
    ids = frame.locator(".ag-header-cell").evaluate_all(
        "els => els.map(e => e.getAttribute('col-id'))"
    )
    return [c for c in ids if c and c.startswith("ag-Grid-AutoColumn")]


def test_group_columns_track_rowgroup_order_after_dimension_swap(page: Page):
    """A row-dimension change must keep the swapped dimension at its assigned
    group level, not send it to the leftmost group column (v36 regression)."""
    frame = page.locator(".st-key-grid_rowgroup_order")
    expect(frame.locator(".ag-root")).to_be_visible()
    expect(
        frame.locator(".ag-header-cell[col-id^='ag-Grid-AutoColumn']")
    ).to_have_count(3)

    # Initial order follows row-group order: day (0), network (1), ad_unit (2).
    assert _group_col_order(frame) == [
        "ag-Grid-AutoColumn-day",
        "ag-Grid-AutoColumn-network",
        "ag-Grid-AutoColumn-ad_unit",
    ]

    # Swap row_2 from network to campaign. The newly-created `campaign`
    # auto-group column must appear at its level-1 (middle) slot, not jump to
    # the front.
    page.get_by_role("button", name="Cycle row_2").click()
    expect(
        frame.locator(".ag-header-cell[col-id='ag-Grid-AutoColumn-campaign']")
    ).to_be_visible()
    page.wait_for_timeout(600)

    assert _group_col_order(frame) == [
        "ag-Grid-AutoColumn-day",
        "ag-Grid-AutoColumn-campaign",
        "ag-Grid-AutoColumn-ad_unit",
    ]
