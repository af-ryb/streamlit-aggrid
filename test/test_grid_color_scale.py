"""The built-in colour scales, painted by a real grid.

Every expected colour comes from `color_scale_fixture.expected_rgba`, never
from a number typed here — the convention the ratio suites established, and
what makes a transcription error in a ramp fail rather than propagate.

Rows are addressed by `row-index`, never by document order: AG-Grid positions
rows absolutely, and a probe written against DOM order produced a false result
in this repo once already.
"""

from pathlib import Path

import pytest
from playwright.sync_api import Page

from color_scale_fixture import (
    NORMAL_FONT_WEIGHT,
    RANK_FONT_WEIGHT,
    RANK_RGBA,
    column_values,
    expected_rank,
    expected_rgba,
    half_up,
    is_scheme_color,
    region_totals,
    region_values,
)
from e2e_utils import StreamlitRunner
from grid_dom import cell_backgrounds, read_rows

ROOT_DIRECTORY = Path(__file__).parent.parent.absolute()
APP_FILE = ROOT_DIRECTORY / "test" / "grid_color_scale.py"

FLAT_GRID = 0
GROUPED_GRID = 1
PIVOT_GRID = 2
BUILDER_GRID = 3
DEFAULT_CELLSTYLE_GRID = 4
PHASE2_FLAT_GRID = 5
SCOPE_GRID = 6

#: The flat grid's body rows, in fixture order: DE, FR, IT, CA, NY, TX.
FLAT_ROWS = tuple(f"body:{index}" for index in range(6))

METRIC_A = column_values("metric_a")
RATIO = column_values("ratio")
ANCHOR_1 = dict(mode="anchor", anchor=1.0, span=1.0)


def _alpha_channel(alpha: float) -> int:
    """The 8-bit channel a browser actually stores for a solid `rgba()`
    colour's alpha. Rounded with the fixture's own `half_up` — the project's
    convention that the fixture owns the arithmetic, matching `schemes.ts`'s
    `halfUp` (JavaScript's `Math.round` semantics, not Python's
    half-to-even `round`)."""
    return half_up(alpha * 255)


def assert_painted(
    actual: tuple[int, int, int, float] | None,
    expected: tuple[int, int, int, float] | None,
    where: str,
) -> None:
    """Compare an `(r, g, b, alpha)` pair the way a browser can actually
    represent it.

    Chromium stores a solid `rgba()` colour's alpha as an 8-bit fraction
    (`n / 255`) and serialises it back as the *shortest* decimal string that
    round-trips to that same fraction. `color_scale_fixture.expected_rgba`
    carries alpha at 3-decimal precision (the arithmetic's own rounding, not
    the browser's), so e.g. its `0.452` comes back from `getComputedStyle` as
    `"0.45"` — `114.75` rounds to the 8-bit value `115`, and `115 / 255`
    rounds *down* to `0.451` at 3 decimals, so `"0.45"` (2 decimals) is the
    shorter string that still round-trips to `115`. Comparing the raw floats
    would fail on cells that are painted exactly correctly, so both sides are
    snapped to the same 1/255 grid before comparing. RGB, which the browser
    never quantises, is still compared exactly.

    Requires a non-`None` expected colour; use `assert_unpainted` to assert
    the opposite.
    """
    assert actual is not None and expected is not None, where
    assert actual[:3] == expected[:3], where
    assert _alpha_channel(actual[3]) == _alpha_channel(expected[3]), where


def assert_unpainted(
    actual: tuple[int, int, int, float] | None, scheme: str, where: str
) -> None:
    """Assert a cell carries no colour this scheme could have painted.

    Checked against the scheme's palette rather than against a transparent
    background, so the assertion does not depend on what the active theme
    paints underneath.
    """
    assert not is_scheme_color(actual, scheme), f"{where}: expected unpainted, got {actual!r}"


def font_weight(page: Page, grid_index: int, row_index: int, col_id: str) -> str | None:
    """The computed `font-weight` of one cell — `rank` is the one built-in
    style with a second CSS property."""
    return page.evaluate(
        """([gridIndex, rowIndex, colId]) => {
             const grid = document.querySelectorAll('.ag-root-wrapper')[gridIndex];
             const cell = grid.querySelector(
               `.ag-row[row-index="${rowIndex}"] .ag-cell[col-id="${colId}"]`);
             return cell ? getComputedStyle(cell).fontWeight : null;
           }""",
        [grid_index, row_index, col_id],
    )


@pytest.fixture(autouse=True, scope="module")
def streamlit_app():
    with StreamlitRunner(APP_FILE) as runner:
        yield runner


