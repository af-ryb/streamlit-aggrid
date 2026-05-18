from pathlib import Path

import pytest

from playwright.sync_api import Page, expect

from e2e_utils import StreamlitRunner

ROOT_DIRECTORY = Path(__file__).parent.parent.absolute()
SORT_PERSIST_FILE = ROOT_DIRECTORY / "test" / "grid_sort_persist.py"


@pytest.fixture(autouse=True, scope="module")
def streamlit_app():
    with StreamlitRunner(SORT_PERSIST_FILE) as runner:
        yield runner


@pytest.fixture(autouse=True, scope="function")
def go_to_app(page: Page, streamlit_app: StreamlitRunner):
    page.goto(streamlit_app.server_url)
    page.get_by_role("img", name="Running...").is_hidden()


def test_sort_persists_across_rerun(page: Page):
    """Regression: an interactive sort must survive a rerun that changes
    rowData and columnDefs, instead of reverting to the colDef `initialSort`
    default.

    Root cause (v2_component branch): the runtime-update useEffect in
    ``AgGridComponent`` called ``updateGridOptions`` whenever gridOptions
    changed. Re-processing columnDefs reverted the sort to ``initialSort``,
    and nothing snapshotted/restored the live sort — unlike hide/rowGroup/
    pivot/pinned, which ``extractColumnStateFromDefs`` re-pushes.
    """
    container = page.locator(".st-key-grid_sort_persist")
    expect(container.locator(".ag-root")).to_be_visible()

    first_name = container.locator(
        '.ag-center-cols-container .ag-row[row-index="0"] [col-id="name"]'
    )

    # Initial render: default sort is id descending, so the top row is the
    # highest id (3) -> name "cherry".
    expect(first_name).to_have_text("cherry")

    # Sort the `name` column ascending by clicking its header.
    name_header = container.locator('.ag-header-cell[col-id="name"]')
    name_header.click()
    expect(name_header).to_have_attribute("aria-sort", "ascending")
    # Top row is now alphabetically first: "apple".
    expect(first_name).to_have_text("apple")

    # Switch the date range — reruns with new rowData and a new headerName
    # for the `name` column (columnDefs change -> updateGridOptions path).
    page.get_by_role("button", name="Switch date range").click()

    # The user's name-ascending sort must persist: top row of the 2025
    # range is "date" (not "fig", which is what id-descending would give).
    expect(name_header).to_have_attribute("aria-sort", "ascending")
    expect(first_name).to_have_text("date")
