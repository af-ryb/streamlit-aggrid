"""Data and reference arithmetic for the cohort-shaped pivot grid.

Rebuilt from the consumer's cohort dashboard
(``hitapps_analytics/web_app/web/dashboards/cohort/grid_builder.py``), which is
the only grid in that service that puts a dimension in AG-Grid's *Column
Labels* by default. Two properties of that shape matter here and are why a
generic pivot fixture would not do:

* **The maturity triangle.** ``cohort_day`` only exists up to the age of the
  install cohort, so the (install_date x cohort_day) matrix is ragged: the
  newest cohort has one column's worth of data, the oldest has eight. Empty
  cells are therefore *expected*, and a probe that treats "blank" as "broken"
  would report the triangle as the bug.
* **Flat numerator/denominator pairs.** Every ratio metric arrives as
  ``<metric>_numerator`` / ``<metric>_denominator`` scalar columns, and the
  grid's JS aggregator folds them per pivot cell. A pivot cell's value is
  therefore *not* derivable from its row's total, which is what makes a value
  read out of the wrong pivot column detectable at all.

Nothing here hand-types an expected number: the grid's arithmetic is restated
once, in :func:`expected`, and every assertion goes through it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

#: Anchor for the maturity triangle. Fixed rather than ``date.today()`` so the
#: frame — and every expectation derived from it — is reproducible.
AS_OF = date(2026, 8, 16)

#: Oldest cohort is ``AS_OF - 8d`` (eight cohort days), newest is ``AS_OF - 1d``
#: (one). Same span the owner's screenshot covered.
INSTALL_DATES: tuple[str, ...] = tuple(
    (AS_OF - timedelta(days=n)).isoformat() for n in range(8, 0, -1)
)

COUNTRIES: tuple[str, ...] = ("US", "DE")

#: Row-group dimensions, outermost first — the order the app configures them in
#: and the order AG-Grid encodes into a group row's ``row-id``.
ROW_DIMENSIONS: tuple[str, ...] = ("install_date", "country")

#: Ratio metrics, in the order the app declares their columns.
METRICS: tuple[str, ...] = ("retention", "arpu")

#: Largest ``max_day`` the app offers — the full triangle.
MAX_DAY_LIMIT = 8


def maturity(install_date: str) -> int:
    """How many cohort days that install cohort has lived through."""
    return (AS_OF - date.fromisoformat(install_date)).days


def day_label(cohort_day: int) -> str:
    """``cohort_day`` as the consumer emits it: zero-padded to two digits.

    The consumer's SQL formats it (``FORMAT('%02d', cohort_day)``), so the
    pivot keys are strings and AG-Grid's generated pivot-result colIds read
    ``"00_installs"``, ``"01_retention"``, and so on. Keeping the padding
    matters: it is what makes the pivot key set sort as text the same way it
    sorts as a number.
    """
    return f"{cohort_day:02d}"


def _installs(date_idx: int, country_idx: int) -> int:
    """Cohort size. Constant across cohort days, as in the source data — the
    same install population is measured on every day of its life."""
    return 100 + 10 * date_idx + 50 * country_idx


def _numerator(metric: str, date_idx: int, country_idx: int, cohort_day: int) -> int:
    """Metric numerator for one leaf.

    Deliberately varies with ``cohort_day`` so that neighbouring pivot cells
    hold different values — a cell painted from the wrong pivot column shows a
    wrong number rather than coincidentally the right one.
    """
    if metric == "retention":
        # Decays with cohort age; stays positive across the whole triangle
        # (worst case 100 - 49 - 21 - 1 = 29).
        return _installs(date_idx, country_idx) - 7 * cohort_day - 3 * date_idx - country_idx
    if metric == "arpu":
        # Accumulates with cohort age.
        return 37 + 13 * cohort_day + 7 * date_idx + 5 * country_idx
    raise ValueError(f"unknown metric {metric!r}")


def _denominator(metric: str, date_idx: int, country_idx: int, cohort_day: int) -> int:
    """Every ratio in this fixture is per-install, so the denominator is the
    cohort size — the ``valuePerInstall`` contract the consumer's aggregator
    implements."""
    del metric, cohort_day
    return _installs(date_idx, country_idx)


@dataclass(frozen=True)
class Shape:
    """One state of the query behind the grid.

    The three axes a cohort refresh actually moves along, kept together because
    they are not independent — widening the date range reaches back to older,
    *more mature* cohorts and so grows the pivot key set as a side effect,
    which is precisely what makes a refresh reshape the columns.

    * ``n_dates`` — how far back the range goes. Widening adds older cohorts.
    * ``max_day`` — the ``max_cohort_day`` cap.
    * ``metrics`` — which ratio metrics were requested. The frame carries the
      component columns of these and no others, so adding a metric changes the
      rowData *and* the columnDefs in the same rerun, as it does in the
      service.
    """

    n_dates: int = len(INSTALL_DATES)
    max_day: int = MAX_DAY_LIMIT
    metrics: tuple[str, ...] = METRICS

    def dates(self) -> tuple[str, ...]:
        """The install dates in range, oldest first."""
        return INSTALL_DATES[len(INSTALL_DATES) - self.n_dates :]


def rows(shape: Shape) -> list[dict]:
    """Every leaf row of the triangle for one query shape.

    A leaf's numbers are keyed off its *absolute* position in
    :data:`INSTALL_DATES`, not its position in the current window, so widening
    the range adds rows without altering any value already on screen — the
    property that lets a refresh be checked against the same arithmetic before
    and after.
    """
    out: list[dict] = []
    for install_date in shape.dates():
        date_idx = INSTALL_DATES.index(install_date)
        for country_idx, country in enumerate(COUNTRIES):
            for cohort_day in range(min(maturity(install_date), shape.max_day)):
                row = {
                    "install_date": install_date,
                    "country": country,
                    "cohort_day": day_label(cohort_day),
                    "installs": _installs(date_idx, country_idx),
                }
                for metric in shape.metrics:
                    row[f"{metric}_numerator"] = _numerator(
                        metric, date_idx, country_idx, cohort_day
                    )
                    row[f"{metric}_denominator"] = _denominator(
                        metric, date_idx, country_idx, cohort_day
                    )
                out.append(row)
    return out


def frame(shape: Shape) -> pd.DataFrame:
    """:func:`rows` as the DataFrame the grid is fed."""
    return pd.DataFrame(rows(shape))


def pivot_keys(shape: Shape) -> tuple[str, ...]:
    """The ``cohort_day`` values present in this shape — i.e. the pivot keys
    AG-Grid must generate result columns for, in header order."""
    deepest = min(max(maturity(d) for d in shape.dates()), shape.max_day)
    return tuple(day_label(k) for k in range(deepest))


def _select(
    shape: Shape,
    *,
    install_date: str | None = None,
    country: str | None = None,
    cohort_day: str | None = None,
) -> list[dict]:
    """Leaves under a group path, restricted to one pivot key.

    ``install_date=None`` and ``country=None`` together mean the grand-total
    row; ``country=None`` alone means a first-level group row.
    """
    return [
        row
        for row in rows(shape)
        if (install_date is None or row["install_date"] == install_date)
        and (country is None or row["country"] == country)
        and (cohort_day is None or row["cohort_day"] == cohort_day)
    ]


def expected(
    col: str,
    shape: Shape,
    *,
    install_date: str | None = None,
    country: str | None = None,
    cohort_day: str | None = None,
) -> float | None:
    """What one rendered cell must hold, or ``None`` for a cell that must be
    empty.

    ``col`` is either ``"installs"`` (summed) or a name in :data:`METRICS`
    (folded as ``sum(numerator) / sum(denominator)`` over the leaves of the
    group path within the pivot key — never an average of per-leaf ratios).

    ``None`` covers both empty cases the grid produces, and they are not the
    same thing: no leaves at all (outside the maturity triangle) and a folded
    value of zero, which the consumer's renderer prints as an empty string.
    """
    leaves = _select(
        shape, install_date=install_date, country=country, cohort_day=cohort_day
    )
    if not leaves:
        return None
    if col not in ("installs", *shape.metrics):
        # A column whose data this shape does not carry. Not "empty" — the
        # column has no business being on screen at all, so say so rather than
        # let a KeyError below read as a fixture bug.
        raise KeyError(f"{col!r} is not part of shape {shape}")
    if col == "installs":
        total = sum(row["installs"] for row in leaves)
        return float(total) if total > 0 else None
    numerator = sum(row[f"{col}_numerator"] for row in leaves)
    denominator = sum(row[f"{col}_denominator"] for row in leaves)
    value = numerator / denominator if denominator > 0 else 0.0
    return value if value > 0 else None


#: Field the app pivots on. Part of the generated colIds, so it belongs here
#: rather than being spelled out at each call site.
PIVOT_FIELD = "cohort_day"


def pivot_col_id(cohort_day: str, col: str) -> str:
    """AG-Grid's generated pivot-result colId for one (pivot key, value column)
    pair.

    v36 namespaces it with the pivot field —
    ``pivot_cohort_day_00_installs`` — which is also what makes the consumer's
    ``js_hide_columns`` regexes match at all: they look for ``_<digits>_``, and
    a bare ``00_installs`` would have no leading underscore.
    """
    return f"pivot_{PIVOT_FIELD}_{cohort_day}_{col}"


def pivot_group_col_id(cohort_day: str) -> str:
    """colId of the header group cell that spans one pivot key's columns."""
    return f"pivotGroup_{PIVOT_FIELD}_{cohort_day}_0"


_ROW_ID_SPLIT = re.compile("-(?=" + "|".join(f"{dim}-" for dim in ROW_DIMENSIONS) + ")")


def group_path(row_id: str | None) -> dict[str, str] | None:
    """The dimension path a rendered group row stands for, read off AG-Grid's
    ``row-id`` (``row-group-install_date-2026-08-08-country-US``). ``{}`` is the
    grand-total row; ``None`` means the id is not a group row's.

    Read from the id rather than carried down from the row above, because a
    parent group row that scrolls out is re-rendered in the sticky container —
    a reader that tracks the last-seen label there attributes every child to
    the wrong parent and invents failures.

    Split on the dimension names rather than on ``-`` alone: ``install_date``
    values are ISO dates and carry dashes of their own.
    """
    if row_id is None:
        return None
    if row_id.startswith("rowGroupFooter"):
        return {}
    if not row_id.startswith("row-group-"):
        return None
    path: dict[str, str] = {}
    for part in _ROW_ID_SPLIT.split(row_id[len("row-group-") :]):
        field, _, value = part.partition("-")
        path[field] = value
    return path