@pytest.fixture(autouse=True, scope="function")
def go_to_app(page: Page, streamlit_app: StreamlitRunner):
    page.goto(streamlit_app.server_url)
    page.get_by_role("img", name="Running...").is_hidden()
    page.wait_for_selector(".ag-root-wrapper", timeout=60000)
    page.wait_for_function(
        "() => document.querySelectorAll('.ag-root-wrapper').length >= 7",
        timeout=60000,
    )
    # The grouped grid (index 1) is the last of the three to settle: 2 region
    # group rows + 6 leaf rows + the `grandTotalRow` — which, unscrolled, AG-Grid
    # renders as an ordinary last body row rather than in `.ag-floating-bottom`
    # — is 9 `.ag-row` elements. Scoped to grid 1 specifically: a page-wide
    # selector such as `[row-index="7"]` would also match the pivot grid's own
    # row-index 7 and would not prove grid 1 in particular had finished.
    page.wait_for_function(
        """() => {
             const grid = document.querySelectorAll('.ag-root-wrapper')[1];
             return !!grid && grid.querySelectorAll('.ag-row').length >= 9;
           }""",
        timeout=60000,
    )
    # Grid 6 has the same nine rows — two groups, six leaves, the grand total —
    # and is now the last grid on the page to finish.
    page.wait_for_function(
        """() => {
             const grid = document.querySelectorAll('.ag-root-wrapper')[6];
             return !!grid && grid.querySelectorAll('.ag-row').length >= 9;
           }""",
        timeout=60000,
    )


def test_positive_minmax_paints_the_flat_ramp(page: Page):
    """The end-to-end smoke: a declaration in `context` alone, with no JsCode,
    paints the column the fixture says it should."""
    painted = cell_backgrounds(page, FLAT_GRID)
    for key, value in zip(FLAT_ROWS, METRIC_A):
        assert_painted(
            painted[key]["pos_minmax"], expected_rgba("positive", METRIC_A, value), key
        )


METRIC_B = column_values("metric_b")


@pytest.mark.parametrize(
    "col_id,scheme,mode",
    [
        ("neu_zscore", "neutral", None),
        ("div_zscore", "diverging", None),
        ("neu_minmax", "neutral", "minmax"),
        ("pos_zscore", "positive", "zscore"),
        ("div_minmax", "diverging", "minmax"),
    ],
)
def test_each_scheme_and_mode_matches_the_reference(page: Page, col_id, scheme, mode):
    painted = cell_backgrounds(page, FLAT_GRID)
    for key, value in zip(FLAT_ROWS, METRIC_A):
        expected = expected_rgba(scheme, METRIC_A, value, mode=mode)
        actual = painted[key][col_id]
        if expected is None:
            assert_unpainted(actual, scheme, f"{key}: {col_id}")
        else:
            assert_painted(actual, expected, f"{key}: {col_id}")


def test_the_zscore_dead_zone_leaves_the_middle_rows_alone(page: Page):
    # 300 and 400 sit within 0.5 sd of the mean 350. Pinned explicitly rather
    # than left to the parametrised loop: it is the one gate whose *absence*
    # would still produce plausible-looking colours.
    painted = cell_backgrounds(page, FLAT_GRID)
    assert_unpainted(painted["body:2"]["neu_zscore"], "neutral", "body:2 (300)")
    assert_unpainted(painted["body:3"]["neu_zscore"], "neutral", "body:3 (400)")
    assert is_scheme_color(painted["body:1"]["neu_zscore"], "neutral")
    assert is_scheme_color(painted["body:4"]["neu_zscore"], "neutral")


def test_a_uniform_column_is_never_painted(page: Page):
    painted = cell_backgrounds(page, FLAT_GRID)
    for key in FLAT_ROWS:
        assert_unpainted(painted[key]["uniform"], "positive", key)


def test_skip_non_positive_excludes_the_zero_and_the_negative(page: Page):
    painted = cell_backgrounds(page, FLAT_GRID)
    # DE is -5 and FR is 0: unpainted, and out of the population, so IT (10) is
    # the column minimum rather than a mid-ramp value.
    assert_unpainted(painted["body:0"]["skip_on"], "positive", "body:0 (-5)")
    assert_unpainted(painted["body:1"]["skip_on"], "positive", "body:1 (0)")
    for key, value in zip(FLAT_ROWS, METRIC_B):
        expected = expected_rgba("positive", METRIC_B, value, skip_non_positive=True)
        if expected is not None:
            assert_painted(painted[key]["skip_on"], expected, key)


