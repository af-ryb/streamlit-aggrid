"""The built-in `stRollup` aggregator: group rows show the server's total.

Values are read from `node.aggData` through each grid's exposed API, and each
node's dimensions are recovered from its first leaf's `row_no` — Python-side
values, so no assertion depends on how a date renders in the browser.
"""

from pathlib import Path

import pytest
from playwright.sync_api import Page

from e2e_utils import StreamlitRunner
from grid_dom import read_rows
from rollup_fixture import DATES, LEAVES, NULL_TOTAL_KEY, expected

ROOT_DIRECTORY = Path(__file__).parent.parent.absolute()
APP_FILE = ROOT_DIRECTORY / "test" / "grid_rollup.py"
GRIDS = ("base", "datetime", "json", "corrupt", "suppress", "pivot", "refresh")
WARNING = "[st_aggrid] stRollup"

_READ_TOTALS = """
([name, colId, afterFilter]) => {
  const api = window.__rollupApis[name];
  const groups = [];
  let root = null;
  const visit = (node) => {
    if (!node.group) return;
    const fields = [];
    let current = node;
    while (current && current.level >= 0) {
      fields.push(current.rowGroupColumn.getColDef().field);
      current = current.parent;
    }
    root = current;
    const leaf = node.allLeafChildren && node.allLeafChildren[0];
    const value = node.aggData ? node.aggData[colId] : null;
    groups.push({ fields, leafNo: leaf ? leaf.data.row_no : null, value: value ?? null });
  };
  if (afterFilter) api.forEachNodeAfterFilter(visit); else api.forEachNode(visit);
  const rootValue = root && root.aggData ? root.aggData[colId] : null;
  return { groups, root: rootValue ?? null };
}
"""


def read_totals(page: Page, name: str, after_filter: bool = False) -> dict:
    return page.evaluate(_READ_TOTALS, [name, "dau", after_filter])


def node_dims(group: dict) -> dict:
    leaf = LEAVES[group["leafNo"]]
    return {field: leaf[field] for field in group["fields"]}


def set_groups(page: Page, name: str, fields: list[str]) -> None:
    page.evaluate(
        "([name, fields]) => window.__rollupApis[name].setRowGroupColumns(fields)",
        [name, fields],
    )
    page.wait_for_timeout(500)


def assert_matches_fixture(totals: dict) -> None:
    assert totals["groups"], "no group rows were read"
    for group in totals["groups"]:
        dims = node_dims(group)
        assert group["value"] == expected(dims), dims
    assert totals["root"] == expected({})


@pytest.fixture(autouse=True, scope="module")
def streamlit_app():
    with StreamlitRunner(APP_FILE) as runner:
        yield runner


@pytest.fixture(autouse=True, scope="function")
def console(page: Page, streamlit_app: StreamlitRunner) -> list[str]:
    """Navigates as part of the fixture: the listener has to be attached
    before the page loads, or the load-time warning is missed."""
    messages: list[str] = []
    page.on("console", lambda message: messages.append(message.text))
    page.goto(streamlit_app.server_url)
    page.wait_for_function(
        "(names) => names.every((n) => window.__rollupApis && window.__rollupApis[n])",
        arg=list(GRIDS),
        timeout=60000,
    )
    page.wait_for_timeout(500)
    return messages


def warnings(messages: list[str]) -> list[str]:
    return [m for m in messages if WARNING in m]


def test_every_group_and_the_grand_total_show_the_server_total(page: Page):
    totals = read_totals(page, "base")
    assert_matches_fixture(totals)
    # Anchor: 1020 summed over six leaves, plus the grand-total offset.
    assert totals["root"] == 21020


def test_the_deepest_group_reads_the_full_grain_total(page: Page):
    deepest = [g for g in read_totals(page, "base")["groups"] if len(g["fields"]) == 2]
    assert len(deepest) == len(LEAVES)
    for group in deepest:
        assert group["value"] == LEAVES[group["leafNo"]]["dau"] + 7


def test_reordering_and_removing_levels_needs_no_rerun(page: Page):
    set_groups(page, "base", ["app_version", "event_date"])
    assert_matches_fixture(read_totals(page, "base"))
    set_groups(page, "base", ["app_version"])
    assert_matches_fixture(read_totals(page, "base"))


def test_a_real_null_version_is_its_own_group(page: Page):
    set_groups(page, "base", ["app_version"])
    groups = read_totals(page, "base")["groups"]
    null_group = [g for g in groups if node_dims(g) == {"app_version": None}]
    assert len(null_group) == 1
    assert null_group[0]["value"] == 1360  # 130 + 230 + 1000, not the grand total


def test_a_server_null_total_is_an_empty_cell(page: Page):
    set_groups(page, "base", ["app_version"])
    groups = read_totals(page, "base")["groups"]
    target = [g for g in groups if node_dims(g) == NULL_TOTAL_KEY]
    assert len(target) == 1 and target[0]["value"] is None


def test_grouping_by_a_field_outside_the_dimensions_is_empty_and_silent(
    page: Page, console: list[str]
):
    before = len(warnings(console))
    set_groups(page, "base", ["platform"])
    totals = read_totals(page, "base")
    assert totals["groups"] and all(g["value"] is None for g in totals["groups"])
    assert totals["root"] == expected({})  # the grand total does not depend on grouping
    assert len(warnings(console)) == before


def test_a_datetime64_date_dimension_matches(page: Page):
    assert_matches_fixture(read_totals(page, "datetime"))


def test_json_transport_matches(page: Page):
    assert_matches_fixture(read_totals(page, "json"))


def test_pivot_mode_shows_no_totals(page: Page):
    pivot = [i for i, n in enumerate(GRIDS) if n == "pivot"][0]
    rows = read_rows(page, pivot)
    cells = [r["dau"] for r in rows.values() if "dau" in r]
    assert cells, "the pivot grid rendered no dau cells"
    assert all(text == "" for text in cells)
