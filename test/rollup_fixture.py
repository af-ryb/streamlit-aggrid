"""Leaves, the server's `CUBE` answer, and the expected value of every node,
for the `stRollup` e2e suite.

The totals are synthetic on purpose: every grouping set carries an offset,
the full-grain set included, so no total equals any sum of the rows beneath
it. A real `CUBE` would make the full-grain totals equal their leaves; here a
grid that summed instead of looking up fails every assertion. Tests never
hand-type an expected number they could derive from `expected()`.
"""

from __future__ import annotations

import datetime as dt
from itertools import product

import pandas as pd

DIMENSIONS = ("event_date", "app_version")
DATES = (dt.date(2026, 10, 1), dt.date(2026, 10, 2))
#: `None` is a real NULL `app_version` — a present level whose value is NULL.
VERSIONS = ("1.19.1", "1.20.0", None)
#: Not a dimension: grouping by it must find no totals.
PLATFORM = {"1.19.1": "ios", "1.20.0": "android", None: "android"}

#: Offset by how many dimensions a grouping set keeps present.
OFFSET = {2: 7, 1: 1000, 0: 20000}

#: The one grouping set whose total the server returned as NULL.
NULL_TOTAL_KEY = {"app_version": "1.20.0"}

LEAVES: list[dict] = [
    {
        "row_no": n,
        "event_date": date,
        "app_version": version,
        "platform": PLATFORM[version],
        "dau": 100 * (i + 1) + 10 * (j + 1),
    }
    for n, ((i, date), (j, version)) in enumerate(
        product(enumerate(DATES), enumerate(VERSIONS))
    )
]


def expected(dims: dict) -> int | None:
    """The total the server sent for the grouping set `dims` (field → value,
    `None` for a NULL value). `None` for `NULL_TOTAL_KEY`."""
    if dims == NULL_TOTAL_KEY:
        return None
    rows = [r for r in LEAVES if all(r[k] == v for k, v in dims.items())]
    return sum(r["dau"] for r in rows) + OFFSET[len(dims)]


def _dates(frame: pd.DataFrame, dates: str) -> pd.DataFrame:
    if dates == "datetime64":
        frame["event_date"] = pd.to_datetime(frame["event_date"])
    return frame


def leaves_frame(dates: str = "date") -> pd.DataFrame:
    """`date`: a `datetime.date` column (Arrow `date32`). `datetime64`: a
    timestamp column (ISO strings after `prepare_frame`)."""
    return _dates(pd.DataFrame(LEAVES), dates)


def cube_frame(dates: str = "date", bump: int = 0) -> pd.DataFrame:
    """Every grouping set, full grain included, as BigQuery returns it:
    rolled-up dimensions are NULL and flagged 1. Shuffled, so the index is
    not a range — what splitting one query result leaves behind."""
    records = []
    for present in ((), ("event_date",), ("app_version",), DIMENSIONS):
        combos = sorted({tuple(r[d] for d in present) for r in LEAVES}, key=repr)
        for combo in combos:
            dims = dict(zip(present, combo))
            total = expected(dims)
            records.append(
                {
                    "event_date": dims.get("event_date"),
                    "app_version": dims.get("app_version"),
                    "dau": None if total is None else total + bump,
                    "_grouping_event_date": int("event_date" not in present),
                    "_grouping_app_version": int("app_version" not in present),
                }
            )
    frame = pd.DataFrame(records).sample(frac=1, random_state=0)
    return _dates(frame, dates)


def corrupt(frame: pd.DataFrame) -> pd.DataFrame:
    """Rename one full-grain key so that its group misses while every field of
    the group's key is a declared dimension — a desync the grid must warn
    about."""
    frame = frame.copy()
    full = (frame["_grouping_event_date"] == 0) & (frame["_grouping_app_version"] == 0)
    target = full & (frame["app_version"] == "1.19.1") & (frame["event_date"] == DATES[0])
    frame.loc[target, "app_version"] = "9.9.9"
    return frame
