"""Anchors for the colour-scale reference arithmetic.

`color_scale_fixture.expected_rgba` is what every e2e assertion compares the
browser against, so it needs anchors of its own — hand-computed here from the
formulas in `docs/superpowers/specs/2026-08-29-grid-color-scale-design.md`.
Without these the e2e suite would only prove that two implementations agree,
not that either is right.

The fixture's `metric_a` is the evenly spaced ramp 100..600, whose population
statistics are mean 350 and sd sqrt(175000/6) = 170.78251276599332.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from color_scale_fixture import (  # noqa: E402
    column_values,
    expected_rgba,
    half_up,
    is_scheme_color,
    region_totals,
    stats,
)

METRIC_A = [100.0, 200.0, 300.0, 400.0, 500.0, 600.0]
METRIC_B = [-5.0, 0.0, 10.0, 20.0, 30.0, 40.0]


def test_half_up_rounds_away_from_zero_at_a_half():
    # Python's built-in `round` is half-to-even and would answer 232 here,
    # disagreeing with JavaScript's Math.round. Both languages must use this.
    assert half_up(232.5) == 233
    assert half_up(233.5) == 234
    assert half_up(232.4) == 232


def test_stats_uses_the_population_standard_deviation():
    lo, hi, mean, sd = stats(METRIC_A)
    assert (lo, hi, mean) == (100.0, 600.0, 350.0)
    assert sd == 170.78251276599332


def test_fixture_columns_are_what_the_app_will_render():
    assert column_values("metric_a") == METRIC_A
    assert column_values("metric_b") == METRIC_B
    assert column_values("metric_c") == [7.0] * 6
    assert region_totals() == {"EU": 600.0, "US": 1500.0}


def test_positive_minmax_ramps_linearly_from_006_to_055():
    assert expected_rgba("positive", METRIC_A, 100) == (29, 158, 117, 0.06)
    assert expected_rgba("positive", METRIC_A, 600) == (29, 158, 117, 0.55)
    # t = 0.4 -> 0.06 + 0.4 * 0.49
    assert expected_rgba("positive", METRIC_A, 300) == (29, 158, 117, 0.256)


def test_neutral_zscore_reproduces_the_piecewise_ramp():
    # |z| = 1.46385 -> 0.2 + 0.25 * log10(1.46385)
    assert expected_rgba("neutral", METRIC_A, 100) == (51, 120, 200, 0.241)
    # |z| = 0.87831 -> 0.08 + 0.12 * (0.87831 - 0.5)
    assert expected_rgba("neutral", METRIC_A, 200) == (51, 120, 200, 0.125)


def test_neutral_zscore_leaves_the_dead_zone_unpainted():
    # |z| = 0.29277, inside the 0.5 dead zone.
    assert expected_rgba("neutral", METRIC_A, 300) is None
    assert expected_rgba("neutral", METRIC_A, 400) is None


def test_diverging_zscore_splits_red_below_and_green_above():
    # |z| = 1.4638501094227996, so alpha = 0.2 + log10(|z|) = 0.3654966,
    # which half_up's to 0.365 — it lands 0.0034 *below* the 365.5 boundary,
    # near enough that it must be computed rather than estimated.
    # u = |z|/3 = 0.48795; 240 - 15u = 232.681 -> 233
    assert expected_rgba("diverging", METRIC_A, 100) == (233, 18, 15, 0.365)
    # 190 - 15u = 182.681 -> 183
    assert expected_rgba("diverging", METRIC_A, 600) == (35, 183, 40, 0.365)


def test_diverging_minmax_reaches_full_saturation_at_both_ends():
    assert expected_rgba("diverging", METRIC_A, 100, mode="minmax") == (225, 18, 15, 0.7)
    assert expected_rgba("diverging", METRIC_A, 600, mode="minmax") == (35, 175, 40, 0.7)
    # t = 0.4 -> s = -0.2, u = 0.2; 240 - 3 = 237; alpha 0.1 + 0.2 * 0.6
    assert expected_rgba("diverging", METRIC_A, 300, mode="minmax") == (237, 18, 15, 0.22)


def test_neutral_minmax_uses_the_linear_ramp_between_its_own_endpoints():
    assert expected_rgba("neutral", METRIC_A, 100, mode="minmax") == (51, 120, 200, 0.08)
    assert expected_rgba("neutral", METRIC_A, 600, mode="minmax") == (51, 120, 200, 0.55)


def test_positive_zscore_has_no_piecewise_ramp_so_it_interpolates():
    # u = 0.48795 -> 0.06 + 0.48795 * 0.49
    assert expected_rgba("positive", METRIC_A, 100, mode="zscore") == (29, 158, 117, 0.299)


def test_a_uniform_column_is_never_painted():
    uniform = [7.0] * 6
    assert expected_rgba("positive", uniform, 7) is None
    assert expected_rgba("neutral", uniform, 7) is None


def test_skip_non_positive_drops_the_zero_and_the_negative():
    # Population becomes [10, 20, 30, 40], so 10 sits at t = 0.
    assert expected_rgba("positive", METRIC_B, 10, skip_non_positive=True) == (
        29, 158, 117, 0.06,
    )
    assert expected_rgba("positive", METRIC_B, 40, skip_non_positive=True) == (
        29, 158, 117, 0.55,
    )
    assert expected_rgba("positive", METRIC_B, -5, skip_non_positive=True) is None
    assert expected_rgba("positive", METRIC_B, 0, skip_non_positive=True) is None


def test_without_the_skip_the_negative_participates():
    # neutral's default skip is True, so this pins the explicit override.
    assert expected_rgba("neutral", METRIC_B, -5, skip_non_positive=False) == (
        51, 120, 200, 0.229,
    )


def test_scheme_defaults_match_the_spec():
    # Same value, default mode vs. explicit: proves the default is wired.
    assert expected_rgba("positive", METRIC_A, 300) == expected_rgba(
        "positive", METRIC_A, 300, mode="minmax"
    )
    assert expected_rgba("neutral", METRIC_A, 100) == expected_rgba(
        "neutral", METRIC_A, 100, mode="zscore"
    )
    assert expected_rgba("diverging", METRIC_A, 100) == expected_rgba(
        "diverging", METRIC_A, 100, mode="zscore"
    )


def test_is_scheme_color_recognises_only_its_own_palette():
    assert is_scheme_color((51, 120, 200, 0.2), "neutral")
    assert not is_scheme_color((29, 158, 117, 0.2), "neutral")
    assert is_scheme_color((233, 18, 15, 0.3), "diverging")
    assert is_scheme_color((35, 183, 40, 0.3), "diverging")
    assert not is_scheme_color((0, 0, 0, 0), "positive")
    assert not is_scheme_color(None, "positive")