def test_without_the_skip_the_negative_is_painted(page: Page):
    painted = cell_backgrounds(page, FLAT_GRID)
    for key, value in zip(FLAT_ROWS, METRIC_B):
        expected = expected_rgba("neutral", METRIC_B, value, skip_non_positive=False)
        actual = painted[key]["skip_off"]
        if expected is None:
            assert_unpainted(actual, "neutral", key)
        else:
            assert_painted(actual, expected, key)


def test_a_caller_supplied_cell_style_wins(page: Page):
    # Same declaration as `pos_minmax`, but the column carries its own
    # cellStyle: the built-in must not be attached at all.
    painted = cell_backgrounds(page, FLAT_GRID)
    for key in FLAT_ROWS:
        assert_painted(painted[key]["own_style"], (1, 2, 3, 1.0), key)


def test_group_rows_are_scaled_against_their_own_level(page: Page):
    """The defect this rule exists to fix.

    On the grouped grid the two region totals are 600 and 1500, both outside
    the leaf range 100..600. Pooled into one population — which is what the
    styler this replaces does — the minimum would be 100 and the maximum 1500,
    EU would land at t = 0.357, and every leaf would be crowded into the pale
    end. Level-scoped, EU is its level's minimum.
    """
    painted = cell_backgrounds(page, GROUPED_GRID)
    totals = list(region_totals().values())

    # body:0 EU group, body:4 US group; leaves sit between and after them.
    assert_painted(painted["body:0"]["grouped"], expected_rgba("positive", totals, 600.0), "EU group")
    assert_painted(painted["body:4"]["grouped"], expected_rgba("positive", totals, 1500.0), "US group")

    # And the leaves keep their own 100..600 scale.
    assert_painted(painted["body:1"]["grouped"], expected_rgba("positive", METRIC_A, 100.0), "DE leaf")
    assert_painted(painted["body:3"]["grouped"], expected_rgba("positive", METRIC_A, 300.0), "IT leaf")

    # The pooled-population answer, spelled out so the assertion above cannot
    # pass by coincidence.
    pooled = METRIC_A + totals
    assert expected_rgba("positive", pooled, 600.0) != expected_rgba(
        "positive", totals, 600.0
    )


def test_the_grand_total_row_is_not_painted(page: Page):
    # Located by its label rather than by a row index: AG-Grid renders
    # `grandTotalRow: "bottom"` either into the pinned-bottom container or as
    # the last body row depending on whether the grid is scrolled, which is why
    # `grid_dom.grand_total_row` exists at all.
    # `grid_color_scale.py`'s grouped grid does not set `groupDisplayType:
    # "multipleColumns"` (unlike the ratio suites), so the auto-group column
    # keeps its unsuffixed col-id `ag-Grid-AutoColumn` rather than
    # `ag-Grid-AutoColumn-region` — confirmed against `read_rows`.
    rows = read_rows(page, GROUPED_GRID)
    key = next(
        key
        for key, cells in rows.items()
        if cells.get("ag-Grid-AutoColumn") == "Total"
    )
    painted = cell_backgrounds(page, GROUPED_GRID)
    assert_unpainted(painted[key].get("grouped"), "positive", "grand total")


def test_pivot_result_columns_are_scaled_column_by_column(page: Page):
    """Each pivot result column carries its own population.

    The EU column holds 100/200/300 and the US column 400/500/600, so IT is the
    top of the EU column. Scaled across both columns instead, IT would sit at
    t = 0.4 — a visibly different colour, which is what makes this assertion
    discriminating.
    """
    painted = cell_backgrounds(page, PIVOT_GRID)
    eu = [100.0, 200.0, 300.0]
    us = [400.0, 500.0, 600.0]

    by_country = group_row_keys(page, PIVOT_GRID)
    eu_col, us_col = pivot_column_ids(page, PIVOT_GRID)

    assert_painted(painted[by_country["DE"]][eu_col], expected_rgba("positive", eu, 100.0), "DE/EU")
    assert_painted(painted[by_country["IT"]][eu_col], expected_rgba("positive", eu, 300.0), "IT/EU")
    assert_painted(painted[by_country["CA"]][us_col], expected_rgba("positive", us, 400.0), "CA/US")
    assert_painted(painted[by_country["TX"]][us_col], expected_rgba("positive", us, 600.0), "TX/US")

    # A country belongs to one region, so its cell in the other region's column
    # is empty — unpainted, and absent from that column's population, which the
    # three-value scales asserted above already depend on.
    assert_unpainted(painted[by_country["DE"]].get(us_col), "positive", "DE/US")
    assert_unpainted(painted[by_country["TX"]].get(eu_col), "positive", "TX/EU")

    pooled = eu + us
    assert expected_rgba("positive", pooled, 300.0) != expected_rgba("positive", eu, 300.0)


