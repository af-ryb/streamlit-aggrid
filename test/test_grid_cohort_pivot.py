"""The consumer's cohort grid shape, checked for stacked cells, stale pivot
columns and wrong numbers.

Written against a defect report on ``hitapps_analytics``' cohort dashboard:
under this fork's AG-Grid 36 pin, some cells drew two values on top of one
another and a few numbers were wrong; it never reproduced on production
(AG-Grid 35.2.1), healed itself when a filter was applied or the pivot column
was dragged out and back, and left nothing in the browser console — which v36
makes easy, since it drops ValidationModule from the ``All*Module`` bundles and
so no longer reports invalid options at all.

Cohort is the only grid in that service that puts a dimension in *Column
Labels* by default, and nothing here covered that: the existing pivot apps
pivot a static frame, and none of them reshapes the pivot key set at runtime.
``grid_cohort_pivot.py`` fills the gap — the configuration transcribed whole,
driven through the four distinct ways the consumer re-feeds its grid.

What each check is for:

* **stacked cells** — the reported symptom, and invisible to `read_rows`, which
  keys on col-id and so silently keeps one of two overlapping cells.
* **painted columns** — pivot result columns left over from the previous frame
  would put two cells in one slot and paint a value from a column that no
  longer belongs there.
* **every number** — the second symptom, and the only check that would catch a
  correct-looking grid holding wrong values.

Two separate defects came out of this, and they belong to different owners:

* `test_adding_a_value_column_while_scrolled_does_not_stack_cells` — the
  reported overlap. It arrived with the pin (50 stacked pairs on the AG-Grid 36
  build, 0 on 35.2.1) and is fixed in this fork: the config-update effect now
  repaints once the column layout has settled rather than while it is still
  moving.
* `test_hide_hook_does_not_re_run_after_a_refresh` — the consumer's
  `onStateUpdated` hook is one-shot per pivot shape. Reproduces identically on
  both pins, so this one is the configuration's, not the fork's, and is
  documented rather than fixed here.
"""

from dataclasses import dataclass, field, replace
from pathlib import Path

import pytest
from playwright.sync_api import Page

import cohort_pivot_fixture as fx
from e2e_utils import StreamlitRunner
from grid_dom import read_cell_boxes, stacked_cells

ROOT_DIRECTORY = Path(__file__).parent.parent.absolute()
APP_FILE = ROOT_DIRECTORY / "test" / "grid_cohort_pivot.py"

GRID = 0
PIVOT_PREFIX = f"pivot_{fx.PIVOT_FIELD}_"
DATE_LIMIT = len(fx.INSTALL_DATES)

VIEWPORT = ".ag-grid-viewport, .ag-body-viewport"
HSCROLL = ".ag-body-horizontal-scroll-viewport"
VSCROLL = ".ag-body-vertical-scroll-viewport"



@dataclass
class Controls:
    """The app's widget state, mirrored so expectations can be derived without
    reading them back off the page."""

    shape: fx.Shape = field(default_factory=fx.Shape)
    hide_hook: bool = True
    #: Whether the consumer's `onStateUpdated` hook has run against the
    #: *current* pivot columns. A rowData reshape regenerates them all-visible
    #: and does not by itself update grid state, so the hook stays un-run until
    #: something else does — see
    #: `test_hide_hook_does_not_re_run_after_a_refresh`.
    hook_applied: bool = True

    def visible_pivot_columns(self) -> set[str]:
        """Every pivot-result colId the grid may paint.

        ``installs`` survives only under pivot key ``00`` — the consumer's hook
        hides it everywhere else, which is the whole reason that hook exists —
        and only while that hook has actually run.
        """
        covered = self.hide_hook and self.hook_applied
        allowed = set()
        for key in fx.pivot_keys(self.shape):
            for metric in self.shape.metrics:
                allowed.add(fx.pivot_col_id(key, metric))
            if key == "00" or not covered:
                allowed.add(fx.pivot_col_id(key, "installs"))
        return allowed


def parse_cell(text: str) -> tuple[float, float]:
    """The number behind a rendered cell, and how far it may honestly differ.

    The two metrics deliberately use the consumer's two different renderers, so
    a cell reads ``"41.47%"``, ``"80.58¢"``, ``"$1.03"`` or a bare number for
    ``installs``. Parsing it back beats comparing formatted strings: it keeps
    the expectations in the fixture's own units and sidesteps JavaScript's
    ``toFixed`` disagreeing with Python's rounding on a tie.

    The tolerance has to come back with the value because the currency renderer
    switches units by magnitude — ``0.9058`` prints as ``"90.58¢"`` (two
    decimals of a hundredth) and ``1.109`` as ``"$1.11"`` (two decimals of a
    whole), so the same column carries two different display precisions. A
    single fixed tolerance is wrong for one of them whichever value is picked.
    """
    if text.endswith("%") or text.endswith("¢"):
        return float(text[:-1]) / 100, 5.1e-5
    if text.startswith("$"):
        return float(text[1:].replace(",", "")), 5.1e-3
    return float(text), 5.1e-3


