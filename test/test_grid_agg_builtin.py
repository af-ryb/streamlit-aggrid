"""`stRatio`'s `den_const` and its fallback-to-`sum` behaviour, exercised
through the built-in aggregator.

`grid_agg_builtin.py` is the new home for every aggregator this coverage plan
adds; this suite covers what Task 3 and Task 4 add to it. Task 3's `share`
column has a denominator that is `SHARE_SPEC.den_const` (a window-wide
constant) rather than a summed field, and `mixed_den` proves that constant
*combines* with a real summed `den` field rather than one silently replacing
the other. Task 4 covers grid index 2 — a grid with no ratio columns at all,
proving `stRatio` degrades to a plain `sum` instead of blanking a column that
carries `aggFunc: "stRatio"` with no `context["stRatio"]` declaration,
acquired at runtime through two different mechanisms (`cost` via
`columns_state` merge, `installs` via `initial_state` — see the "Fallback"
section below for why both are runtime-acquired rather than one being
parse-time-declared, as originally scoped). `stRatio`'s base semantics
already have their regression baseline in `test_grid_ratio_builtin.py`,
which stays frozen and green.

Row indices for the row-group grid (index 0) and the fallback grid (index 2)
mirror `test_grid_ratio_builtin.py` exactly: same fixture, same two-level
grouping (campaign then country), same eight leaf rows, so a broken
`den_const` — or a broken fallback — cannot hide behind a different tree
shape.
"""

from pathlib import Path

import pytest
from playwright.sync_api import Page

from e2e_utils import StreamlitRunner
from grid_dom import assert_number, grand_total_row, read_rows
from ratio_fixture import RATIO_ROWS, RatioSpec, SHARE_SPEC, evaluate, rows_where

ROOT_DIRECTORY = Path(__file__).parent.parent.absolute()
BUILTIN_FILE = ROOT_DIRECTORY / "test" / "grid_agg_builtin.py"

ROWGROUP_GRID = 0
PIVOT_GRID = 1
FALLBACK_GRID = 2

SHARE_COL = SHARE_SPEC.col_id

# Body row indices of the fully expanded row-group grid — identical to
# `test_grid_ratio_builtin.py`'s RAW_GRID, same fixture and grouping:
#   0 A            4 A/DE          8  B/US        12 B/DE row 0
#   1 A/US         5 A/DE row 0    9  B/US row 0  13 B/DE row 1
#   2 A/US row 0   6 A/DE row 1    10 B/US row 1
#   3 A/US row 1   7 B            11 B/DE
# The grand total follows at row-index 14; find it with `grand_total_row`.
GROUP_ROW_DIMS = {
    0: {"campaign": "A"},
    1: {"campaign": "A", "country": "US"},
    4: {"campaign": "A", "country": "DE"},
    7: {"campaign": "B"},
    8: {"campaign": "B", "country": "US"},
    11: {"campaign": "B", "country": "DE"},
}
LEAF_ROW_SOURCE = {2: 0, 3: 1, 5: 2, 6: 3, 9: 4, 10: 5, 12: 6, 13: 7}

# Mirrors `grid_agg_builtin.MIXED_DEN_SPEC` exactly — same col_id, same
# fields, same constant. Apps in this repo run via `streamlit
# run`/`StreamlitRunner`, never as an imported module: importing one directly
# executes its top-level `AgGrid()` calls outside a Streamlit run context and
# raises. So the spec is declared independently here rather than shared by
# import, the same way `GROUP_ROW_DIMS` above independently encodes the app's
# grouping structure rather than importing it.
MIXED_DEN_SPEC = RatioSpec(
    col_id="mixed_den",
    header="Cost / (rebate + const)",
    num=("cost",),
    den=("rebate",),
    den_const=200.0,
)


@pytest.fixture(autouse=True, scope="module")
def streamlit_app():
    with StreamlitRunner(BUILTIN_FILE) as runner:
        yield runner


@pytest.fixture(autouse=True, scope="function")
def go_to_app(page: Page, streamlit_app: StreamlitRunner):
    page.goto(streamlit_app.server_url)
    page.get_by_role("img", name="Running...").is_hidden()
    page.wait_for_selector(".ag-root-wrapper", timeout=60000)
    # Three grids: row-group, pivot, and (Task 4) the fallback grid.
    page.wait_for_function(
        "() => document.querySelectorAll('.ag-root-wrapper').length >= 3",
        timeout=60000,
    )
    page.wait_for_selector('[row-index="14"]', timeout=60000)
    # The row-group grid (index 0) and the fallback grid (index 2) share the
    # same two-level grouping, so both reach row-index 14 — the selector
    # above is unscoped and could be satisfied by grid 0 alone while grid 2 is
    # still mounting. Wait on grid 2 specifically so its tests never read a
    # half-rendered tree.
    page.wait_for_function(
        """() => {
             const grid = document.querySelectorAll('.ag-root-wrapper')[2];
             return grid !== undefined && grid.querySelector('[row-index="14"]') !== null;
           }""",
        timeout=60000,
    )