def group_row_keys(page: Page, grid_index: int) -> dict[str, str]:
    """Group label -> ``"<section>:<row-index>"``.

    Read rather than assumed: AG-Grid orders groups by first encounter in the
    data, not alphabetically, and hard-coding either order would make this
    suite fail for a reason that has nothing to do with colour.
    """
    # Same unsuffixed col-id as the grouped grid's auto column — this app
    # never sets `groupDisplayType: "multipleColumns"`.
    keys = {}
    for key, cells in read_rows(page, grid_index).items():
        label = cells.get("ag-Grid-AutoColumn", "")
        # `"DE"` with `suppressCount` off renders as `"DE(1)"`.
        name = label.split("(")[0].strip()
        if name and name != "Total":
            keys[name] = key
    return keys


def pivot_column_ids(page: Page, grid_index: int) -> tuple[str, str]:
    """The EU and US pivot result column ids, read from the rendered headers.

    AG-Grid derives a pivot result colId from the pivot key and the value
    column, and the exact spelling is not part of its public contract — so it
    is read rather than assumed.
    """
    ids = page.evaluate(
        """(gridIndex) => {
             const grid = document.querySelectorAll('.ag-root-wrapper')[gridIndex];
             return [...grid.querySelectorAll('.ag-header-cell[col-id]')]
               .map((cell) => cell.getAttribute('col-id'));
           }""",
        grid_index,
    )
    eu = [col for col in ids if "EU" in col]
    us = [col for col in ids if "US" in col]
    assert len(eu) == 1 and len(us) == 1, f"unexpected pivot columns: {ids}"
    return eu[0], us[0]


def test_filtering_rescales_the_column(page: Page):
    """The reason the population is read after filter and sort, and the reason
    the cached statistics are invalidated on `modelUpdated`."""
    before = cell_backgrounds(page, FLAT_GRID)
    assert_painted(before["body:0"]["pos_minmax"], expected_rgba("positive", METRIC_A, 100.0), "DE before")

    it_background_before = page.evaluate(
        """(gridIndex) => {
             const grid = document.querySelectorAll('.ag-root-wrapper')[gridIndex];
             const cell = grid.querySelector('.ag-row[row-index="2"] .ag-cell[col-id="pos_minmax"]');
             return getComputedStyle(cell).backgroundColor;
           }""",
        FLAT_GRID,
    )

    grid = page.locator(".ag-root-wrapper").nth(FLAT_GRID)
    grid.locator('.ag-floating-filter[col-id="region"] input').fill("EU")
    # `.ag-center-cols-container` no longer exists under this AG-Grid version
    # (the row-container classes were renamed, same family of rename already
    # noted for the sticky-row containers in `grid_dom.py`); count `.ag-row`
    # under the grid root instead, as `go_to_app` above already does. This has
    # to land before the repaint wait below can mean anything.
    page.wait_for_function(
        """(gridIndex) => {
             const grid = document.querySelectorAll('.ag-root-wrapper')[gridIndex];
             return grid.querySelectorAll('.ag-row').length === 3;
           }""",
        arg=FLAT_GRID,
        timeout=10000,
    )

    # The row count landing is not the same event as the colour scale
    # finishing recomputing: `attachColorScaleInvalidation`
    # (`colorScales/index.ts`) clears the stats cache synchronously on
    # `modelUpdated`, then schedules the corrective repaint in a
    # `requestAnimationFrame` as a safety net against listener ordering it
    # does not control — so the row count can reach 3 on the same pass that
    # still paints from the stale, pre-filter population. Wait for IT's
    # background to actually change rather than trusting the row count alone:
    # a repaint that never happens times out here with a clear signal, and a
    # repaint to the wrong colour still fails on the assertion below, which is
    # where it should be seen.
    page.wait_for_function(
        """([gridIndex, previousBackground]) => {
             const grid = document.querySelectorAll('.ag-root-wrapper')[gridIndex];
             const cell = grid.querySelector('.ag-row[row-index="2"] .ag-cell[col-id="pos_minmax"]');
             return !!cell && getComputedStyle(cell).backgroundColor !== previousBackground;
           }""",
        arg=[FLAT_GRID, it_background_before],
        timeout=10000,
    )

    after = cell_backgrounds(page, FLAT_GRID)
    eu_only = [100.0, 200.0, 300.0]
    assert_painted(after["body:0"]["pos_minmax"], expected_rgba("positive", eu_only, 100.0), "DE after")
    # IT was mid-ramp over six rows and is the maximum over three.
    assert_painted(after["body:2"]["pos_minmax"], expected_rgba("positive", eu_only, 300.0), "IT after")
    # Both sides are browser output, so this one compares like with like — but
    # via the 8-bit channel, which is the resolution the browser actually has.
    assert half_up(after["body:2"]["pos_minmax"][3] * 255) != half_up(
        before["body:2"]["pos_minmax"][3] * 255
    )