@pytest.fixture(autouse=True, scope="module")
def streamlit_app():
    with StreamlitRunner(APP_FILE) as runner:
        yield runner


@pytest.fixture(autouse=True, scope="function")
def go_to_app(page: Page, streamlit_app: StreamlitRunner):
    page.set_viewport_size({"width": 1400, "height": 900})
    page.goto(streamlit_app.server_url)
    page.wait_for_selector(".ag-root-wrapper", timeout=60000)
    page.wait_for_selector(".ag-row", timeout=60000)
    settle(page)


def settle(page: Page) -> None:
    """Wait out the Streamlit rerun and the grid re-render it triggers."""
    page.wait_for_timeout(400)
    try:
        page.wait_for_selector(
            '[data-testid="stStatusWidget"]', state="detached", timeout=15000
        )
    except Exception:
        # The status widget can appear and vanish between polls; the fixed
        # wait below still covers the re-render.
        pass
    page.wait_for_timeout(900)


def _radio(page: Page, label: str, value: int) -> None:
    """Click one option of a named radio group. Scoped by the group's label
    because `max_day` and `n_dates` offer the same numbers."""
    group = page.get_by_test_id("stRadio").filter(has_text=label)
    group.get_by_text(str(value), exact=True).click()


def set_max_day(page: Page, controls: Controls, value: int) -> Controls:
    """Reshape the data only — the pivot key set changes, columnDefs do not.

    Clears `hook_applied`: this is one of the paths that regenerates the pivot
    result columns without producing a grid-state update.
    """
    _radio(page, "max_day", value)
    settle(page)
    return replace(
        controls, shape=replace(controls.shape, max_day=value), hook_applied=False
    )


def set_date_range(page: Page, controls: Controls, value: int) -> Controls:
    """Widen or narrow the install-date range — more rows *and*, because older
    cohorts are more mature, more pivot keys. The refresh the report names
    first."""
    _radio(page, "n_dates", value)
    settle(page)
    return replace(
        controls, shape=replace(controls.shape, n_dates=value), hook_applied=False
    )


def toggle(page: Page, controls: Controls, label: str) -> Controls:
    """Flip a checkbox. Unlike a reshape these paths do update grid state — the
    component applies column state and redraws rows — so the hook re-runs and
    `hook_applied` stays set."""
    page.get_by_text(label, exact=True).click()
    settle(page)
    if label.startswith("metric_"):
        metric = label[len("metric_") :]
        current = controls.shape.metrics
        metrics = (
            tuple(m for m in current if m != metric)
            if metric in current
            else tuple(m for m in fx.METRICS if m in current or m == metric)
        )
        return replace(controls, shape=replace(controls.shape, metrics=metrics))
    if label == "hide_hook":
        return replace(controls, hide_hook=not controls.hide_hook)
    return controls


def nudge_state(page: Page, controls: Controls) -> Controls:
    """Scroll a little, which is enough of a grid-state update to re-run the
    consumer's hook. The smallest stand-in for the two gestures the report says
    heal the grid (applying a filter, re-dragging the pivot column)."""
    page.wait_for_selector(VIEWPORT, timeout=30000)
    page.evaluate(
        """([hSel, vSel]) => {
             const hs = document.querySelector(hSel);
             const vs = document.querySelector(vSel);
             if (hs) hs.scrollLeft += 40;
             if (vs) vs.scrollTop += 1;
           }""",
        [HSCROLL, VSCROLL],
    )
    page.wait_for_timeout(700)
    return replace(controls, hook_applied=True)


def scroll_extent(page: Page) -> tuple[float, float]:
    page.wait_for_selector(VIEWPORT, timeout=30000)
    return page.evaluate(
        """([vpSel, hSel, vSel]) => {
             const vp = document.querySelector(vpSel);
             const hs = document.querySelector(hSel) || vp;
             const vs = document.querySelector(vSel) || vp;
             return [hs.scrollWidth - hs.clientWidth, vs.scrollHeight - vs.clientHeight];
           }""",
        [VIEWPORT, HSCROLL, VSCROLL],
    )