def test_share_group_rows_match_the_fixture_at_both_levels(page: Page):
    rows = read_rows(page, ROWGROUP_GRID)

    for row_index, dims in GROUP_ROW_DIMS.items():
        assert_number(
            rows[f"body:{row_index}"][SHARE_COL],
            evaluate(SHARE_SPEC, rows_where(**dims)),
            f"row {row_index} {dims} share",
        )


def test_share_leaf_rows_show_the_per_row_share(page: Page):
    rows = read_rows(page, ROWGROUP_GRID)

    for row_index, source_index in LEAF_ROW_SOURCE.items():
        source_row = RATIO_ROWS[source_index]
        assert_number(
            rows[f"body:{row_index}"][SHARE_COL],
            evaluate(SHARE_SPEC, [source_row]),
            f"leaf {row_index} share",
        )


def test_share_grand_total_is_exactly_100(page: Page):
    """The anchor: `den_const` is added once for the whole grid, not once per
    leaf. `Σcost` across all eight rows is exactly `1020` — the same number
    declared as `den_const` — so the grand total must equal exactly `100.0`.
    An aggregator that folded `den_const` per leaf (multiplying it by the
    child count) would blow this number far past 100, not land close to it.
    """
    total = grand_total_row(read_rows(page, ROWGROUP_GRID))
    assert float(total[SHARE_COL]) == 100.0


def test_den_const_combines_with_a_summed_den_rather_than_replacing_it(page: Page):
    """`share`'s `den` is empty, so nothing above proves `denominator =
    den_const + Σden` actually adds both terms instead of one silently
    overriding the other. `mixed_den` (`cost / (rebate + 200)`) has both:
    checked at a folded group row (campaign A, two levels of children folded
    through `sums`) and at the grand total (every leaf folded), so a `+` that
    quietly became a `den_const`-only or `den`-only computation would show up
    at both.
    """
    rows = read_rows(page, ROWGROUP_GRID)

    assert_number(
        rows["body:0"][MIXED_DEN_SPEC.col_id],
        evaluate(MIXED_DEN_SPEC, rows_where(campaign="A")),
        "campaign A mixed_den",
    )
    assert_number(
        grand_total_row(rows)[MIXED_DEN_SPEC.col_id],
        evaluate(MIXED_DEN_SPEC, rows_where()),
        "grand total mixed_den",
    )


# --------------------------------------------------------------------------
# Pivot
# --------------------------------------------------------------------------


def pivot_col(country: str) -> str:
    return f"pivot_country_{country}_{SHARE_COL}"


def pivot_total_col() -> str:
    return f"PivotRowTotal_pivot_country__{SHARE_COL}"


def test_share_pivot_cells_compute_their_own_share(page: Page):
    """`share` has no `den` field to fold — only `den_const` — so a pivot cell
    that dropped the constant per pivot key would render blank instead of
    wrong. This proves the constant reaches every pivot cell, and that each
    cell computes its own (campaign, country) share rather than leaking its
    row's total."""
    rows = read_rows(page, PIVOT_GRID)

    for row_index, campaign in ((0, "A"), (1, "B")):
        cells = rows[f"body:{row_index}"]
        for country in ("US", "DE"):
            assert_number(
                cells[pivot_col(country)],
                evaluate(SHARE_SPEC, rows_where(campaign=campaign, country=country)),
                f"{campaign}/{country} share",
            )


def test_share_pivot_row_totals_match_the_fixture(page: Page):
    rows = read_rows(page, PIVOT_GRID)

    for row_index, campaign in ((0, "A"), (1, "B")):
        assert_number(
            rows[f"body:{row_index}"][pivot_total_col()],
            evaluate(SHARE_SPEC, rows_where(campaign=campaign)),
            f"{campaign} row total share",
        )


def test_share_pivot_grand_total_is_exactly_100(page: Page):
    """Same anchor as the row-group grid's, reached through the pivot's row
    total instead: `den_const` added once for the grid, not once per pivot
    key."""
    total = grand_total_row(read_rows(page, PIVOT_GRID))
    assert float(total[pivot_total_col()]) == 100.0


