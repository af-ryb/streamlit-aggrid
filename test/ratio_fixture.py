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

Two evaluators live here:

- :func:`evaluate` — the semantics the *declarative* aggregator is specified to
  have, ``((Σ signᵢ·numᵢ)·multiplier / Σden)·scale``.
- :func:`evaluate_legacy` — what the consumer's current ``ratioSum`` JavaScript
  actually computes. It differs on purpose (see :class:`RatioSpec`), and the
  differences are the migration's behaviour changes, pinned by tests instead of
  discovered in production.
"""

from __future__ import annotations

from dataclasses import dataclass
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
RATIO_ROWS: list[dict[str, Any]] = [
    # campaign, country, cost, installs, impressions, seconds, sessions, rebate, revenue, payers
    dict(campaign="A", country="US", cost=800, installs=2,  impressions=20000, seconds=1200, sessions=10, rebate=100, revenue=100, payers=5),
    dict(campaign="A", country="US", cost=100, installs=8,  impressions=5000,  seconds=600,  sessions=20, rebate=10,  revenue=50,  payers=5),
    dict(campaign="A", country="DE", cost=90,  installs=10, impressions=3000,  seconds=300,  sessions=5,  rebate=9,   revenue=30,  payers=2),
    dict(campaign="A", country="DE", cost=10,  installs=80, impressions=2000,  seconds=300,  sessions=15, rebate=1,   revenue=10,  payers=3),
    dict(campaign="B", country="US", cost=9,   installs=10, impressions=1000,  seconds=60,   sessions=2,  rebate=1,   revenue=7,   payers=0),
    dict(campaign="B", country="US", cost=1,   installs=90, impressions=500,   seconds=120,  sessions=3,  rebate=0,   revenue=3,   payers=0),
    dict(campaign="B", country="DE", cost=8,   installs=20, impressions=300,   seconds=30,   sessions=1,  rebate=1,   revenue=4,   payers=0),
    dict(campaign="B", country="DE", cost=2,   installs=80, impressions=200,   seconds=60,   sessions=2,  rebate=1,   revenue=6,   payers=0),
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
)


# --------------------------------------------------------------------------
# Specs
# --------------------------------------------------------------------------


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
        ctx: dict[str, Any] = {"num": list(self.num), "den": list(self.den)}
        if self.num_signs is not None:
            ctx["num_signs"] = list(self.num_signs)
        if self.multiplier != 1.0:
            ctx["multiplier"] = self.multiplier
        if self.scale != 1.0:
            ctx["scale"] = self.scale
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


def evaluate(spec: RatioSpec, rows: Sequence[Mapping[str, Any]]) -> Optional[float]:
    """The specified semantics: ``((Σ signᵢ·numᵢ)·multiplier / Σden)·scale``.

    Every field name resolves to the sum of that field over ``rows`` — the
    node's subtree. When ``Σden == 0`` the result is ``spec.fill_null``, which
    may be ``None`` (an empty cell).
    """
    numerator = sum(
        sign * _sum(rows, name)
        for name, sign in zip(spec.num, spec.resolved_num_signs)
    )
    denominator = sum(_sum(rows, name) for name in spec.den)
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


# --------------------------------------------------------------------------
# DataFrame
# --------------------------------------------------------------------------


def ratio_dataframe() -> pd.DataFrame:
    """The fixture as a grid-ready DataFrame.

    Carries the raw component columns *and* a precomputed scalar per ratio
    column. That mirrors the consumer: leaf cells render the precomputed
    number straight from the dataframe and only group rows run the aggregator,
    so leaf values and rolled-up values come from different code paths and a
    disagreement between them is visible on screen.
    """
    frame = pd.DataFrame(RATIO_ROWS)
    for spec in RATIO_SPECS:
        frame[spec.col_id] = [evaluate(spec, [row]) for row in RATIO_ROWS]
    return frame


DIMENSION_FIELDS: tuple[str, ...] = (ROW_DIM, PIVOT_DIM)

#: Order of columns in the grid: dimensions, then ratios, then components.
GRID_FIELD_ORDER: tuple[str, ...] = (
    *DIMENSION_FIELDS,
    *(spec.col_id for spec in RATIO_SPECS),
    *COMPONENT_FIELDS,
)