def test_grid_options_builder_default_is_inherited_by_a_bare_opt_in(page: Page):
    """The consumer's actual migration shape: `configure_color_scale` once per
    grid, then `configure_column(field, color_scale=True)` per metric column —
    no per-column dict at all. Before this test, `readColorScaleConfig`'s
    grid-defaults merge had zero coverage in either language, and it was
    unproven that `gridOptions.context` survives the builder's `build()` and
    the frontend's `cloneDeep` -> `deepMap` -> `updateGridOptions` pipeline to
    arrive as `params.context`.

    `metric_a` here is the same field, over the same fixture rows, as the flat
    grid's `pos_minmax` column (`scheme="positive"`, default mode `minmax`,
    default `skip_non_positive=False`) — so the two must paint identically.
    """
    painted = cell_backgrounds(page, BUILDER_GRID)
    for key, value in zip(FLAT_ROWS, METRIC_A):
        assert_painted(
            painted[key]["metric_a"], expected_rgba("positive", METRIC_A, value), key
        )


def test_default_coldef_cellstyle_disables_the_scale_grid_wide(page: Page):
    """The branch that can silently turn the feature off for an entire grid.

    `defaultColDef.cellStyle` outranks a column's own, otherwise-valid
    `stColorScale` declaration (`callerCellStyleSource` in `colorScales/
    index.ts`), so the built-in is never attached here and no row of the
    `blocked` column may show the positive scheme's colour, however far its
    value sits from the column's minimum or maximum.
    """
    painted = cell_backgrounds(page, DEFAULT_CELLSTYLE_GRID)
    for key in FLAT_ROWS:
        assert_unpainted(painted[key]["blocked"], "positive", key)


# --- Phase 2: grid 5 ----------------------------------------------------------


@pytest.mark.parametrize(
    "col_id,scheme,reverse",
    [
        ("anchor_div", "diverging", False),
        ("anchor_default", "diverging", False),
        ("anchor_rev", "diverging", True),
        ("anchor_pos", "positive", False),
    ],
)
def test_anchor_mode_paints_deviation_from_a_fixed_anchor(page: Page, col_id, scheme, reverse):
    """`ratio` against anchor 1.0, span 1.0: DE and FR below, IT exactly on
    the anchor (unpainted), CA and NY above, TX past the clamp. `anchor_default`
    names no scheme anywhere and must resolve to diverging."""
    painted = cell_backgrounds(page, PHASE2_FLAT_GRID)
    for key, value in zip(FLAT_ROWS, RATIO):
        expected = expected_rgba(scheme, RATIO, value, reverse=reverse, **ANCHOR_1)
        actual = painted[key][col_id]
        if expected is None:
            assert_unpainted(actual, scheme, f"{key}: {col_id}")
        else:
            assert_painted(actual, expected, f"{key}: {col_id}")
    # The exact anchor, pinned explicitly: the gate whose absence would still
    # produce a plausible faint colour.
    assert_unpainted(painted["body:2"][col_id], scheme, f"body:2 (1.0): {col_id}")


def test_anchor_mode_clamps_past_one_span(page: Page):
    painted = cell_backgrounds(page, PHASE2_FLAT_GRID)
    # TX is 2.5 — d = 1.5 before the clamp — and must paint exactly what a
    # value one span above the anchor paints.
    clamped = expected_rgba("diverging", RATIO, 2.5, **ANCHOR_1)
    assert clamped == expected_rgba("diverging", RATIO, 2.0, **ANCHOR_1)
    assert_painted(painted["body:5"]["anchor_div"], clamped, "TX clamped")


def test_reverse_complements_a_minmax_ramp(page: Page):
    painted = cell_backgrounds(page, PHASE2_FLAT_GRID)
    for key, value in zip(FLAT_ROWS, METRIC_A):
        assert_painted(
            painted[key]["rev_minmax"],
            expected_rgba("positive", METRIC_A, value, reverse=True),
            f"{key}: rev_minmax",
        )
    # DE is now the darkest, TX the palest — the opposite of `pos_minmax`.
    assert painted["body:0"]["rev_minmax"][3] > painted["body:5"]["rev_minmax"][3]


