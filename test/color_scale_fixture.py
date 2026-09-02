"""Shared fixture for the built-in colour scales.

Owns the row data **and** the reference arithmetic, so no e2e assertion ever
hand-types an expected colour — the convention `ratio_fixture.py` established
for the aggregators. This module is a second, independently written
implementation of the formulas in
`docs/superpowers/specs/2026-08-29-grid-color-scale-design.md`; that is
deliberate, because a single implementation shared with the frontend could not
catch a transcription error in a ramp.

The data is six rows, one per country, two regions:

    region  country  metric_a  metric_b  metric_c
    EU      DE           100        -5         7
    EU      FR           200         0         7
    EU      IT           300        10         7
    US      CA           400        20         7
    US      NY           500        30         7
    US      TX           600        40         7

`metric_a` is an evenly spaced ramp, so a min/max scale and a z-score scale
both have something to say about it, and its two innermost values fall inside
the z-score dead zone. `metric_b` carries a negative and a zero so
`skip_non_positive` is observable in both settings. `metric_c` is constant so
the uniformity gate fires.

`ratio` straddles an anchor of `1.0` with a span of `1.0`: both signs, the
exact anchor (IT), and one value past the clamp (TX).

Summed by region, `metric_a` gives EU 600 and US 1500 — deliberately outside
the leaf range 100..600, so a grid that pooled group totals with leaf values
would paint every leaf near the pale end and the level-scoped rule is
observable rather than inferred.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import floor, log10, sqrt
from typing import Iterable, Optional, Sequence

import pandas as pd

ROW_DIM = "region"
LEAF_DIM = "country"

COLOR_SCALE_ROWS: tuple[dict, ...] = (
    {"region": "EU", "country": "DE", "metric_a": 100, "metric_b": -5, "metric_c": 7, "ratio": 0.5},
    {"region": "EU", "country": "FR", "metric_a": 200, "metric_b": 0, "metric_c": 7, "ratio": 0.9},
    {"region": "EU", "country": "IT", "metric_a": 300, "metric_b": 10, "metric_c": 7, "ratio": 1.0},
    {"region": "US", "country": "CA", "metric_a": 400, "metric_b": 20, "metric_c": 7, "ratio": 1.1},
    {"region": "US", "country": "NY", "metric_a": 500, "metric_b": 30, "metric_c": 7, "ratio": 1.5},
    {"region": "US", "country": "TX", "metric_a": 600, "metric_b": 40, "metric_c": 7, "ratio": 2.5},
)


def color_scale_dataframe() -> pd.DataFrame:
    """The fixture as a DataFrame, in declaration order."""
    return pd.DataFrame(list(COLOR_SCALE_ROWS))


def column_values(field: str) -> list[float]:
    """One column's leaf values, in row order."""
    return [float(row[field]) for row in COLOR_SCALE_ROWS]


def region_totals(field: str = "metric_a") -> dict[str, float]:
    """``field`` summed per region — the level-0 population of a grid that
    row-groups by region."""
    totals: dict[str, float] = {}
    for row in COLOR_SCALE_ROWS:
        totals[row[ROW_DIM]] = totals.get(row[ROW_DIM], 0.0) + float(row[field])
    return totals


def region_values(region: str, field: str = "metric_a") -> list[float]:
    """``field``'s leaf values within one region — the parent-scoped
    population of a grid that row-groups by region."""
    return [float(row[field]) for row in COLOR_SCALE_ROWS if row[ROW_DIM] == region]


# --------------------------------------------------------------------------
# Gates and rounding
# --------------------------------------------------------------------------

#: Below this coefficient of variation a column is treated as uniform.
CV_FLOOR = 0.001
#: Values inside this many standard deviations of the mean are not painted.
Z_DEAD = 0.5
#: |z| at and beyond which the diverging hue is fully saturated.
Z_CAP = 3.0


def half_up(x: float) -> int:
    """``floor(x + 0.5)`` — JavaScript's ``Math.round`` semantics.

    Python's built-in ``round`` is half-to-even (``round(232.5) == 232``) and
    would disagree with the frontend on any exact ``.5``. Every rounding in
    this module and in ``schemes.ts`` goes through this rule.
    """
    return floor(x + 0.5)


# --------------------------------------------------------------------------
# Schemes
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Scheme:
    name: str
    default_mode: str
    default_skip_non_positive: bool
    alpha_min: float
    alpha_max: float


SCHEMES: dict[str, Scheme] = {
    "neutral": Scheme("neutral", "zscore", True, 0.08, 0.55),
    "positive": Scheme("positive", "minmax", False, 0.06, 0.55),
    "diverging": Scheme("diverging", "zscore", True, 0.1, 0.7),
}

#: `rank`'s single highlight: the saturated end of diverging's green, at a
#: fixed alpha. Derived, not typed, so it cannot drift from the ramp.
RANK_ALPHA = 0.35


def _neutral_z_alpha(abs_z: float) -> float:
    if abs_z < 1:
        return 0.08 + 0.12 * (abs_z - 0.5)
    if abs_z < 3:
        return 0.2 + 0.25 * log10(abs_z)
    return 0.55


def _diverging_z_alpha(abs_z: float) -> float:
    if abs_z < 1:
        return 0.1 + 0.2 * (abs_z - 0.5)
    if abs_z < 3:
        return 0.2 + log10(abs_z)
    return 0.7


# --------------------------------------------------------------------------
# Arithmetic
# --------------------------------------------------------------------------


