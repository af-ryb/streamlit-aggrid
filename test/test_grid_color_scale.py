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

from color_scale_fixture import column_values, expected_rgba, half_up, is_scheme_color
from e2e_utils import StreamlitRunner
from grid_dom import cell_backgrounds

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