def test_reverse_negates_a_zscore_ramp(page: Page):
    painted = cell_backgrounds(page, PHASE2_FLAT_GRID)
    for key, value in zip(FLAT_ROWS, METRIC_A):
        expected = expected_rgba("diverging", METRIC_A, value, reverse=True)
        actual = painted[key]["rev_zscore"]
        if expected is None:
            assert_unpainted(actual, "diverging", f"{key}: rev_zscore")
        else:
            assert_painted(actual, expected, f"{key}: rev_zscore")
    # DE (100, below the mean) now wears the hue TX wears unreversed, and
    # vice versa — the flip, spelled out without a literal.
    assert painted["body:0"]["rev_zscore"][:3] == expected_rgba("diverging", METRIC_A, 600)[:3]
    assert painted["body:5"]["rev_zscore"][:3] == expected_rgba("diverging", METRIC_A, 100)[:3]


def test_rank_paints_only_the_maximum(page: Page):
    painted = cell_backgrounds(page, PHASE2_FLAT_GRID)
    for key, value in zip(FLAT_ROWS, METRIC_A):
        if expected_rank(METRIC_A, value):
            assert_painted(painted[key]["rank_max"], RANK_RGBA, f"{key}: rank_max")
        else:
            assert_unpainted(painted[key]["rank_max"], "rank", f"{key}: rank_max")
    assert font_weight(page, PHASE2_FLAT_GRID, 5, "rank_max") == RANK_FONT_WEIGHT
    assert font_weight(page, PHASE2_FLAT_GRID, 4, "rank_max") == NORMAL_FONT_WEIGHT


def test_rank_reverse_paints_only_the_minimum(page: Page):
    painted = cell_backgrounds(page, PHASE2_FLAT_GRID)
    for key, value in zip(FLAT_ROWS, METRIC_A):
        if expected_rank(METRIC_A, value, reverse=True):
            assert_painted(painted[key]["rank_min"], RANK_RGBA, f"{key}: rank_min")
        else:
            assert_unpainted(painted[key]["rank_min"], "rank", f"{key}: rank_min")
    assert font_weight(page, PHASE2_FLAT_GRID, 0, "rank_min") == RANK_FONT_WEIGHT


def test_fill_paints_every_row_with_the_literal_colour(page: Page):
    painted = cell_backgrounds(page, PHASE2_FLAT_GRID)
    for key in FLAT_ROWS:
        assert_painted(painted[key]["fill_lit"], (4, 5, 6, 1.0), f"{key}: fill_lit")


def test_fill_resolves_a_css_variable_through_the_host_page(page: Page):
    """`var(--st-aggrid-test-fill)` is set on `:root` by the app; the fill
    passes the string through and the browser resolves it — the same path the
    consumer's `--secondary-background-color` takes under CCv2's no-iframe
    delivery."""
    painted = cell_backgrounds(page, PHASE2_FLAT_GRID)
    for key in FLAT_ROWS:
        assert_painted(painted[key]["fill_var"], (7, 8, 9, 1.0), f"{key}: fill_var")


# --- Phase 2: grid 6 ----------------------------------------------------------
#
# Row layout with `groupDefaultExpanded: -1` and the fixture's data order:
# body:0 EU group, body:1-3 DE FR IT, body:4 US group, body:5-7 CA NY TX, and
# the grand total either as the last body row or in the pinned-bottom section
# (located by label, never by index — see `test_the_grand_total_row_is_not_painted`).

EU_LEAVES = {"body:1": 100.0, "body:2": 200.0, "body:3": 300.0}
US_LEAVES = {"body:5": 400.0, "body:6": 500.0, "body:7": 600.0}
EU_VALUES = region_values("EU", "metric_a")
US_VALUES = region_values("US", "metric_a")


def total_row_key(page: Page, grid_index: int) -> str:
    rows = read_rows(page, grid_index)
    return next(key for key, cells in rows.items() if cells.get("ag-Grid-AutoColumn") == "Total")


def test_parent_scope_compares_a_leaf_with_its_siblings_only(page: Page):
    """Under `scope: "parent"` the EU leaves are scaled over 100..300 and the
    US leaves over 400..600, so DE and CA are both palest and IT and TX both
    darkest. The `level_pos` control column, same field, same rows, keeps the
    2.4.0 picture — one 100..600 ramp — which is what makes the two scopes
    distinguishable on one screen."""
    painted = cell_backgrounds(page, SCOPE_GRID)
    for key, value in EU_LEAVES.items():
        assert_painted(painted[key]["parent_pos"], expected_rgba("positive", EU_VALUES, value), f"{key} parent")
        assert_painted(painted[key]["level_pos"], expected_rgba("positive", METRIC_A, value), f"{key} level")
    for key, value in US_LEAVES.items():
        assert_painted(painted[key]["parent_pos"], expected_rgba("positive", US_VALUES, value), f"{key} parent")
        assert_painted(painted[key]["level_pos"], expected_rgba("positive", METRIC_A, value), f"{key} level")
    # Same alpha for DE and CA under parent scope; different under level.
    assert _alpha_channel(painted["body:1"]["parent_pos"][3]) == _alpha_channel(painted["body:5"]["parent_pos"][3])
    assert _alpha_channel(painted["body:1"]["level_pos"][3]) != _alpha_channel(painted["body:5"]["level_pos"][3])


