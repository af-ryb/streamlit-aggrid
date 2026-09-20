"""Colour assertions shared by the colour-scale e2e suites.

Lived in `test_grid_color_scale.py` until the picker suite needed the same
alpha-quantisation rule; two copies of that rule would drift.
"""

from playwright.sync_api import Page

from color_scale_fixture import half_up, is_scheme_color


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