def scroll_to(page: Page, left: float, top: float) -> None:
    page.wait_for_selector(VIEWPORT, timeout=30000)
    page.evaluate(
        """([left, top, vpSel, hSel, vSel]) => {
             const vp = document.querySelector(vpSel);
             const hs = document.querySelector(hSel) || vp;
             const vs = document.querySelector(vSel) || vp;
             hs.scrollLeft = left;
             vs.scrollTop = top;
           }""",
        [left, top, VIEWPORT, HSCROLL, VSCROLL],
    )
    page.wait_for_timeout(450)


def rendered_rows(page: Page) -> dict[int, dict]:
    """Cells keyed by row-index, merging a row's sticky copy with its body one
    and keeping the text-bearing fragment of each cell."""
    rows: dict[int, dict] = {}
    for box in read_cell_boxes(page, GRID):
        row = rows.setdefault(
            int(box["rowIndex"]), {"rowId": box["rowId"], "cells": {}}
        )
        row["cells"].setdefault(box["colId"], box["text"])
        if box["text"]:
            row["cells"][box["colId"]] = box["text"]
    return rows


def installs_keys_in_view(page: Page) -> set[str]:
    """Pivot keys whose ``installs`` column is painted right now, without
    scrolling — scrolling would itself re-run the hook and destroy the state
    under examination."""
    return {
        box["colId"][len(PIVOT_PREFIX) :].partition("_")[0]
        for box in read_cell_boxes(page, GRID)
        if box["colId"].startswith(PIVOT_PREFIX)
        and box["colId"].endswith("_installs")
    }


def assert_consistent(page: Page, controls: Controls, where: str) -> None:
    """No cell stacked on another, no column outside the current pivot shape,
    and every rendered number equal to the fixture's arithmetic."""
    boxes = read_cell_boxes(page, GRID)

    stacked = stacked_cells(boxes)
    assert not stacked, (
        f"{where}: {len(stacked)} pairs of cells share screen space, "
        f"first {stacked[0][0]['colId']} over {stacked[0][1]['colId']}"
    )

    allowed = controls.visible_pivot_columns()
    for row_index, row in sorted(rendered_rows(page).items()):
        selector = fx.group_path(row["rowId"])
        assert selector is not None, (
            f"{where}: row {row_index} has an unreadable row-id {row['rowId']!r}"
        )
        for col_id, text in row["cells"].items():
            if not col_id.startswith(PIVOT_PREFIX):
                continue
            assert col_id in allowed, (
                f"{where}: row {row_index} paints {col_id!r}={text!r}, which is "
                f"not part of the current pivot shape"
            )
            cohort_day, _, col = col_id[len(PIVOT_PREFIX) :].partition("_")
            reference = fx.expected(
                col, controls.shape, cohort_day=cohort_day, **selector
            )
            at = f"{where}: row {row_index} ({selector or 'grand total'}) {col_id}"
            if reference is None:
                assert text == "", f"{at} expected an empty cell, got {text!r}"
            else:
                assert text != "", f"{at} expected {reference:.6f}, got an empty cell"
                value, tolerance = parse_cell(text)
                assert abs(value - reference) <= tolerance, (
                    f"{at} expected {reference:.6f}, got {text!r}"
                )


def assert_not_stacked(page: Page, where: str) -> None:
    """Only the overlap check, usable in states where the expected column set
    is not yet known — in particular straight after a refresh, before anything
    has updated grid state. That is where the report says the cells double up,
    so it must be examined before the nudge repairs it."""
    stacked = stacked_cells(read_cell_boxes(page, GRID))
    assert not stacked, (
        f"{where}: {len(stacked)} pairs of cells share screen space, first "
        f"{stacked[0][0]['colId']}={stacked[0][0]['text']!r} over "
        f"{stacked[0][1]['colId']}={stacked[0][1]['text']!r}"
    )


def sweep(page: Page, controls: Controls, where: str) -> Controls:
    """Check the settled grid at three scroll positions.

    Scrolling is not incidental: with column virtualisation on — the state the
    defect was reported in — only the columns in view exist in the DOM, so the
    right-hand pivot keys are never examined at rest. The opening nudge is what
    makes "settled" true, since a scroll re-runs the consumer's hook — so the
    un-nudged state is checked for overlap first, before it is repaired.
    """
    assert_not_stacked(page, f"{where}/pre-nudge")
    controls = nudge_state(page, controls)
    max_left, max_top = scroll_extent(page)
    for label, (left, top) in {
        "left": (0, 0),
        "middle": (max_left / 2, max_top),
        "right": (max_left, 0),
    }.items():
        scroll_to(page, left, top)
        assert_consistent(page, controls, f"{where}/{label}")
    return controls


