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
    column_values,
    expected_rgba,
    half_up,
    is_scheme_color,
    region_totals,
)
from e2e_utils import StreamlitRunner
from grid_dom import cell_backgrounds, read_rows

ROOT_DIRECTORY = Path(__file__).parent.parent.absolute()
APP_FILE = ROOT_DIRECTORY / "test" / "grid_color_scale.py"

FLAT_GRID = 0
GROUPED_GRID = 1
PIVOT_GRID = 2

#: The flat grid's body rows, in fixture order: DE, FR, IT, CA, NY, TX.
FLAT_ROWS = tuple(f"body:{index}" for index in range(6))

METRIC_A = column_values("metric_a")


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
        "() => document.querySelectorAll('.ag-root-wrapper').length >= 3",
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


def test_positive_minmax_paints_the_flat_ramp(page: Page):
    """The end-to-end smoke: a declaration in `context` alone, with no JsCode,
    paints the column the fixture says it should."""
    painted = cell_backgrounds(page, FLAT_GRID)
    for key, value in zip(FLAT_ROWS, METRIC_A):
        assert_painted(
            painted[key]["pos_minmax"], expected_rgba("positive", METRIC_A, value), key
        )


METRIC_B = column_values("metric_b")
METRIC_C = column_values("metric_c")


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

    grid = page.locator(".ag-root-wrapper").nth(FLAT_GRID)
    grid.locator('.ag-floating-filter[col-id="region"] input').fill("EU")
    # `.ag-center-cols-container` no longer exists under this AG-Grid version
    # (the row-container classes were renamed, same family of rename already
    # noted for the sticky-row containers in `grid_dom.py`); count `.ag-row`
    # under the grid root instead, as `go_to_app` above already does.
    page.wait_for_function(
        """(gridIndex) => {
             const grid = document.querySelectorAll('.ag-root-wrapper')[gridIndex];
             return grid.querySelectorAll('.ag-row').length === 3;
           }""",
        arg=FLAT_GRID,
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