# --------------------------------------------------------------------------
# Fallback (Task 4): stRatio degrades to sum without a declaration
# --------------------------------------------------------------------------
#
# `grid_agg_builtin.fallback_grid_options()` declares no `RATIO_COLUMNS` at
# all: both `cost` and `installs` carry `aggFunc: "sum"` in `columnDefs`.
#
# The brief's original framing called for one column declaring
# `aggFunc: "stRatio"` directly in `columnDefs` with no `context` — the
# "parse-time" path. That construction turns out to be unreachable through
# the public `AgGrid()` API: `validate_ratio_columns` (`ratio.py`) rejects
# *any* colDef declaring `aggFunc: "stRatio"` with no `context["stRatio"]`,
# unconditionally, before the grid options ever leave Python — pinned by
# `test/unit/test_ratio_validation.py::test_agg_func_without_a_context_is_rejected`.
# That guard runs over every column in the *original* `columnDefs`
# regardless of DataFrame/rowData mode, so it is a structural guarantee: any
# column that reaches `stRatioAggFunc` with `aggFunc === "stRatio"` in the
# colDef Python built is also guaranteed a structurally valid `context`,
# meaning `readStRatioConfig` cannot return `null` for it. `null` is only
# reachable for a column whose `aggFunc` became `"stRatio"` *after* Python
# validated it — runtime acquisition, unconditionally. That is also exactly
# the real-world bug this task exists to fix: the columns tool panel's
# aggregation picker is itself a runtime mutation Python never sees.
#
# `cost` and `installs` each exercise a different, genuine runtime-mutation
# route — both existing, documented `AgGrid()` features, both entirely
# outside `columnDefs` so `validate_ratio_columns` never inspects either and
# `registerStRatio`'s `columnDefs` walk never attaches a comparator to
# either:
#
# - `installs` is switched to `stRatio` via the raw `initial_state` prop
#   (`GridState.aggregation.aggregationModel`), applied pre-paint, before
#   the grid is created.
# - `cost` is switched to `stRatio` via `columns_state` in `"merge"` mode
#   (a `ColumnState[]` overlay), applied post-creation in `onGridReady`.
#
# Neither ever carries a comparator, so both sort assertions below prove the
# missing comparator doesn't leave the column unsorted: a regression back to
# the old blanking behaviour would make every group cell empty text, which
# does not sort by magnitude at all.
#
# They do NOT, on their own, discriminate a fallback that wrongly returned an
# `StAggValue` instead of a plain number — measured, not assumed: AG-Grid
# 36's own default comparator (`ag-grid-community.js`'s `_defaultComparator`,
# used whenever no column comparator is configured, exactly the case here)
# already unwraps a `toNumber()`-bearing object before comparing, the same
# way `stAggComparator` does. So an `StAggValue` sorts identically to a plain
# number under the *default* comparator too, for a non-null result. The
# `stRatioAggFunc` docstring covers why the fallback returns a plain number
# regardless (a `valueFormatter` written for a raw number, on a column that
# started life as `aggFunc: "sum"`, must keep working when the column is
# switched to `stRatio` purely at runtime) — that reason alone is decisive
# and does not depend on this sorting behaviour.


def test_fallback_cost_group_and_grand_total_sum_rather_than_blank(page: Page):
    """`cost` acquires `aggFunc: "stRatio"` only through
    `FALLBACK_COLUMNS_STATE` (`columns_state_mode="merge"`), applied after
    the grid is created — `registerStRatio`'s `columnDefs` walk never saw it,
    since `columnDefs` declares `aggFunc: "sum"` for this column. Before this
    task, a column that reached the aggregator this way rendered blank; the
    fallback must show the plain `Σcost` instead: campaign A =
    800+100+90+10 = 1000, campaign B = 9+1+8+2 = 20 (the same eight
    `RATIO_ROWS`, and the same grand total `SHARE_SPEC`'s `den_const` anchor
    uses)."""
    rows = read_rows(page, FALLBACK_GRID)
    assert_number(rows["body:0"]["cost"], 1000.0, "campaign A cost")
    assert_number(rows["body:7"]["cost"], 20.0, "campaign B cost")
    assert float(grand_total_row(rows)["cost"]) == pytest.approx(1020.0)


