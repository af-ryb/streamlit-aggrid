from pathlib import Path

import pytest

from playwright.sync_api import Page, expect

from e2e_utils import StreamlitRunner

ROOT_DIRECTORY = Path(__file__).parent.parent.absolute()
ROWGROUP_FILE = ROOT_DIRECTORY / "test" / "grid_rowgroup.py"


@pytest.fixture(autouse=True, scope="module")
def streamlit_app():
    with StreamlitRunner(ROWGROUP_FILE) as runner:
        yield runner


@pytest.fixture(autouse=True, scope="function")
def go_to_app(page: Page, streamlit_app: StreamlitRunner):
    page.goto(streamlit_app.server_url)
    page.get_by_role("img", name="Running...").is_hidden()


def test_toggle_rowgroup(page: Page):
    """Regression: rowGroupIndex flipping from None to a number after the
    initial render must add the column as a row group, and flipping back to
    None must remove it.

    Root cause of the original bug (v2_state branch):
      1. ``AgGridComponent``'s runtime-update useEffect captured
         ``prevDataRef.current`` only after a ``gridApi`` guard. On first
         mount AG-Grid's ``onGridReady`` fires asynchronously after React's
         effect phase, so the guard returned early and the ref was never
         populated. The next widget-driven ``data`` change then saw
         ``prevData === undefined`` and returned early at the subsequent
         "first commit" guard, silently dropping the rowGroup update.
      2. ``extractRowGroupColumns`` / ``extractColumnStateFromDefs`` used
         ``??`` to pick between ``rowGroupIndex`` and
         ``initialRowGroupIndex``, so Python's ``None`` (JSON ``null``) fell
         through to the initial variant and left the column row-grouped on
         the ungroup transition.
    """
    container = page.locator(".st-key-grid_toggle_rowgroup")
    expect(container.locator(".ag-root")).to_be_visible()

    auto_group_headers = container.locator(
        '.ag-header-cell[col-id^="ag-Grid-AutoColumn"]'
    )
    top_level_rows = container.locator(".ag-row.ag-row-level-0")
    sub_level_rows = container.locator(".ag-row.ag-row-level-1")

    # Initial state: ``level_order`` is grouped (``initialRowGroupIndex=0``)
    # but ``groupby`` is not (``rowGroupIndex=None`` overrides the initial).
    # Expect one auto-group header and three level-0 group rows (level_order
    # values 1/2/3), no level-1 rows.
    expect(auto_group_headers).to_have_count(1)
    expect(top_level_rows).to_have_count(3)
    expect(sub_level_rows).to_have_count(0)

    # Toggle on: ``groupby`` joins as the second row group. Expect two
    # auto-group headers and six level-1 group rows (3 × 2).
    page.get_by_role("button", name="Toggle rowGroup").click()
    expect(auto_group_headers).to_have_count(2)
    expect(top_level_rows).to_have_count(3)
    expect(sub_level_rows).to_have_count(6)

    # Toggle off: must drop ``groupby`` back out of row groups even though
    # ``initialRowGroupIndex`` is still 1 (covers the secondary ``??`` fix).
    page.get_by_role("button", name="Toggle rowGroup").click()
    expect(auto_group_headers).to_have_count(1)
    expect(top_level_rows).to_have_count(3)
    expect(sub_level_rows).to_have_count(0)
