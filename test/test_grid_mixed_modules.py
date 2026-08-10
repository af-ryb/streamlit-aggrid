from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

from e2e_utils import StreamlitRunner

ROOT_DIRECTORY = Path(__file__).parent.parent.absolute()
BASIC_EXAMPLE_FILE = ROOT_DIRECTORY / "test" / "grid_mixed_modules.py"


@pytest.fixture(autouse=True, scope="module")
def streamlit_app():
    with StreamlitRunner(BASIC_EXAMPLE_FILE) as runner:
        yield runner


@pytest.fixture(autouse=True, scope="function")
def go_to_app(page: Page, streamlit_app: StreamlitRunner):
    page.goto(streamlit_app.server_url)
    page.get_by_role("img", name="Running...").is_hidden()


def test_both_grids_render(page: Page):
    expect(page.locator(".st-key-community_grid").locator(".ag-root")).to_be_visible()
    expect(page.locator(".st-key-enterprise_grid").locator(".ag-root")).to_be_visible()


def test_enterprise_grid_gets_its_modules_despite_the_community_grid(page: Page):
    """The sidebar only exists if AllEnterpriseModule was registered.

    A module-level latch set by the community grid above would swallow the
    enterprise registration and leave this locator empty.
    """
    enterprise = page.locator(".st-key-enterprise_grid")
    expect(enterprise.locator(".ag-side-bar")).to_be_visible()


def test_community_grid_renders_no_sidebar_because_it_asked_for_none(page: Page):
    """This does not prove the community grid lacks enterprise modules.

    ``ModuleRegistry`` is process-global, so once the enterprise grid on this
    page registers, enterprise modules are available to every grid, including
    this one. The sidebar is absent only because this grid's ``gridOptions``
    never enabled one.
    """
    community = page.locator(".st-key-community_grid")
    expect(community.locator(".ag-side-bar")).to_have_count(0)


def test_pressing_r_over_a_grid_cell_does_not_rerun_the_app(page: Page):
    """Streamlit binds "r" to rerun on the document. Without an iframe the grid
    must stop that key from escaping, or keyboard use silently reruns the app.
    """
    counter = page.locator(".st-key-run_count")

    community = page.locator(".st-key-community_grid")
    cell = community.locator(".ag-cell").first
    cell.click()

    # The click itself may trigger a rerun (selection). Let that settle before
    # taking the baseline, or the rerun it causes would be blamed on the "r".
    page.wait_for_timeout(1000)
    before = counter.inner_text()

    page.keyboard.press("r")
    page.wait_for_timeout(1500)

    assert counter.inner_text() == before