def test_fallback_installs_acquired_at_runtime_sums_rather_than_blanks(page: Page):
    """`installs` acquires `aggFunc: "stRatio"` only through
    `FALLBACK_INITIAL_STATE` (`GridState.aggregation.aggregationModel`),
    applied pre-paint — `registerStRatio`'s `columnDefs` walk never saw it
    either, since `columnDefs` declares `aggFunc: "sum"` for this column too.
    `Σinstalls`: campaign A = 2+8+10+80 = 100, campaign B = 10+90+20+80 =
    200, grand total = 300."""
    rows = read_rows(page, FALLBACK_GRID)
    assert_number(rows["body:0"]["installs"], 100.0, "campaign A installs")
    assert_number(rows["body:7"]["installs"], 200.0, "campaign B installs")
    assert float(grand_total_row(rows)["installs"]) == pytest.approx(300.0)


def click_header(page: Page, grid_index: int, col_id: str, expect_sort: str) -> None:
    """Click a header and wait for AG-Grid to report the new direction.

    Redeclared locally rather than imported from
    `test_grid_ratio_builtin.py` (frozen, and this module already
    independently redeclares `MIXED_DEN_SPEC` for the same reason): waiting
    on `aria-sort` rather than a timeout matters here because several of
    these assertions expect an order that is also the *unsorted* order, so a
    click that silently failed to register would let the test pass without
    sorting anything.
    """
    grid = page.locator(".ag-root-wrapper").nth(grid_index)
    header = grid.locator(f'.ag-header-cell[col-id="{col_id}"]')
    header.click()
    page.wait_for_function(
        """([gridIndex, colId, direction]) => {
             const grid = document.querySelectorAll('.ag-root-wrapper')[gridIndex];
             const cell = grid.querySelector(`.ag-header-cell[col-id="${colId}"]`);
             return cell && cell.getAttribute('aria-sort') === direction;
           }""",
        arg=[grid_index, col_id, expect_sort],
        timeout=10000,
    )


def campaign_order(page: Page, grid_index: int) -> list[str]:
    """Group labels top to bottom, read by row-index. The grand-total row is
    dropped — it stays put regardless of sort.

    Matched by first character rather than equality: this module's
    `COMMON_OPTIONS`, unlike `test_grid_ratio_builtin.py`'s, does not set
    `autoGroupColumnDef.cellRendererParams.suppressCount`, so AG-Grid renders
    each campaign group's row count into the label too (`"A(4)"`, `"B(4)"`)
    rather than the plain `"A"`/`"B"` the frozen suite sees.
    """
    rows = read_rows(page, grid_index)
    ordered = sorted(
        ((key, cells) for key, cells in rows.items() if key.startswith("body:")),
        key=lambda item: int(item[0].split(":")[1]),
    )
    labels = [cells.get("ag-Grid-AutoColumn-campaign", "") for _, cells in ordered]
    return [label[:1] for label in labels if label[:1] in ("A", "B")]


def test_fallback_cost_sorts_numerically_with_no_comparator(page: Page):
    """`cost` (1000 for A, 20 for B) never carries a comparator: it was
    `aggFunc: "sum"` at parse time, and only became `stRatio` through
    `columns_state` (merge mode) — a path `registerStRatio`'s `columnDefs`
    walk cannot see, so this column sorts entirely under AG-Grid's own
    default comparator. Proves the fallback produces genuinely-sortable
    numeric group values rather than the old blank cells (which do not order
    by magnitude at all); see the "Fallback" section note above for why this
    does not additionally discriminate a plain `number` from an `StAggValue`
    on AG-Grid 36 specifically."""
    click_header(page, FALLBACK_GRID, "cost", "ascending")
    assert campaign_order(page, FALLBACK_GRID) == ["B", "A"]

    click_header(page, FALLBACK_GRID, "cost", "descending")
    assert campaign_order(page, FALLBACK_GRID) == ["A", "B"]


def test_fallback_installs_sorts_numerically_with_no_comparator(page: Page):
    """Same claim as `test_fallback_cost_sorts_numerically_with_no_comparator`,
    through the other runtime-mutation route: `installs` (100 for A, 200 for
    B) was `aggFunc: "sum"` at parse time and only became `stRatio` through
    the raw `initial_state` prop, also invisible to `registerStRatio`'s
    `columnDefs` walk, so it too sorts entirely under AG-Grid's default
    comparator with no comparator of its own."""
    click_header(page, FALLBACK_GRID, "installs", "ascending")
    assert campaign_order(page, FALLBACK_GRID) == ["A", "B"]

    click_header(page, FALLBACK_GRID, "installs", "descending")
    assert campaign_order(page, FALLBACK_GRID) == ["B", "A"]