def test_parent_scope_leaves_top_level_groups_unpainted(page: Page):
    # The group rows' parent is the root: they are the groups, not siblings.
    painted = cell_backgrounds(page, SCOPE_GRID)
    assert_unpainted(painted["body:0"]["parent_pos"], "positive", "EU group / parent")
    assert_unpainted(painted["body:4"]["parent_pos"], "positive", "US group / parent")
    assert_unpainted(painted["body:0"]["parent_rank"], "rank", "EU group / parent rank")
    assert_unpainted(painted["body:4"]["parent_rank"], "rank", "US group / parent rank")
    # ...whereas level scope still scales the two groups against each other.
    totals = list(region_totals().values())
    assert_painted(painted["body:0"]["level_pos"], expected_rgba("positive", totals, 600.0), "EU group / level")


def test_rank_under_parent_scope_picks_one_winner_per_group(page: Page):
    painted = cell_backgrounds(page, SCOPE_GRID)
    for key, value in EU_LEAVES.items():
        if expected_rank(EU_VALUES, value):
            assert_painted(painted[key]["parent_rank"], RANK_RGBA, f"{key} parent rank")
        else:
            assert_unpainted(painted[key]["parent_rank"], "rank", f"{key} parent rank")
    for key, value in US_LEAVES.items():
        if expected_rank(US_VALUES, value):
            assert_painted(painted[key]["parent_rank"], RANK_RGBA, f"{key} parent rank")
        else:
            assert_unpainted(painted[key]["parent_rank"], "rank", f"{key} parent rank")
    # Spelled out: IT and TX, one per region.
    assert is_scheme_color(painted["body:3"]["parent_rank"], "rank")
    assert is_scheme_color(painted["body:7"]["parent_rank"], "rank")


def test_rank_under_level_scope_picks_one_winner_per_level(page: Page):
    painted = cell_backgrounds(page, SCOPE_GRID)
    # Leaves: TX alone (600 over 100..600). IT is not the level maximum.
    assert is_scheme_color(painted["body:7"]["level_rank"], "rank")
    assert_unpainted(painted["body:3"]["level_rank"], "rank", "IT / level rank")
    # Groups: US (1500) over EU (600).
    assert is_scheme_color(painted["body:4"]["level_rank"], "rank")
    assert_unpainted(painted["body:0"]["level_rank"], "rank", "EU group / level rank")


def test_fill_reaches_group_rows_and_the_grand_total(page: Page):
    painted = cell_backgrounds(page, SCOPE_GRID)
    for key in ("body:0", "body:1", "body:2", "body:3", "body:4", "body:5", "body:6", "body:7"):
        assert_painted(painted[key]["fill_grouped"], (4, 5, 6, 1.0), f"{key} fill")
    total = total_row_key(page, SCOPE_GRID)
    assert_painted(painted[total].get("fill_grouped"), (4, 5, 6, 1.0), "grand total fill")


