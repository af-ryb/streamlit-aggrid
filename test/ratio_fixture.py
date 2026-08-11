"""Shared fixture for ratio-aggregation examples and tests.

A ratio metric cannot be aggregated by aggregating the ratio: a group's value
is ``Σnumerator / Σdenominator``, never the average of its children's ratios.
This module owns the data and the arithmetic that every ratio example and test
in this repo compares against, so the JavaScript baseline
(``grid_ratio_js.py``) and any future built-in aggregator are held to the same
numbers rather than to two independently hand-typed tables.

The row data is the reference fixture from
``docs/superpowers/specs/2026-08-10-declarative-ratio-aggregation-design.md``:
every level discriminates ``Σnum/Σden`` from ``avg(ratio)``, so a test built on
it cannot pass against a broken implementation.

    campaign A / country US   cost  900   installs  10
    campaign A / country DE   cost  100   installs  90
    campaign B / country US   cost   10   installs 100
    campaign B / country DE   cost   10   installs 100

    campaign A   = 1000/100 = 10.00
    campaign B   =   20/200 =  0.10
    grand total  = 1020/300 =  3.40   <- correct
    avg of the two campaign ratios =  5.05   <- multi-level trap
    avg of the eight leaf ratios   = 52.87   <- single-level trap

Each (campaign, country) cell is split into two rows so that pivot cells
aggregate too, and so a pivot cell's value differs from its row's total: an
aggregator that ignores the pivot key returns 10.00 for both A/US and A/DE
instead of 90.00 and 1.1111.

Five evaluators live here, one pair per aggregator plus the plain-``RatioSpec``
pair above:

- :func:`evaluate` / :func:`evaluate_legacy` — the ``stRatio`` semantics (also
  what :data:`SHARE_SPEC` uses, via its ``den_const``: a window-constant
  denominator folded in alongside any summed fields).
- :func:`evaluate_ratio_of_ratios` / :func:`evaluate_ratio_of_ratios_legacy` —
  the ``stRatioOfRatios`` semantics: ``to_ratio / from_ratio``, each leg its
  own ``Σnum/Σden``. See :data:`GROWTH_SPECS`.
- :func:`evaluate_weighted_avg` — the ``stWeightedAvg`` semantics:
  ``Σ(vᵢ·wᵢ)/Σwᵢ`` over a precomputed per-row ratio, skipping non-finite
  values and non-positive weights. See :data:`WEIGHTED_SPECS`. It has no
  legacy counterpart — there is no retired JavaScript to compare it to.

Every ``evaluate*`` variant agrees on the same rule the Global Constraints
require: the *declarative* semantics gate every denominator at ``!= 0``, and
the *legacy* semantics gate at ``> 0``. ``growth_neg`` is the fixture column
that makes the difference visible: campaign B's *from*-period ratio is
negative, so the declarative aggregator renders a negative growth number
where the retired JavaScript would have rendered nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Iterable, Mapping, Optional, Sequence

import pandas as pd


# --------------------------------------------------------------------------
# Row data
# --------------------------------------------------------------------------

#: Source rows. Two per (campaign, country) cell. Column meanings:
#: ``cost``/``installs`` -> cpi, ``cost``/``impressions`` -> cpm (x1000),
#: ``seconds``/``sessions`` -> session length in minutes (x1/60),
#: ``cost``-``rebate``/``installs`` -> net cpi (signed numerator),
#: ``revenue``/``payers`` -> revenue per payer, whose denominator collapses to
#: zero for the whole of campaign B.
#:
#: ``ads_d0``/``inst_d0`` -> ``inst_d1`` is period-0 (``d0``) vs period-1
#: (``d1``) installs-attributed ad spend, feeding :data:`GROWTH_SPECS`'s
#: ``growth`` ratio-of-ratios: ``inst_d0`` equals ``inst_d1`` on every row, so
#: the growth number reduces to ``Σads_d1/Σads_d0`` and the denominator drops
#: out — a property used to hand-check the reference values below.
#: ``credits_d0`` mirrors ``ads_d0`` with campaign B's sign flipped, feeding
#: ``growth_neg``: campaign B's *from*-period ratio is negative (network
#: credits, refunds), which is what pins the ``> 0`` -> ``!= 0`` behaviour
#: change the Global Constraints require.
#: ``wa_value``/``wa_weight`` feed :data:`WEIGHTED_SPECS`'s weighted average.
#: Row 2's ``wa_value`` is ``None`` (NaN once in a DataFrame) — a leaf the
#: weighted average must skip rather than treat as zero. Row 4's
#: ``wa_weight`` is ``-100`` — a leaf the ``weight > 0`` gate must also skip.
#: ``-100`` rather than ``0`` on purpose: under ``Σ(vᵢwᵢ)/Σwᵢ`` a ``w=0`` leaf
#: is unobservable regardless of whether it is skipped (it contributes ``0``
#: either way), so no test could ever catch a missing gate. Row 4's ``-100``
#: exactly cancels row 5's ``+100`` when a broken implementation sums every
#: weight regardless of sign, which drives B/US to a division-by-zero blank,
#: B's campaign total to ``3.0`` instead of the correct ``4.0``, and the
#: grand total to ``2.54`` instead of ``3.36`` — three levels that only
#: discriminate a dropped gate because of this row. See
#: ``test_wavg_gate_excludes_the_negative_weight_row``.
RATIO_ROWS: list[dict[str, Any]] = [
    # campaign, country, cost, installs, impressions, seconds, sessions, rebate, revenue, payers, ads_d0, inst_d0, ads_d1, inst_d1, credits_d0, wa_value, wa_weight
    dict(campaign="A", country="US", cost=800, installs=2,  impressions=20000, seconds=1200, sessions=10, rebate=100, revenue=100, payers=5, ads_d0=80, inst_d0=2,  ads_d1=70, inst_d1=2,  credits_d0=80,  wa_value=10,   wa_weight=2),
    dict(campaign="A", country="US", cost=100, installs=8,  impressions=5000,  seconds=600,  sessions=20, rebate=10,  revenue=50,  payers=5, ads_d0=20, inst_d0=8,  ads_d1=20, inst_d1=8,  credits_d0=20,  wa_value=1,    wa_weight=8),
    dict(campaign="A", country="DE", cost=90,  installs=10, impressions=3000,  seconds=300,  sessions=5,  rebate=9,   revenue=30,  payers=2, ads_d0=9,  inst_d0=10, ads_d1=35, inst_d1=10, credits_d0=9,   wa_value=None, wa_weight=10),
    dict(campaign="A", country="DE", cost=10,  installs=80, impressions=2000,  seconds=300,  sessions=15, rebate=1,   revenue=10,  payers=3, ads_d0=1,  inst_d0=90, ads_d1=5,  inst_d1=90, credits_d0=1,   wa_value=2,    wa_weight=90),
    dict(campaign="B", country="US", cost=9,   installs=10, impressions=1000,  seconds=60,   sessions=2,  rebate=1,   revenue=7,   payers=0, ads_d0=6,  inst_d0=10, ads_d1=9,  inst_d1=10, credits_d0=-6,  wa_value=5,    wa_weight=-100),
    dict(campaign="B", country="US", cost=1,   installs=90, impressions=500,   seconds=120,  sessions=3,  rebate=0,   revenue=3,   payers=0, ads_d0=4,  inst_d0=90, ads_d1=1,  inst_d1=90, credits_d0=-4,  wa_value=3,    wa_weight=100),
    dict(campaign="B", country="DE", cost=8,   installs=20, impressions=300,   seconds=30,   sessions=1,  rebate=1,   revenue=4,   payers=0, ads_d0=15, inst_d0=20, ads_d1=30, inst_d1=20, credits_d0=-15, wa_value=4,    wa_weight=50),
    dict(campaign="B", country="DE", cost=2,   installs=80, impressions=200,   seconds=60,   sessions=2,  rebate=1,   revenue=6,   payers=0, ads_d0=5,  inst_d0=80, ads_d1=10, inst_d1=80, credits_d0=-5,  wa_value=6,    wa_weight=50),
]

#: Nodes where ``Σnum/Σden`` unavoidably coincides with the average of the
#: node's children, keyed ``(col_id, campaign)``. Discrimination is impossible
#: whenever the children share a denominator, and the spec's reference fixture
#: fixes campaign B at ``10/100`` in both countries — so every column
#: denominated by ``installs`` is degenerate there, as is every column whose
#: denominator collapses to zero. Listed rather than hidden: a test asserts
#: both that these really are degenerate and that nothing else is.
DEGENERATE_NODES: frozenset[tuple[str, str]] = frozenset(
    {
        ("cpi", "B"),  # both countries are 10/100
        ("net_cpi", "B"),  # same denominator, 100 installs each
        ("arpp", "B"),  # zero payers throughout
        ("arpp_blank", "B"),  # zero payers throughout
        ("wavg_blank", "B"),  # zero payers throughout: both children are None
        ("wavg_zero", "B"),  # zero payers throughout: both children are 0.0
        # B/US's negative-weight leaf (row 4, wa_weight=-100) is skipped
        # entirely, so B/US reduces to row 5's own value (3.0); B/DE is 5.0.
        # Their plain average (4.0) happens to equal B's properly
        # Σ(vᵢ·wᵢ)/Σwᵢ total (3·100 + 4·50 + 6·50)/(100+50+50) = 4.0 too — a
        # genuine coincidence of these particular numbers, verified
        # independently of the aggregator, not a defect. Declared for the
        # same reason every other entry here is: measured, not left for a
        # test to trip over silently.
        ("wavg", "B"),
    }
)

#: Cells where a pivot cell's value equals its row's total, keyed
#: ``(col_id, campaign, country)``. An aggregator that ignores the pivot key
#: returns the row total, so these cells cannot detect that defect. Campaign A
#: detects it on every column; campaign B is blind wherever its two countries
#: carry identical components.
PIVOT_BLIND_CELLS: frozenset[tuple[str, str, str]] = frozenset(
    {
        ("cpi", "B", "US"),
        ("cpi", "B", "DE"),
        ("arpp", "B", "US"),
        ("arpp", "B", "DE"),
        ("arpp_blank", "B", "US"),
        ("arpp_blank", "B", "DE"),
        ("wavg_blank", "B", "US"),
        ("wavg_blank", "B", "DE"),
        ("wavg_zero", "B", "US"),
        ("wavg_zero", "B", "DE"),
    }
)

#: Raw component columns, in grid order. These are summed with AG-Grid's
#: built-in ``sum`` and are what the ratio aggregator reads.
COMPONENT_FIELDS: tuple[str, ...] = (
    "cost",
    "installs",
    "impressions",
    "seconds",
    "sessions",
    "rebate",
    "revenue",
    "payers",
    "ads_d0",
    "inst_d0",
    "ads_d1",
    "inst_d1",
    "credits_d0",
    "wa_value",
    "wa_weight",
)


# --------------------------------------------------------------------------
# Specs
# --------------------------------------------------------------------------


def _num_den_context(
    num: Iterable[str],
    den: Iterable[str],
    num_signs: Optional[Iterable[int]],
    multiplier: float,
    scale: float,
    den_const: Optional[float],
) -> dict[str, Any]:
    """The ``{num, den, ...}`` shape shared by :meth:`RatioSpec.to_context`
    and one leg of a :class:`RatioOfRatiosSpec` (:func:`_leg_context`).
    Optional keys are emitted only when non-default."""
    ctx: dict[str, Any] = {"num": list(num), "den": list(den)}
    if num_signs is not None:
        ctx["num_signs"] = list(num_signs)
    if multiplier != 1.0:
        ctx["multiplier"] = multiplier
    if scale != 1.0:
        ctx["scale"] = scale
    if den_const is not None:
        ctx["den_const"] = den_const
    return ctx


@dataclass(frozen=True)
class RatioSpec:
    """One ratio column, declared the way the design spec declares it.

    Mirrors the subset of the consumer's ``MetricSpec`` that drives ratio
    aggregation (``num``, ``den``, ``num_signs``, ``multiplier``, ``scale``,
    ``fill_null``) with no Streamlit or dashboard dependency.
    """

    col_id: str
    header: str
    num: tuple[str, ...]
    den: tuple[str, ...]
    num_signs: Optional[tuple[int, ...]] = None
    multiplier: float = 1.0
    scale: float = 1.0
    den_const: Optional[float] = None
    """Added to ``Σden`` before the zero check, so a ratio can be declared
    against a window-constant denominator (:data:`SHARE_SPEC`'s ``share``,
    whose ``den`` is empty and whose whole denominator is this constant) or a
    real component field plus a constant floor. ``None`` — the default —
    contributes nothing, which is not the same as ``0.0``: an explicit
    ``den_const=0.0`` still participates in ``to_context()``."""
    fill_null: Optional[float] = None
    """Value when ``Σden == 0``. Defaults to ``None`` — an empty cell — which
    is what the JavaScript being replaced already renders on group rows, so
    the migration changes no dashboard. Note this is *not* ``MetricSpec``'s
    default (``0.0``, honoured by its Python materialization path): the two
    paths disagree today, and the consumer's ``to_agg_context()`` has to pass
    ``fill_null`` through explicitly rather than rely on either default."""
    #: Set when the legacy JavaScript cannot express this spec, naming the
    #: reason. Such columns are baseline-negative: the JS number is recorded as
    #: what it is, not as what it should be.
    legacy_gap: Optional[str] = None

    @property
    def resolved_num_signs(self) -> tuple[int, ...]:
        return self.num_signs if self.num_signs is not None else (1,) * len(self.num)

    def to_context(self) -> dict[str, Any]:
        """The declarative ``colDef.context["stRatio"]`` payload the design
        specifies. Optional keys are emitted only when non-default, matching
        what ``MetricSpec.to_agg_context()`` does today."""
        ctx = _num_den_context(
            self.num, self.den, self.num_signs, self.multiplier, self.scale, self.den_const
        )
        if self.fill_null is not None:
            ctx["fill_null"] = self.fill_null
        return ctx

    def to_legacy_context(self) -> dict[str, Any]:
        """The flat ``{num, num2, den, multiplier, scale}`` payload the
        consumer's current ``ratioSum`` JavaScript reads, as produced by
        ``MetricSpec.to_agg_context()``.

        The shape carries no signs and at most two numerator terms — the
        documented capability gap the declarative aggregator closes.
        """
        ctx: dict[str, Any] = {}
        if self.num:
            ctx["num"] = self.num[0]
        if len(self.num) > 1:
            ctx["num2"] = self.num[1]
        if self.den:
            ctx["den"] = self.den[0]
        if self.multiplier != 1.0:
            ctx["multiplier"] = self.multiplier
        if self.scale != 1.0:
            ctx["scale"] = self.scale
        return ctx


RATIO_SPECS: tuple[RatioSpec, ...] = (
    RatioSpec(
        col_id="cpi",
        header="CPI",
        num=("cost",),
        den=("installs",),
    ),
    RatioSpec(
        col_id="cpm",
        header="CPM",
        num=("cost",),
        den=("impressions",),
        multiplier=1000.0,
    ),
    RatioSpec(
        col_id="sess_min",
        header="Session min",
        num=("seconds",),
        den=("sessions",),
        scale=1.0 / 60.0,
    ),
    RatioSpec(
        col_id="net_cpi",
        header="Net CPI",
        num=("cost", "rebate"),
        den=("installs",),
        num_signs=(1, -1),
        legacy_gap=(
            "ratioSum adds every numerator term; it has no num_signs, so it "
            "computes (cost + rebate)/installs instead of (cost - rebate)/installs"
        ),
    ),
    # The two zero-denominator cases, side by side: an explicit `fill_null=0.0`
    # and the default. Campaign B has no payers at all, so every campaign-B
    # node exercises the collapsed-denominator branch.
    RatioSpec(
        col_id="arpp",
        header="ARPP",
        num=("revenue",),
        den=("payers",),
        fill_null=0.0,
    ),
    RatioSpec(
        col_id="arpp_blank",
        header="ARPP (blank)",
        num=("revenue",),
        den=("payers",),
    ),
)

RATIO_SPECS_BY_ID: Mapping[str, RatioSpec] = {s.col_id: s for s in RATIO_SPECS}

#: A ratio whose denominator includes its own numerator — `part / (part + rest)`,
#: the shape retention, conversion rate and share-of-total take. Only
#: expressible because `den` is a list, and the case where summing per
#: occurrence rather than per distinct name silently doubles the shared field.
#: Deliberately outside `RATIO_SPECS`: that tuple drives the JavaScript
#: baseline suite and the degenerate-node declarations, which are about a
#: different property and should not move for this.
OVERLAP_SPEC = RatioSpec(
    col_id="rebate_share",
    header="Rebate share",
    num=("rebate",),
    den=("rebate", "cost"),
)


def _leg_context(leg: Mapping[str, Any]) -> dict[str, Any]:
    """The ``{num, den, ...}`` payload for one :class:`RatioOfRatiosSpec` leg
    — the same shape :func:`_num_den_context` builds for a whole
    :class:`RatioSpec`, minus ``col_id``/``header``/``fill_null``, which are
    the outer spec's concern, not a leg's."""
    return _num_den_context(
        leg.get("num", ()),
        leg.get("den", ()),
        leg.get("num_signs"),
        leg.get("multiplier", 1.0),
        leg.get("scale", 1.0),
        leg.get("den_const"),
    )


@dataclass(frozen=True)
class RatioOfRatiosSpec:
    """One growth-style column: ``to_ratio / from_ratio``, each leg its own
    ``Σnum/Σden``. A ``growth`` column over two time windows is the running
    example — ``from_leg`` is period 0, ``to_leg`` is period 1 — but nothing
    here is period-specific; a leg is just a ratio.

    Each leg is a plain ``RatioSpec``-shaped mapping (``num``, ``den``, and
    optionally ``num_signs``, ``multiplier``, ``scale``, ``den_const``) rather
    than a full ``RatioSpec``: a leg has no ``col_id``, ``header`` or
    ``fill_null`` of its own — only the outer spec is a grid column, and only
    the outer spec's ``fill_null`` is reachable (a collapsed leg always
    evaluates to ``None``, never a leg-local filler).
    """

    col_id: str
    header: str
    from_leg: Mapping[str, Any]
    to_leg: Mapping[str, Any]
    fill_null: Optional[float] = None
    """Value when either leg's denominator collapses to zero, or when
    ``from_ratio`` itself is exactly zero (the outer division's own ``!= 0``
    gate — see the Global Constraints). Defaults to ``None``, same as
    ``RatioSpec.fill_null``."""

    def to_context(self) -> dict[str, Any]:
        """The declarative ``colDef.context["stRatioOfRatios"]`` payload:
        ``{"from": {...}, "to": {...}}`` plus ``fill_null`` when set."""
        ctx: dict[str, Any] = {
            "from": _leg_context(self.from_leg),
            "to": _leg_context(self.to_leg),
        }
        if self.fill_null is not None:
            ctx["fill_null"] = self.fill_null
        return ctx


@dataclass(frozen=True)
class WeightedAvgSpec:
    """One weighted-average column: ``Σ(vᵢ·wᵢ)/Σwᵢ`` over a precomputed
    per-row ratio ``value`` and its ``weight`` — the shape a blended CPI,
    blended ARPU or any "average of an already-computed metric" column takes.
    Unlike :class:`RatioSpec`, there is no numerator/denominator field pair to
    sum: ``value`` is read straight off each row.
    """

    col_id: str
    header: str
    value: str
    weight: str
    scale: float = 1.0
    fill_null: Optional[float] = None
    """Value when the surviving weight sums to ``0`` — every row was skipped
    because its value was non-finite or its weight was not positive. Defaults
    to ``None``, same as ``RatioSpec.fill_null``."""

    def to_context(self) -> dict[str, Any]:
        """The declarative ``colDef.context["stWeightedAvg"]`` payload:
        ``{"value": ..., "weight": ...}`` plus non-default ``scale`` /
        ``fill_null``."""
        ctx: dict[str, Any] = {"value": self.value, "weight": self.weight}
        if self.scale != 1.0:
            ctx["scale"] = self.scale
        if self.fill_null is not None:
            ctx["fill_null"] = self.fill_null
        return ctx


#: `growth` from ads_d0/inst_d0 to ads_d1/inst_d1 — the direction-
#: discriminating column the P1 spec asks for: A/US is 0.9 (below 1) while
#: campaign A's row total is 1.181818… (above 1), so a pivot cell cannot pass
#: by silently reading its row's total. `inst_d0` equals `inst_d1` on every
#: row, so growth reduces to `Σads_d1/Σads_d0` — used to hand-check the
#: reference table in `test_ratio_fixture.py`.
#:
#: `growth_neg` is the same shape from `credits_d0`/`inst_d0` to
#: `ads_d1`/`inst_d1`. `credits_d0` mirrors `ads_d0` with campaign B's sign
#: flipped, so campaign B's *from*-ratio is negative — the case the Global
#: Constraints' `> 0` -> `!= 0` behaviour change exists for.
GROWTH_SPECS: tuple[RatioOfRatiosSpec, ...] = (
    RatioOfRatiosSpec(
        col_id="growth",
        header="Growth",
        from_leg={"num": ("ads_d0",), "den": ("inst_d0",)},
        to_leg={"num": ("ads_d1",), "den": ("inst_d1",)},
    ),
    RatioOfRatiosSpec(
        col_id="growth_neg",
        header="Growth (net)",
        from_leg={"num": ("credits_d0",), "den": ("inst_d0",)},
        to_leg={"num": ("ads_d1",), "den": ("inst_d1",)},
    ),
)

GROWTH_SPECS_BY_ID: Mapping[str, RatioOfRatiosSpec] = {
    s.col_id: s for s in GROWTH_SPECS
}

#: `wavg` proves the skip rules over `wa_value`/`wa_weight`: A/DE ignores row
#: 2's NaN value (else its 2.0 would be 1.8, treating the missing value as 0)
#: and B/US ignores row 4's negative weight, reducing to row 5's own value,
#: 3.0 (an unweighted average of both leaves' raw values would instead give
#: 4.0).
#: `wavg` is degenerate at campaign B regardless (see `DEGENERATE_NODES`) —
#: B/US's 3.0 and B/DE's 5.0 happen to average to exactly B's own total, 4.0.
#:
#: `wavg_blank`/`wavg_zero` share `wa_value`/`payers` — campaign B has zero
#: payers throughout, so the surviving weight collapses to 0 in both
#: countries — and differ only in `fill_null`, the same blank-vs-zero pairing
#: `arpp`/`arpp_blank` already demonstrates for `RatioSpec`.
WEIGHTED_SPECS: tuple[WeightedAvgSpec, ...] = (
    WeightedAvgSpec(
        col_id="wavg",
        header="Weighted avg",
        value="wa_value",
        weight="wa_weight",
    ),
    WeightedAvgSpec(
        col_id="wavg_blank",
        header="Weighted avg (blank)",
        value="wa_value",
        weight="payers",
    ),
    WeightedAvgSpec(
        col_id="wavg_zero",
        header="Weighted avg (zero)",
        value="wa_value",
        weight="payers",
        fill_null=0.0,
    ),
)

WEIGHTED_SPECS_BY_ID: Mapping[str, WeightedAvgSpec] = {
    s.col_id: s for s in WEIGHTED_SPECS
}

#: `share = cost / 1020`, scaled to a percentage. `den=()` — the entire
#: denominator is the constant — and `Σcost` across every row is exactly
#: `1020`, so the grand total is exactly `100.0`. That is the anchor that
#: proves `den_const` is a window-wide constant and not something summed once
#: per leaf: an aggregator that added `1020` per row instead of once would
#: blow the grand total far past 100.
SHARE_SPEC = RatioSpec(
    col_id="share",
    header="Share",
    num=("cost",),
    den=(),
    den_const=1020.0,
    scale=100.0,
)

#: Dimensions, outermost first. ``campaign`` groups rows; ``country`` is the
#: pivot dimension in the pivot grid and the second grouping level in the
#: row-group grid.
ROW_DIM = "campaign"
PIVOT_DIM = "country"


# --------------------------------------------------------------------------
# Arithmetic
# --------------------------------------------------------------------------


def _sum(rows: Sequence[Mapping[str, Any]], field_name: str) -> float:
    return float(sum(row[field_name] for row in rows))


def _signed_sum(
    rows: Sequence[Mapping[str, Any]], names: Sequence[str], signs: Sequence[int]
) -> float:
    """``Σ signᵢ·fieldᵢ`` — the numerator core shared by :func:`evaluate` and
    one leg of a ratio-of-ratios (:func:`_leg_value`)."""
    return sum(sign * _sum(rows, name) for name, sign in zip(names, signs))


def _den_sum(
    rows: Sequence[Mapping[str, Any]],
    names: Sequence[str],
    den_const: Optional[float],
) -> float:
    """``Σ fieldᵢ + den_const`` — the denominator core shared by
    :func:`evaluate` and one leg of a ratio-of-ratios. ``den_const`` folds in
    a window-constant term (:data:`SHARE_SPEC`) alongside any summed fields."""
    total = sum(_sum(rows, name) for name in names)
    if den_const is not None:
        total += den_const
    return total


def evaluate(spec: RatioSpec, rows: Sequence[Mapping[str, Any]]) -> Optional[float]:
    """The specified semantics: ``((Σ signᵢ·numᵢ)·multiplier / (Σden +
    den_const))·scale``.

    Every field name resolves to the sum of that field over ``rows`` — the
    node's subtree. When the denominator is ``0`` the result is
    ``spec.fill_null``, which may be ``None`` (an empty cell).
    """
    numerator = _signed_sum(rows, spec.num, spec.resolved_num_signs)
    denominator = _den_sum(rows, spec.den, spec.den_const)
    if denominator == 0:
        return spec.fill_null
    return (numerator * spec.multiplier / denominator) * spec.scale


def evaluate_legacy(
    spec: RatioSpec, rows: Sequence[Mapping[str, Any]]
) -> Optional[float]:
    """What the consumer's current ``ratioSum`` JavaScript computes.

    Reproduces its behaviour exactly, including the parts that differ from
    :func:`evaluate`:

    - numerator terms are **added**, never subtracted (no ``num_signs``);
    - at most two numerator terms (``num``, ``num2``) are read;
    - the guard is ``Σden > 0``, not ``Σden != 0``, so a negative denominator
      also falls through to the empty case;
    - the empty case is always ``None``, never a configurable ``fill_null``.
    """
    ctx = spec.to_legacy_context()
    numerator = 0.0
    if "num" in ctx:
        numerator += _sum(rows, ctx["num"])
    if "num2" in ctx:
        numerator += _sum(rows, ctx["num2"])
    denominator = _sum(rows, ctx["den"]) if "den" in ctx else 0.0
    if denominator > 0:
        return (numerator / denominator) * spec.multiplier * spec.scale
    return None


def _leg_numerator(rows: Sequence[Mapping[str, Any]], leg: Mapping[str, Any]) -> float:
    num = leg.get("num", ())
    signs = leg.get("num_signs")
    return _signed_sum(rows, num, signs if signs is not None else (1,) * len(num))


def _leg_value(rows: Sequence[Mapping[str, Any]], leg: Mapping[str, Any]) -> Optional[float]:
    """One :class:`RatioOfRatiosSpec` leg, gated the same ``!= 0`` way as
    :func:`evaluate`. A leg has no ``fill_null`` of its own — a collapsed leg
    is always ``None``, and the outer evaluator decides what that means."""
    denominator = _den_sum(rows, leg.get("den", ()), leg.get("den_const"))
    if denominator == 0:
        return None
    numerator = _leg_numerator(rows, leg)
    return (numerator * leg.get("multiplier", 1.0) / denominator) * leg.get("scale", 1.0)


def _leg_value_legacy(
    rows: Sequence[Mapping[str, Any]], leg: Mapping[str, Any]
) -> Optional[float]:
    """Same leg, gated ``Σden > 0`` — the retired JavaScript's guard, so a
    negative leg denominator also blanks (matching :func:`evaluate_legacy`)."""
    denominator = _den_sum(rows, leg.get("den", ()), leg.get("den_const"))
    if denominator <= 0:
        return None
    numerator = _leg_numerator(rows, leg)
    return (numerator * leg.get("multiplier", 1.0) / denominator) * leg.get("scale", 1.0)


def evaluate_ratio_of_ratios(
    rows: Sequence[Mapping[str, Any]], spec: RatioOfRatiosSpec
) -> Optional[float]:
    """``to_ratio / from_ratio``, each leg the same ``Σnum/Σden`` semantics as
    :func:`evaluate`. Every gate is ``!= 0``: a leg's own denominator
    collapsing, *and* the outer division by ``from_ratio``, both fall through
    to ``spec.fill_null`` only when they are exactly zero — a negative
    ``from_ratio`` (campaign B's ``growth_neg``) still divides.
    """
    from_ratio = _leg_value(rows, spec.from_leg)
    to_ratio = _leg_value(rows, spec.to_leg)
    if from_ratio is None or to_ratio is None or from_ratio == 0:
        return spec.fill_null
    return to_ratio / from_ratio


def evaluate_ratio_of_ratios_legacy(
    rows: Sequence[Mapping[str, Any]], spec: RatioOfRatiosSpec
) -> Optional[float]:
    """The retired JavaScript: each leg gated ``Σden > 0``, and the outer
    division additionally requires ``from_ratio > 0``. Exists so the ``> 0``
    -> ``!= 0`` behaviour change is a pinned number (``growth_neg``'s campaign
    B, whose ``from_ratio`` is negative) rather than a surprise found in
    production.
    """
    from_ratio = _leg_value_legacy(rows, spec.from_leg)
    to_ratio = _leg_value_legacy(rows, spec.to_leg)
    if from_ratio is None or to_ratio is None or not (from_ratio > 0):
        return None
    return to_ratio / from_ratio


def evaluate_weighted_avg(
    rows: Sequence[Mapping[str, Any]], spec: WeightedAvgSpec
) -> Optional[float]:
    """``Σ(vᵢ·wᵢ)/Σwᵢ`` over rows where ``vᵢ`` is finite *and* ``wᵢ > 0``.

    A row failing either condition is skipped entirely — it contributes to
    neither the numerator nor the surviving weight — so a NaN value cannot
    poison a group's total (``wavg`` at A/DE) and a non-positive weight cannot
    pass as a valid zero-value observation (``wavg`` at B/US). The result is
    ``spec.fill_null`` when the surviving weight sums to ``0``, same as every
    other aggregator here.
    """
    total_weighted = 0.0
    total_weight = 0.0
    for row in rows:
        weight = row[spec.weight]
        if weight is None or not (weight > 0):
            continue
        value = row[spec.value]
        if value is None or not isfinite(value):
            continue
        total_weighted += value * weight
        total_weight += weight
    if total_weight == 0:
        return spec.fill_null
    return (total_weighted / total_weight) * spec.scale


def evaluate_avg_of(values: Iterable[Optional[float]]) -> Optional[float]:
    """Average of already-computed child ratios — the statistically wrong
    rollup. Tests assert the fixture's correct value differs from this, so a
    passing test proves the aggregator re-derived the ratio instead of
    averaging."""
    present = [v for v in values if v is not None]
    if not present:
        return None
    return sum(present) / len(present)


def as_text(value: Optional[float]) -> str:
    """Render a reference number the way the grids' valueFormatter does —
    four decimals, empty string for a null. Shared so the JavaScript baseline
    and the built-in aggregator are compared against identically formatted
    expectations."""
    return "" if value is None else f"{value:.4f}"


def rows_where(**dims: Optional[str]) -> list[dict[str, Any]]:
    """Rows matching the given dimension values. ``rows_where()`` is every row
    (the grand total); ``rows_where(campaign="A")`` is one row group;
    ``rows_where(campaign="A", country="US")`` is one pivot cell."""
    selected = RATIO_ROWS
    for name, value in dims.items():
        if value is None:
            continue
        selected = [row for row in selected if row[name] == value]
    return list(selected)


def expected(col_id: str, **dims: Optional[str]) -> Optional[float]:
    """Correct value of a ratio column over the rows matching ``dims``."""
    return evaluate(RATIO_SPECS_BY_ID[col_id], rows_where(**dims))


def expected_legacy(col_id: str, **dims: Optional[str]) -> Optional[float]:
    """Value the current JavaScript produces over the rows matching ``dims``."""
    return evaluate_legacy(RATIO_SPECS_BY_ID[col_id], rows_where(**dims))


def expected_ratio_of_ratios(col_id: str, **dims: Optional[str]) -> Optional[float]:
    """Correct value of a ratio-of-ratios column over the rows matching
    ``dims``. Mirrors :func:`expected`'s signature."""
    return evaluate_ratio_of_ratios(rows_where(**dims), GROWTH_SPECS_BY_ID[col_id])


def expected_weighted_avg(col_id: str, **dims: Optional[str]) -> Optional[float]:
    """Correct value of a weighted-average column over the rows matching
    ``dims``. Mirrors :func:`expected`'s signature."""
    return evaluate_weighted_avg(rows_where(**dims), WEIGHTED_SPECS_BY_ID[col_id])


# --------------------------------------------------------------------------
# DataFrame
# --------------------------------------------------------------------------


def ratio_dataframe() -> pd.DataFrame:
    """The fixture as a grid-ready DataFrame.

    Carries the raw component columns *and* a precomputed scalar per ratio,
    ratio-of-ratios, weighted-average and share column. That mirrors the
    consumer: leaf cells render the precomputed number straight from the
    dataframe and only group rows run the aggregator, so leaf values and
    rolled-up values come from different code paths and a disagreement
    between them is visible on screen. Row 2's precomputed ``wavg`` is `None`
    (NaN) — its own ``wa_value`` is null, so even the single-row evaluation
    has nothing to average.
    """
    frame = pd.DataFrame(RATIO_ROWS)
    for spec in RATIO_SPECS:
        frame[spec.col_id] = [evaluate(spec, [row]) for row in RATIO_ROWS]
    frame[SHARE_SPEC.col_id] = [evaluate(SHARE_SPEC, [row]) for row in RATIO_ROWS]
    for ror_spec in GROWTH_SPECS:
        frame[ror_spec.col_id] = [
            evaluate_ratio_of_ratios([row], ror_spec) for row in RATIO_ROWS
        ]
    for wavg_spec in WEIGHTED_SPECS:
        frame[wavg_spec.col_id] = [
            evaluate_weighted_avg([row], wavg_spec) for row in RATIO_ROWS
        ]
    return frame


DIMENSION_FIELDS: tuple[str, ...] = (ROW_DIM, PIVOT_DIM)

#: Order of columns in the grid: dimensions, then ratios, then components.
GRID_FIELD_ORDER: tuple[str, ...] = (
    *DIMENSION_FIELDS,
    *(spec.col_id for spec in RATIO_SPECS),
    *COMPONENT_FIELDS,
)