def painted_pivot_columns(page: Page, steps: int = 8) -> set[str]:
    """Every pivot-result column the grid paints anywhere across its width.

    Collected by scrolling rather than by suppressing virtualisation:
    ``suppressColumnVirtualisation`` is read once when the grid is constructed,
    so toggling it on a live grid changes nothing and a test that believed
    otherwise would only ever examine the leftmost screenful.
    """
    max_left, _ = scroll_extent(page)
    seen: set[str] = set()
    for step in range(steps + 1):
        scroll_to(page, max_left * step / steps, 0)
        for row in rendered_rows(page).values():
            seen |= {c for c in row["cells"] if c.startswith(PIVOT_PREFIX)}
    return seen


def test_full_triangle_paints_exactly_the_expected_columns(page: Page):
    """Compared for equality, not containment — the one check that catches both
    a column the current shape no longer calls for and one it calls for but
    never generated."""
    controls = Controls()
    assert painted_pivot_columns(page) == controls.visible_pivot_columns()
    assert_consistent(page, controls, "full-triangle")


def test_narrowed_shape_drops_the_columns_it_should(page: Page):
    """The same equality after a reshape: pivot keys the data no longer has
    must be gone from the painted set, not merely scrolled out of reach."""
    controls = set_max_day(page, Controls(), 4)
    controls = nudge_state(page, controls)
    assert painted_pivot_columns(page) == controls.visible_pivot_columns()
    assert_consistent(page, controls, "narrowed")


def test_data_refresh_reshapes_the_pivot_cleanly(page: Page):
    """rowData changes, columnDefs do not — an ordinary data refresh, and the
    path the report follows most closely. Cycled rather than stepped once,
    because the reported defect was intermittent."""
    controls = Controls()
    controls = sweep(page, controls, "start")

    for max_day in (2, fx.MAX_DAY_LIMIT, 4, fx.MAX_DAY_LIMIT):
        controls = set_max_day(page, controls, max_day)
        controls = sweep(page, controls, f"refresh/day{max_day}")


def test_date_range_widening_reshapes_the_pivot_cleanly(page: Page):
    """The refresh the report names first. Widening the install-date range adds
    rows and, because the cohorts it reaches back to are older and therefore
    more mature, pivot keys as well — both halves of a reshape in one step."""
    controls = Controls()
    controls = sweep(page, controls, "range/start")

    for n_dates in (2, 6, DATE_LIMIT, 4, DATE_LIMIT):
        controls = set_date_range(page, controls, n_dates)
        controls = sweep(page, controls, f"range/{n_dates}")


def test_widening_the_range_and_adding_a_metric_together(page: Page):
    """The pair the report names as the trigger, in one sequence and in both
    orders. Adding a metric changes the rowData columns and the columnDefs in
    the same rerun — a combination neither knob reaches on its own."""
    controls = Controls()

    # `sweep` leaves the grid scrolled right, so every metric toggle below adds
    # or drops a value column from a scrolled grid — the arrangement that used
    # to stack cells. Left that way on purpose: it costs nothing here and puts
    # the settled-redraw under load from a second angle.
    controls = toggle(page, controls, "metric_arpu")
    controls = set_date_range(page, controls, 4)
    controls = sweep(page, controls, "combo/narrow-one-metric")

    controls = set_date_range(page, controls, DATE_LIMIT)
    controls = toggle(page, controls, "metric_arpu")
    controls = sweep(page, controls, "combo/wide-both-metrics")

    controls = toggle(page, controls, "metric_arpu")
    controls = sweep(page, controls, "combo/wide-one-metric")

    controls = set_date_range(page, controls, 2)
    controls = toggle(page, controls, "metric_arpu")
    controls = sweep(page, controls, "combo/narrow-both-metrics")


def test_column_and_group_changes_keep_the_pivot_consistent(page: Page):
    """The other two re-feed paths: new columnDefs (a metric comes and goes,
    driving `updateGridOptions`) and a row-group change (driving
    `setRowGroupColumns` and the multipleColumns auto-column reorder)."""
    controls = Controls()

    controls = toggle(page, controls, "metric_arpu")
    controls = sweep(page, controls, "metrics/one")

    controls = set_max_day(page, controls, 4)
    controls = sweep(page, controls, "metrics/one-day4")

    controls = toggle(page, controls, "metric_arpu")
    controls = sweep(page, controls, "metrics/both-day4")

    # Row grouping: the breakdown dimension leaves and comes back while the
    # pivot stays put. Values are unaffected — the grand total and the
    # install_date rows fold the same leaves either way — so the fixture
    # expectations need no branch here.
    controls = toggle(page, controls, "breakdown")
    controls = sweep(page, controls, "group/one-dimension")

    controls = toggle(page, controls, "breakdown")
    controls = sweep(page, controls, "group/two-dimensions")