def population(values: Iterable, skip_non_positive: bool) -> list[float]:
    """The values that take part in a column's scale: finite, and strictly
    positive when the skip rule is on."""
    out: list[float] = []
    for raw in values:
        if raw is None:
            continue
        value = float(raw)
        if value != value or value in (float("inf"), float("-inf")):
            continue
        if skip_non_positive and value <= 0:
            continue
        out.append(value)
    return out


def stats(values: Sequence[float]) -> tuple[float, float, float, float]:
    """``(min, max, mean, sd)``. ``sd`` is the **population** standard
    deviation (divisor ``N``), which is what the JavaScript being replaced
    computes."""
    count = len(values)
    mean = sum(values) / count
    sd = sqrt(sum((v - mean) ** 2 for v in values) / count)
    return min(values), max(values), mean, sd


def _rgb(scheme_name: str, signed: float, u: float) -> tuple[int, int, int]:
    if scheme_name == "neutral":
        return (51, 120, 200)
    if scheme_name == "positive":
        return (29, 158, 117)
    if signed < 0:
        return (half_up(240 - 15 * u), 18, 15)
    return (35, half_up(190 - 15 * u), 40)


RANK_RGBA: tuple[int, int, int, float] = (*_rgb("diverging", 1.0, 1.0), RANK_ALPHA)


def _clamp(d: float) -> float:
    return -1.0 if d < -1.0 else 1.0 if d > 1.0 else d


def expected_rgba(
    scheme_name: str,
    values: Iterable,
    value,
    *,
    mode: Optional[str] = None,
    skip_non_positive: Optional[bool] = None,
    reverse: bool = False,
    anchor: Optional[float] = None,
    span: Optional[float] = None,
) -> Optional[tuple[int, int, int, float]]:
    """The ``(r, g, b, alpha)`` a cell must be painted, or ``None`` when it is
    left unpainted.

    ``values`` is the raw population — every value of the same column in the
    same scope, before the skip rule, which is applied here. It is ignored
    under ``mode="anchor"``, which needs ``anchor`` and ``span`` instead.
    ``reverse`` complements a min/max position, negates a z-score, and
    mirrors an anchored deviation.
    """
    scheme = SCHEMES[scheme_name]
    mode = mode or scheme.default_mode
    skip = (
        scheme.default_skip_non_positive
        if skip_non_positive is None
        else skip_non_positive
    )

    if value is None:
        return None
    v = float(value)
    if v != v or v in (float("inf"), float("-inf")):
        return None
    if skip and v <= 0:
        return None

    if mode == "anchor":
        if anchor is None:
            raise ValueError("mode='anchor' needs an anchor")
        if span is None:
            raise ValueError("mode='anchor' needs a span")
        d = _clamp((v - anchor) / span)
        if reverse:
            d = -d
        if d == 0:
            return None
        signed = d
        u = abs(d)
        alpha = scheme.alpha_min + u * (scheme.alpha_max - scheme.alpha_min)
        return (*_rgb(scheme_name, signed, u), half_up(alpha * 1000) / 1000)

    pop = population(values, skip)
    if not pop:
        return None
    low, high, mean, sd = stats(pop)

    if mode == "minmax":
        if high <= low:
            return None
        t = (v - low) / (high - low)
        if reverse:
            t = 1 - t
        if scheme_name == "diverging":
            signed = 2 * t - 1
            u = abs(signed)
        else:
            signed = 1.0
            u = t
        alpha = scheme.alpha_min + u * (scheme.alpha_max - scheme.alpha_min)
    else:
        if sd == 0:
            return None
        # `abs(mean)`: dividing by a signed mean makes the coefficient
        # negative for a negative-mean column, which would silently fail the
        # floor and never paint.
        if mean != 0 and sd / abs(mean) < CV_FLOOR:
            return None
        z = (v - mean) / sd
        if abs(z) < Z_DEAD:
            return None
        if reverse:
            z = -z
        signed = z
        u = min(abs(z) / Z_CAP, 1.0)
        if scheme_name == "neutral":
            alpha = _neutral_z_alpha(abs(z))
        elif scheme_name == "diverging":
            alpha = _diverging_z_alpha(abs(z))
        else:
            alpha = scheme.alpha_min + u * (scheme.alpha_max - scheme.alpha_min)

    return (*_rgb(scheme_name, signed, u), half_up(alpha * 1000) / 1000)


def expected_rank(
    values: Iterable,
    value,
    *,
    reverse: bool = False,
    skip_non_positive: bool = False,
) -> bool:
    """Whether ``value`` is the best of ``values`` — the maximum, or the
    minimum under ``reverse`` — and so painted ``RANK_RGBA``. A population
    of fewer than two is never painted; ties all are."""
    if value is None:
        return False
    v = float(value)
    if skip_non_positive and v <= 0:
        return False
    pop = population(values, skip_non_positive)
    if len(pop) < 2:
        return False
    best = min(pop) if reverse else max(pop)
    return v == best


def is_scheme_color(
    rgba: Optional[tuple[int, int, int, float]], scheme_name: str
) -> bool:
    """Whether an ``(r, g, b, a)`` could have been painted by this scheme.

    Asserting a cell is *unpainted* this way rather than by comparing against
    a transparent background keeps the assertion independent of whatever the
    active theme paints underneath.
    """
    if rgba is None:
        return False
    r, g, b, a = rgba
    if a == 0:
        return False
    if scheme_name == "neutral":
        return (r, g, b) == (51, 120, 200)
    if scheme_name == "positive":
        return (r, g, b) == (29, 158, 117)
    if scheme_name == "rank":
        return (r, g, b) == RANK_RGBA[:3]
    return (g == 18 and b == 15) or (r == 35 and b == 40)