def test_filtering_another_group_away_does_not_rescale_a_parent_scoped_column(page: Page):
    """The one property of parent scoping a static grid cannot show.

    `lessThan 15` on `metric_b` keeps DE, FR, IT and drops every US row. The
    EU leaves' *parent* population is still 100/200/300, so `parent_pos`
    must not change; `level_pos`'s population shrinks from 100..600 to
    100..300 and FR moves from t = 0.2 to t = 0.5. FR keeps row-index 2
    through the filter, so its `level_pos` background changing is the repaint
    signal — the same wait `test_filtering_rescales_the_column` uses.
    """
    before = cell_backgrounds(page, SCOPE_GRID)
    fr_level_before = page.evaluate(
        """(gridIndex) => {
             const grid = document.querySelectorAll('.ag-root-wrapper')[gridIndex];
             const cell = grid.querySelector('.ag-row[row-index="2"] .ag-cell[col-id="level_pos"]');
             return getComputedStyle(cell).backgroundColor;
           }""",
        SCOPE_GRID,
    )

    grid = page.locator(".ag-root-wrapper").nth(SCOPE_GRID)
    # `agNumberColumnFilter`'s floating filter renders two inputs: the
    # editable number spinbutton and a disabled read-only text field (its
    # summary fallback for multi-condition filters) — both under the same
    # `.ag-floating-filter[col-id]`, so the enabled one must be singled out.
    grid.locator('.ag-floating-filter[col-id="metric_b"] input:not([disabled])').fill("15")
    # EU group + 3 leaves + the grand total.
    page.wait_for_function(
        """(gridIndex) => {
             const grid = document.querySelectorAll('.ag-root-wrapper')[gridIndex];
             return grid.querySelectorAll('.ag-row').length === 5;
           }""",
        arg=SCOPE_GRID,
        timeout=10000,
    )
    page.wait_for_function(
        """([gridIndex, previousBackground]) => {
             const grid = document.querySelectorAll('.ag-root-wrapper')[gridIndex];
             const cell = grid.querySelector('.ag-row[row-index="2"] .ag-cell[col-id="level_pos"]');
             return !!cell && getComputedStyle(cell).backgroundColor !== previousBackground;
           }""",
        arg=[SCOPE_GRID, fr_level_before],
        timeout=10000,
    )

    after = cell_backgrounds(page, SCOPE_GRID)
    for key, value in EU_LEAVES.items():
        # Unchanged: same expected colour as before the filter, and the same
        # browser output, on the 8-bit grid.
        assert_painted(after[key]["parent_pos"], expected_rgba("positive", EU_VALUES, value), f"{key} parent after")
        assert _alpha_channel(after[key]["parent_pos"][3]) == _alpha_channel(before[key]["parent_pos"][3])
    # Re-scaled: FR is now mid-ramp over three rows, not over six.
    assert_painted(after["body:2"]["level_pos"], expected_rgba("positive", EU_VALUES, 200.0), "FR level after")
    assert _alpha_channel(after["body:2"]["level_pos"][3]) != _alpha_channel(before["body:2"]["level_pos"][3])


def test_a_cell_that_stops_being_the_winner_loses_its_highlight(page: Page):
    """A painted cell must be *un*painted when the next model generation
    says so. `cellStyle` returning `null` does not clear a cell's previous
    inline style under ag-grid-react, so without an explicit clearing style
    the interim winner would keep its highlight after the filter is cleared
    — two winners on screen.

    Filtered to `lessThan 15`, IT (300) is `level_rank`'s leaf winner over
    100..300; cleared, TX (600) is, and IT must go back to plain.
    """
    grid = page.locator(".ag-root-wrapper").nth(SCOPE_GRID)
    filter_input = grid.locator('.ag-floating-filter[col-id="metric_b"] input:not([disabled])')

    filter_input.fill("15")
    page.wait_for_function(
        """(gridIndex) => {
             const grid = document.querySelectorAll('.ag-root-wrapper')[gridIndex];
             return grid.querySelectorAll('.ag-row').length === 5;
           }""",
        arg=SCOPE_GRID,
        timeout=10000,
    )
    # IT keeps row-index 3 through both transitions; wait for it to become the winner.
    page.wait_for_function(
        """([gridIndex, weight]) => {
             const grid = document.querySelectorAll('.ag-root-wrapper')[gridIndex];
             const cell = grid.querySelector('.ag-row[row-index="3"] .ag-cell[col-id="level_rank"]');
             return !!cell && getComputedStyle(cell).fontWeight === weight;
           }""",
        arg=[SCOPE_GRID, RANK_FONT_WEIGHT],
        timeout=10000,
    )
    filtered = cell_backgrounds(page, SCOPE_GRID)
    assert_painted(filtered["body:3"]["level_rank"], RANK_RGBA, "IT while filtered")

    filter_input.fill("")
    page.wait_for_function(
        """(gridIndex) => {
             const grid = document.querySelectorAll('.ag-root-wrapper')[gridIndex];
             return grid.querySelectorAll('.ag-row').length === 9;
           }""",
        arg=SCOPE_GRID,
        timeout=10000,
    )
    # TX is a fresh row comp painted from the new population; once it wears
    # the highlight, the repaint pass that must also clear IT has run.
    page.wait_for_function(
        """([gridIndex, weight]) => {
             const grid = document.querySelectorAll('.ag-root-wrapper')[gridIndex];
             const cell = grid.querySelector('.ag-row[row-index="7"] .ag-cell[col-id="level_rank"]');
             return !!cell && getComputedStyle(cell).fontWeight === weight;
           }""",
        arg=[SCOPE_GRID, RANK_FONT_WEIGHT],
        timeout=10000,
    )
    cleared = cell_backgrounds(page, SCOPE_GRID)
    assert_painted(cleared["body:7"]["level_rank"], RANK_RGBA, "TX after clearing")
    assert_unpainted(cleared["body:3"]["level_rank"], "rank", "IT after clearing")
    assert font_weight(page, SCOPE_GRID, 3, "level_rank") == NORMAL_FONT_WEIGHT