def test_saved_column_state_survives_a_reshape(page: Page):
    """The consumer never calls AgGrid directly: `render_managed_grid`
    re-applies a saved column state in replace mode on every rerun. A snapshot
    captured against one pivot shape and re-applied against another is the
    sequence the stale-pivot-column hypothesis needs, so it gets its own path.

    The sort is what makes a snapshot exist at all — programmatic
    (source="api") column events are filtered out of the collect path, so the
    hide hook's own `setColumnsVisible` never produces one.
    """
    controls = Controls()

    page.locator(
        f'.ag-header-cell[col-id="{fx.pivot_col_id("00", "retention")}"]'
    ).first.click()
    settle(page)

    page.get_by_role("button", name="save_view", exact=True).click()
    settle(page)
    assert "restore_state: none" not in page.content(), (
        "no column state was captured, so this test would prove nothing"
    )

    for max_day in (2, fx.MAX_DAY_LIMIT, 6):
        controls = set_max_day(page, controls, max_day)
        controls = sweep(page, controls, f"restore/day{max_day}")


def test_adding_a_value_column_while_scrolled_does_not_stack_cells(page: Page):
    """The reported defect, reduced to its trigger.

    Remove a metric, scroll the grid right, put the metric back. Before the fix
    the grid painted a value cell of one pivot key on top of a value cell of the
    next — a `¢` over a `%` in this configuration, which is how the owner
    spotted it. Both colIds were current: not a leftover column, but two live
    columns computing the same left offset, because the redraw ran while the
    column layout was still in flight.

    Order is the whole point and is what makes this a separate test: the same
    toggle from the left edge was always clean, as were the data-only reshapes
    (`n_dates`, `max_day`) and a row-group change, scrolled or not. Measured at
    50 stacked pairs on this fork's AG-Grid 36 build against 0 on the 35.2.1
    build production runs, with the same app, viewport and gestures — so it
    arrived with the pin.

    Guards the settled-redraw in `AgGridComponent`'s config-update effect. That
    fix cannot be loosened into a delay: a redraw deferred from the effect by a
    microtask, a frame, or a timeout of any length was measured to still land
    before the columns settle.
    """
    controls = Controls()
    controls = toggle(page, controls, "metric_arpu")

    max_left, _ = scroll_extent(page)
    scroll_to(page, max_left, 0)

    controls = toggle(page, controls, "metric_arpu")
    assert_not_stacked(page, "value-column-added-while-scrolled")
    assert_consistent(page, controls, "value-column-added-while-scrolled")


def test_hide_hook_does_not_re_run_after_a_refresh(page: Page):
    """A defect in the consumer's configuration, pinned here because this is
    where it is reproducible.

    `js_hide_columns` hangs off `onStateUpdated` and hides the `installs`
    column under every cohort day but the zeroth. A data refresh that changes
    the pivot key set regenerates the pivot result columns all-visible but does
    not itself update grid state, so the hook does not re-run and the hidden
    columns come back — inserted inside each cohort-day group, shifting every
    column to its right. Any later state update (this test scrolls; the report
    describes a filter, or dragging the pivot column out and back) re-runs the
    hook and the grid heals itself, which is exactly the intermittency the
    report describes.

    Not caused by the AG-Grid 36 pin: the same sequence behaves identically on
    the 35.2.1 build production runs.

    The pre-nudge reads deliberately do not scroll — scrolling is itself the
    state update under examination, so a scan across the grid's full width
    would repair the state it is trying to observe.
    """
    controls = Controls()
    assert installs_keys_in_view(page) == {"00"}, (
        "the hook should have run at first paint"
    )

    controls = set_max_day(page, controls, 4)
    assert "01" in installs_keys_in_view(page), (
        "expected the hidden installs columns back after a reshape"
    )
    # The re-shown columns are wrong to be there but not wrong in themselves:
    # nothing is stacked and the numbers still hold.
    assert_consistent(page, controls, "hook-not-re-run")

    controls = nudge_state(page, controls)
    assert installs_keys_in_view(page) == {"00"}, (
        "a grid-state update should have re-run the hook"
    )
