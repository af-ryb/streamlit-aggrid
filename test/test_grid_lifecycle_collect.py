"""gridReady and firstDataRendered as zero-interaction auto-collect triggers.

Collector invocations are counted from the browser console, not from what
arrived in Python. `on_grid_state_change` runs only when the component's state
value changes, so a second, byte-identical collect would be invisible on the
Python side — and a second collect is exactly the regression this suite guards:
AG-Grid queues the `firstDataRendered` dispatch into requestAnimationFrame, so
a listener attached from a React effect in the same tick does win the race.

The `debug=True` console line the count comes from is emitted by
`useAutoCollect` immediately before it posts the result to the host, so it
tracks collector calls one for one.
"""

import json
import re
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

from e2e_utils import StreamlitRunner

ROOT_DIRECTORY = Path(__file__).parent.parent.absolute()
APP_FILE = ROOT_DIRECTORY / "test" / "grid_lifecycle_collect.py"

COLLECT_LINE = re.compile(r'\[useAutoCollect\] Event "([^"]+)"')

#: How long to wait before asserting that nothing else fired. Every positive
#: assertion runs first and has already waited for a full browser -> Streamlit
#: -> browser round trip, so this only has to cover a late duplicate.
SETTLE_MS = 1500


@pytest.fixture(autouse=True, scope="module")
def streamlit_app():
    with StreamlitRunner(APP_FILE) as runner:
        yield runner


@pytest.fixture
def collected(page: Page, streamlit_app: StreamlitRunner):
    """Event names the frontend collector was invoked with, in order.

    Navigates as part of the fixture: the console listener has to be attached
    before the first load or the page's own lines are missed.
    """
    names: list[str] = []

    def _on_console(message):
        found = COLLECT_LINE.search(message.text)
        if found:
            names.append(found.group(1))

    page.on("console", _on_console)
    page.goto(streamlit_app.server_url)
    page.get_by_role("img", name="Running...").is_hidden()
    return names


def select_case(page: Page, case: str) -> None:
    page.get_by_test_id("stRadio").get_by_text(case, exact=True).click()


def test_grid_ready_collects_once_without_interaction(page: Page, collected):
    select_case(page, "gridReady")

    expect(page.get_by_test_id("fires-lc_ready")).to_have_text("gridReady")

    page.wait_for_timeout(SETTLE_MS)
    assert collected == ["gridReady"]


def test_first_data_rendered_collects_once_without_interaction(page: Page, collected):
    select_case(page, "firstDataRendered")

    expect(page.get_by_test_id("fires-lc_first")).to_have_text("firstDataRendered")

    page.wait_for_timeout(SETTLE_MS)
    assert collected == ["firstDataRendered"]


def test_both_triggers_fire_once_each_and_in_order(page: Page, collected):
    """gridOptions handlers are queued until gridReady has fired, so the order
    is a property of AG-Grid, not of luck."""
    select_case(page, "both")

    expect(page.get_by_test_id("fires-lc_both")).to_have_text(
        "gridReady,firstDataRendered"
    )

    page.wait_for_timeout(SETTLE_MS)
    assert collected == ["gridReady", "firstDataRendered"]


def test_grid_ready_snapshot_is_post_restore(page: Page, collected):
    """The ordering trap: a collect placed before the restore block in
    onGridReady returns the columnDefs layout, and the feature then lies."""
    select_case(page, "restore")

    state_element = page.get_by_test_id("state-lc_restore")
    expect(state_element).to_contain_text("rowGroupIndex")

    state = json.loads(state_element.inner_text())
    by_id = {entry["colId"]: entry for entry in state}
    assert by_id["region"]["rowGroupIndex"] == 0
    assert by_id["channel"]["hide"] is True


def test_empty_grid_never_fires_first_data_rendered(page: Page, collected):
    select_case(page, "empty")

    grid = page.locator(".st-key-lc_empty")
    expect(grid.locator(".ag-root")).to_be_visible()
    expect(grid.locator(".ag-row")).to_have_count(0)

    page.wait_for_timeout(SETTLE_MS)
    assert collected == []
    expect(page.get_by_test_id("fires-lc_empty")).to_have_text("")


def test_user_handler_is_chained_and_runs_once(page: Page, collected):
    """A prop of the same name replaces the gridOptions key rather than adding
    to it, so the chain is hand-written — and a hand-written chain is where a
    handler gets called twice."""
    select_case(page, "chain")

    expect(page.get_by_test_id("fires-lc_chain")).to_have_text("firstDataRendered")

    page.wait_for_timeout(SETTLE_MS)
    assert collected == ["firstDataRendered"]
    assert page.evaluate("window.__userFirstDataRendered") == 1
