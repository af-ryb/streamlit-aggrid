# Declarative Ratio Aggregation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a built-in `stRatio` aggregator so grids can compute `Σnum/Σden` rollups from a declarative `colDef.context` payload instead of injected JavaScript.

**Architecture:** A single TypeScript module owns the arithmetic, the sort comparator and the registration. `parseGridOptions` — the one funnel every `gridOptions` object already passes through — merges the aggregator into `gridOptions.aggFuncs` (caller-supplied entries win) and installs the comparator on every column that uses it. Python's only role is to reject a malformed or unresolvable declaration before it reaches the browser; it learns nothing about ratio semantics.

**Tech Stack:** TypeScript / React / Vite / AG-Grid 36.0.0 Enterprise · Python 3.13 · Streamlit 1.56 · pytest + Playwright.

**Design spec:** `docs/superpowers/specs/2026-08-10-declarative-ratio-aggregation-design.md`. Read it first — it records what was measured against a running grid, including four corrections to the original design that this plan implements.

## Global Constraints

- **Aggregator name:** `stRatio`. **Context key:** `colDef.context["stRatio"]`.
- **`fill_null` defaults to `None`** (an empty cell), *not* `0.0`. This matches what the JavaScript being replaced already renders, so no dashboard changes.
- **Nulls sort last in both directions.** Requires the comparator; AG-Grid's native behaviour is nulls-first-ascending.
- **The value object exposes `toNumber()`, not `valueOf()`.** `valueOf()` leaves a column containing a null completely unsorted.
- **Field names are validated against the DataFrame, never against `columnDefs`.** The aggregator reads `rowNode.data[field]`; a component does not need a column. Validating against `columnDefs` would reject 7 of the consumer's 12 ratio components.
- **No new frontend dependencies and no JS test runner.** This repo has none by design: `test/unit/` is pure Python, everything else is Playwright e2e driving a standalone Streamlit app of the same name (`test/conftest.py` auto-marks it `e2e`). TypeScript is therefore verified through the browser.
- **`test/ratio_fixture.py` is the single source of expected numbers** for bulk assertions: anything that loops over columns or levels derives its expectation from `expected()` / `as_text()`, never from a typed-out table.
  A *small* number of hand-typed literal anchors is deliberate and required — `pytest.approx(8.8)`, `== "3.4000"` and friends. They are the only thing standing between the suite and a fixture that is itself wrong: a test that compares the grid to `evaluate()` and nothing else passes just as happily when both are broken. Where the task text gives a literal, keep it.
- **Frontend rebuild after every TypeScript change:**
  ```bash
  cd st_aggrid/frontend && COREPACK_ENABLE_DOWNLOAD_PROMPT=0 corepack yarn build
  ```
  `yarn` is not on PATH — always `corepack yarn`. Run `corepack yarn install` once first (from the repo root or `st_aggrid/frontend`; it is a workspace, so `node_modules/` lands at the repo root). `build` wipes `build/` and emits content-hashed filenames, so `git status` shows a delete + an add, not a modify. `st_aggrid/frontend/build/` is committed on purpose. Each glob in `st_aggrid/component.py` must match exactly one file.
- **Fast Python loop:** `pytest -m "not e2e"` (seconds). **Browser loop:** `pytest test/test_<name>.py`.

## Already in place

Committed before this plan and used by every task — do not recreate:

| File | Role |
|---|---|
| `test/ratio_fixture.py` | Row data, `RatioSpec`, `evaluate()` (specified semantics), `evaluate_legacy()` (the JavaScript's semantics), `expected()`, `as_text()`, and the declared blind spots |
| `test/unit/test_ratio_fixture.py` | Guards the fixture's arithmetic and its discriminating power |
| `test/grid_ratio_js.py` | The JavaScript baseline app — the consumer's `ratioSum` verbatim |
| `test/test_grid_ratio_js.py` | Pins the baseline, including its two defects |

`test/conftest.py` puts `test/` on `sys.path`, so `from ratio_fixture import ...` works from `test/`, from `test/unit/`, and from a Streamlit app launched as a subprocess.

---

### Task 1: Python-side validation of the `stRatio` declaration

Pure Python, no browser, no frontend build. An unresolvable field name is the one failure mode that produces a wrong number with no error at all, so it is rejected before the payload leaves Python.

**Files:**
- Create: `st_aggrid/ratio.py`
- Modify: `st_aggrid/aggrid.py` (import, and one call after `_parse_data_and_grid_options`)
- Test: `test/unit/test_ratio_validation.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `st_aggrid.ratio.AGG_FUNC_NAME: str` — `"stRatio"`
  - `st_aggrid.ratio.CONTEXT_KEY: str` — `"stRatio"`
  - `st_aggrid.ratio.validate_ratio_columns(grid_options: dict | None, data_columns: Iterable[str] | None) -> None` — raises `ValueError`; returns `None` on success. `data_columns=None` skips the field-existence check only.

- [ ] **Step 1: Write the failing tests**

Create `test/unit/test_ratio_validation.py`:

```python
"""Validation rules for the built-in `stRatio` declaration.

The dangerous failure is a field name that resolves to nothing: the aggregator
sums `rowNode.data[field]`, a missing key contributes 0, and the ratio comes
out wrong with nothing raised anywhere. Every rule here exists to turn a silent
wrong number into a loud error.
"""

import pytest

from st_aggrid.ratio import validate_ratio_columns

COLUMNS = ["campaign", "cost", "installs", "rebate"]


def grid_options(context, **col_overrides):
    """One ratio column carrying `context`, plus a plain dimension column."""
    column = {"colId": "cpi", "field": "cpi", "aggFunc": "stRatio"}
    column.update(col_overrides)
    if context is not None:
        column["context"] = {"stRatio": context}
    return {"columnDefs": [{"field": "campaign", "rowGroup": True}, column]}


VALID = {"num": ["cost"], "den": ["installs"]}


def test_a_valid_declaration_passes():
    validate_ratio_columns(grid_options(VALID), COLUMNS)


def test_every_optional_key_is_accepted():
    validate_ratio_columns(
        grid_options(
            {
                "num": ["cost", "rebate"],
                "den": ["installs"],
                "num_signs": [1, -1],
                "multiplier": 1000,
                "scale": 0.5,
                "fill_null": 0.0,
            }
        ),
        COLUMNS,
    )


def test_fill_null_may_be_none():
    validate_ratio_columns(grid_options({**VALID, "fill_null": None}), COLUMNS)


def test_unknown_numerator_field_is_rejected():
    with pytest.raises(ValueError, match="spend"):
        validate_ratio_columns(grid_options({"num": ["spend"], "den": ["installs"]}), COLUMNS)


def test_unknown_denominator_field_is_rejected():
    with pytest.raises(ValueError, match="clicks"):
        validate_ratio_columns(grid_options({"num": ["cost"], "den": ["clicks"]}), COLUMNS)


def test_the_error_names_the_column_and_lists_what_is_available():
    with pytest.raises(ValueError) as excinfo:
        validate_ratio_columns(grid_options({"num": ["spend"], "den": ["installs"]}), COLUMNS)
    message = str(excinfo.value)
    assert "cpi" in message
    assert "spend" in message
    assert "installs" in message  # the available names


def test_fields_are_checked_against_the_data_not_the_column_defs():
    """`revenue_total` has no colDef and never will — it rides in the
    dataframe as an aggregation input only. Requiring a column would reject
    every ARPU and ROAS column the consumer defines."""
    validate_ratio_columns(
        grid_options({"num": ["revenue_total"], "den": ["installs"]}),
        ["campaign", "revenue_total", "installs"],
    )


def test_field_existence_is_skipped_when_there_is_no_data_to_check_against():
    validate_ratio_columns(grid_options({"num": ["spend"], "den": ["installs"]}), None)


def test_structural_rules_still_apply_without_data():
    with pytest.raises(ValueError, match="num"):
        validate_ratio_columns(grid_options({"num": [], "den": ["installs"]}), None)


@pytest.mark.parametrize(
    "context",
    [
        {"den": ["installs"]},
        {"num": ["cost"]},
        {"num": [], "den": ["installs"]},
        {"num": ["cost"], "den": []},
        {"num": "cost", "den": ["installs"]},
        {"num": [""], "den": ["installs"]},
        {"num": [1], "den": ["installs"]},
    ],
    ids=["no-num", "no-den", "empty-num", "empty-den", "num-not-a-list", "empty-name", "non-string"],
)
def test_num_and_den_must_be_non_empty_lists_of_names(context):
    with pytest.raises(ValueError):
        validate_ratio_columns(grid_options(context), COLUMNS)


def test_num_signs_length_must_match_num():
    with pytest.raises(ValueError, match="num_signs"):
        validate_ratio_columns(
            grid_options({"num": ["cost", "rebate"], "den": ["installs"], "num_signs": [1]}),
            COLUMNS,
        )


def test_num_signs_must_be_numbers():
    with pytest.raises(ValueError, match="num_signs"):
        validate_ratio_columns(grid_options({**VALID, "num_signs": ["+"]}), COLUMNS)


@pytest.mark.parametrize("key", ["multiplier", "scale"])
def test_multiplier_and_scale_must_be_numeric(key):
    with pytest.raises(ValueError, match=key):
        validate_ratio_columns(grid_options({**VALID, key: "1000"}), COLUMNS)


def test_fill_null_must_be_numeric_or_none():
    with pytest.raises(ValueError, match="fill_null"):
        validate_ratio_columns(grid_options({**VALID, "fill_null": "blank"}), COLUMNS)


def test_agg_func_without_a_context_is_rejected():
    with pytest.raises(ValueError, match="context"):
        validate_ratio_columns(grid_options(None), COLUMNS)


def test_a_context_on_a_column_group_child_is_validated():
    """Marketing wraps its metric columns in column groups, so the walk has to
    descend into `children` or validation silently covers nothing."""
    options = {
        "columnDefs": [
            {
                "headerName": "Acquisition",
                "children": [
                    {
                        "colId": "cpi",
                        "aggFunc": "stRatio",
                        "context": {"stRatio": {"num": ["spend"], "den": ["installs"]}},
                    }
                ],
            }
        ]
    }
    with pytest.raises(ValueError, match="spend"):
        validate_ratio_columns(options, COLUMNS)


def test_columns_without_a_ratio_context_are_ignored():
    options = {
        "columnDefs": [
            {"field": "campaign", "rowGroup": True},
            {"field": "cost", "aggFunc": "sum"},
            {"field": "notes", "context": {"metric_doc": {"name": "notes"}}},
        ]
    }
    validate_ratio_columns(options, COLUMNS)


def test_missing_or_empty_grid_options_are_ignored():
    validate_ratio_columns(None, COLUMNS)
    validate_ratio_columns({}, COLUMNS)
    validate_ratio_columns({"columnDefs": []}, COLUMNS)
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
.venv/bin/python -m pytest test/unit/test_ratio_validation.py -q
```

Expected: collection error, `ModuleNotFoundError: No module named 'st_aggrid.ratio'`.

- [ ] **Step 3: Write the implementation**

Create `st_aggrid/ratio.py`:

```python
"""Validation for the built-in ``stRatio`` aggregator's declaration.

The arithmetic lives in the frontend (``frontend/src/aggFuncs/stRatio.ts``).
Python's only job is to reject a declaration that would otherwise produce a
silently wrong number.

An unresolvable field name is the dangerous case: the aggregator sums
``rowNode.data[field]`` over a node's subtree, and a name that is not in the
data contributes ``0``, which skews the ratio without raising anything. Names
are checked against the **data**, not against ``columnDefs`` — a component only
has to be present in the row data, and requiring a column of its own would
reject the common case of an aggregation input that is never displayed.
"""

from __future__ import annotations

from typing import Any, Iterable, Iterator, Optional

AGG_FUNC_NAME = "stRatio"
CONTEXT_KEY = "stRatio"

_NUMERIC = (int, float)


def _is_number(value: Any) -> bool:
    # bool is an int subclass; a True multiplier is a mistake, not a 1.
    return isinstance(value, _NUMERIC) and not isinstance(value, bool)


def _iter_column_defs(column_defs: Any) -> Iterator[dict]:
    """Every leaf and group colDef, depth first. Column groups nest their
    columns under ``children``; a walk that stops at the top level would cover
    nothing on a grouped grid."""
    if not isinstance(column_defs, (list, tuple)):
        return
    for column in column_defs:
        if not isinstance(column, dict):
            continue
        yield column
        yield from _iter_column_defs(column.get("children"))


def _label(column: dict) -> str:
    name = column.get("colId") or column.get("field")
    return f"column {name!r}" if name else "unnamed ratio column"


def _field_names(value: Any, key: str, label: str) -> list[str]:
    if not isinstance(value, (list, tuple)) or not value:
        raise ValueError(
            f"{label}: context['{CONTEXT_KEY}']['{key}'] must be a non-empty "
            f"list of field names, got {value!r}."
        )
    for name in value:
        if not isinstance(name, str) or not name:
            raise ValueError(
                f"{label}: every '{key}' entry must be a non-empty string, "
                f"got {value!r}."
            )
    return list(value)


def _validate_config(config: Any, column: dict, known: Optional[set]) -> None:
    label = _label(column)

    if not isinstance(config, dict):
        raise ValueError(
            f"{label}: context['{CONTEXT_KEY}'] must be a dict, "
            f"got {type(config).__name__}."
        )

    num = _field_names(config.get("num"), "num", label)
    den = _field_names(config.get("den"), "den", label)

    signs = config.get("num_signs")
    if signs is not None:
        if not isinstance(signs, (list, tuple)) or not all(_is_number(s) for s in signs):
            raise ValueError(f"{label}: 'num_signs' must be a list of numbers, got {signs!r}.")
        if len(signs) != len(num):
            raise ValueError(
                f"{label}: 'num_signs' has {len(signs)} entries but 'num' has "
                f"{len(num)}; they must line up term for term."
            )

    for key in ("multiplier", "scale"):
        if key in config and config[key] is not None and not _is_number(config[key]):
            raise ValueError(f"{label}: '{key}' must be a number, got {config[key]!r}.")

    if "fill_null" in config:
        fill_null = config["fill_null"]
        if fill_null is not None and not _is_number(fill_null):
            raise ValueError(
                f"{label}: 'fill_null' must be a number or None, got {fill_null!r}."
            )

    if known is not None:
        unknown = [name for name in (*num, *den) if name not in known]
        if unknown:
            raise ValueError(
                f"{label}: unknown field(s) {unknown} in the ratio declaration. "
                f"{AGG_FUNC_NAME} sums these from the row data; a name that is "
                f"not there contributes 0 and silently skews the ratio. "
                f"Available: {sorted(known)}."
            )


def validate_ratio_columns(
    grid_options: Optional[dict],
    data_columns: Optional[Iterable[str]] = None,
) -> None:
    """Raise ``ValueError`` for a malformed or unresolvable ratio declaration.

    Parameters
    ----------
    grid_options:
        The built grid options. Ignored when None or when it declares no
        columns.
    data_columns:
        Column names available in the row data. ``None`` skips the
        field-existence check — the structural rules still apply — because
        there is nothing to check against rather than because anything is
        known to be valid.
    """
    if not isinstance(grid_options, dict):
        return

    known = set(data_columns) if data_columns is not None else None

    for column in _iter_column_defs(grid_options.get("columnDefs")):
        context = column.get("context")
        config = context.get(CONTEXT_KEY) if isinstance(context, dict) else None

        if config is None:
            if column.get("aggFunc") == AGG_FUNC_NAME:
                raise ValueError(
                    f"{_label(column)}: aggFunc {AGG_FUNC_NAME!r} requires "
                    f"context[{CONTEXT_KEY!r}] carrying 'num' and 'den'."
                )
            continue

        _validate_config(config, column, known)
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
.venv/bin/python -m pytest test/unit/test_ratio_validation.py -q
```

Expected: PASS (all of them).

- [ ] **Step 5: Call the validator from `AgGrid`**

In `st_aggrid/aggrid.py`, add the import beside the existing `st_aggrid` imports near the top:

```python
from st_aggrid.ratio import validate_ratio_columns
```

The `_parse_data_and_grid_options(...)` call currently discards its third return value as `_column_types`. Rename that binding to `column_types` — the validation needs it.

Then, immediately after that call and before `custom_css = custom_css or {}`, insert:

```python
    # A ratio column whose components are not in the data would aggregate to a
    # wrong number with nothing raised, so reject it here rather than let it
    # reach the browser. Checked against the data's columns: `stRatio` reads
    # row data, so a component needs no column of its own.
    #
    # Read from `column_types` (the dtypes snapshot) rather than `data_df`.
    # `_parse_data_and_grid_options` sets `data_df = None` whenever it
    # JSON-serializes rowData — which the default `use_json_serialization="auto"`
    # does for any frame carrying a dict cell, even in a column unrelated to
    # the ratio. Reading `data_df.columns` there would silently skip the check
    # that is this task's entire point. The dtypes are captured before that
    # branch, and before `::auto_unique_id::` is injected, so they are both
    # available and cleaner.
    validate_ratio_columns(
        grid_options,
        column_types.index if column_types is not None else None,
    )
```

Cover it with a regression test — append to `test/unit/test_ratio_validation.py`:

```python
def test_validation_survives_the_json_rowdata_fallback():
    """`use_json_serialization="auto"` nulls out the DataFrame for any frame
    with a dict cell, even in a column the ratio never touches. The check must
    still fire — that path is exactly where a silently wrong ratio would go
    unnoticed."""
    import pandas as pd

    from st_aggrid import AgGrid

    frame = pd.DataFrame(
        {"campaign": ["A"], "cost": [10], "installs": [2], "tags": [{"a": 1}]}
    )
    options = {
        "columnDefs": [
            {"field": "campaign", "rowGroup": True},
            {
                "colId": "cpi",
                "aggFunc": "stRatio",
                "context": {"stRatio": {"num": ["spend"], "den": ["installs"]}},
            },
        ]
    }

    with pytest.raises(ValueError, match="spend"):
        AgGrid(frame, grid_options=options, key="ratio_validation_json_probe")
```

- [ ] **Step 6: Add the wiring test**

Append to `test/unit/test_ratio_validation.py`:

```python
def test_aggrid_rejects_an_unresolvable_ratio_before_rendering():
    """The rule has to fire from `AgGrid`, not just from the validator."""
    import pandas as pd

    from st_aggrid import AgGrid

    frame = pd.DataFrame({"campaign": ["A"], "cost": [10], "installs": [2]})
    options = {
        "columnDefs": [
            {"field": "campaign", "rowGroup": True},
            {
                "colId": "cpi",
                "aggFunc": "stRatio",
                "context": {"stRatio": {"num": ["spend"], "den": ["installs"]}},
            },
        ]
    }

    with pytest.raises(ValueError, match="spend"):
        AgGrid(frame, grid_options=options, key="ratio_validation_probe")
```

- [ ] **Step 7: Run the whole fast suite**

```bash
.venv/bin/python -m pytest -m "not e2e" -q
```

Expected: PASS. The validation must fire before `AgGrid` reaches component registration, so this stays a pure-Python test with no Streamlit runtime.

- [ ] **Step 8: Commit**

```bash
git add st_aggrid/ratio.py st_aggrid/aggrid.py test/unit/test_ratio_validation.py
git commit -m "Validate stRatio column declarations against the data"
```

---

### Task 2: The `stRatio` aggregator, under row grouping

The arithmetic, the value object and the registration. Pivot comes in Task 3 and sorting in Task 4; this task must be correct at both grouping levels and at the grand-total row.

**Files:**
- Create: `st_aggrid/frontend/src/aggFuncs/stRatio.ts`
- Modify: `st_aggrid/frontend/src/utils/parsers.ts`
- Create: `test/grid_dom.py`
- Modify: `test/test_grid_ratio_js.py` (import the extracted helpers instead of defining them)
- Create: `test/grid_ratio_builtin.py`
- Create: `test/test_grid_ratio_builtin.py`
- Rebuild: `st_aggrid/frontend/build/`

**Interfaces:**
- Consumes: `test/ratio_fixture.py` (`RATIO_SPECS`, `expected`, `as_text`, `ratio_dataframe`, `COMPONENT_FIELDS`, `ROW_DIM`, `PIVOT_DIM`).
- Produces, from `src/aggFuncs/stRatio.ts`:
  - `ST_RATIO: string` — `"stRatio"`
  - `interface StRatioConfig { num: string[]; den: string[]; num_signs?: number[]; multiplier?: number; scale?: number; fill_null?: number | null }`
  - `interface StRatioValue { value: number | null; sums: Record<string, number>; toNumber(): number | null; toString(): string }`
  - `readStRatioConfig(colDef?: ColDef | null): StRatioConfig | null`
  - `stRatioAggFunc(params: IAggFuncParams): StRatioValue | null`
  - `registerStRatio(gridOptions: GridOptions, debug?: boolean): GridOptions`
  - Task 4 adds `stRatioComparator` to this module.

- [ ] **Step 1: Write the example app**

Create `test/grid_ratio_builtin.py`. Grid order is fixed — Task 3 appends a third grid, so these indices stay stable:

```python
"""Streamlit app: ratio aggregation via the built-in `stRatio` aggregator.

The counterpart to `grid_ratio_js.py`. Same fixture, same grouping, same
columns — the only difference is that no JavaScript crosses the boundary: the
ratio is declared as data in `colDef.context["stRatio"]` and computed by the
aggregator the fork registers.

Grid 0 runs with `allow_unsafe_jscode` off entirely, which is the point of the
feature: a grid that needed unsafe JavaScript only for its ratios no longer
needs it at all. Its cells render the value object's own `toString()`.

Grid 1 is the same grid plus the consumer's existing `JsCode` valueFormatter,
which branches on `typeof v === 'object'`. It proves formatters keep working
untouched, and it renders four-decimal text directly comparable to
`grid_ratio_js.py`.

Run standalone with:  streamlit run test/grid_ratio_builtin.py
"""

import streamlit as st

from st_aggrid import AgGrid, JsCode

from ratio_fixture import (
    COMPONENT_FIELDS,
    PIVOT_DIM,
    RATIO_SPECS,
    ROW_DIM,
    ratio_dataframe,
)

# Copied verbatim from the consumer (marketing/js_funcs.py). Unchanged on
# purpose: the claim under test is that existing formatters need no edit.
js_ratio_value_formatter = JsCode("""
function(params) {
    const v = params.value;
    if (v == null) { return ''; }
    if (typeof v === 'object') {
        return (v.value != null && !isNaN(v.value)) ? v.value.toFixed(4) : '';
    }
    return isNaN(v) ? '' : Number(v).toFixed(4);
}
""")


def ratio_column_defs(formatted: bool) -> list[dict]:
    """One colDef per spec. The ratio is declared, never scripted."""
    columns = []
    for spec in RATIO_SPECS:
        column = {
            "colId": spec.col_id,
            "field": spec.col_id,
            "headerName": spec.header,
            "type": "numericColumn",
            "aggFunc": "stRatio",
            "context": {"stRatio": spec.to_context()},
            "width": 130,
        }
        if formatted:
            column["valueFormatter"] = js_ratio_value_formatter
        columns.append(column)
    return columns


def component_column_defs() -> list[dict]:
    return [
        {"colId": name, "field": name, "aggFunc": "sum", "width": 110,
         "type": "numericColumn"}
        for name in COMPONENT_FIELDS
    ]


COMMON_OPTIONS = {
    "groupDefaultExpanded": -1,
    "suppressAggFuncInHeader": True,
    "grandTotalRow": "bottom",
    "autoGroupColumnDef": {
        "cellRendererParams": {"suppressCount": True},
        "minWidth": 140,
    },
    # Every cell in the DOM, so an assertion can read an off-screen column.
    "suppressColumnVirtualisation": True,
    "suppressRowVirtualisation": True,
}


def rowgroup_grid_options(formatted: bool) -> dict:
    return {
        **COMMON_OPTIONS,
        "groupDisplayType": "multipleColumns",
        "columnDefs": [
            {"colId": ROW_DIM, "field": ROW_DIM, "rowGroup": True, "rowGroupIndex": 0},
            {"colId": PIVOT_DIM, "field": PIVOT_DIM, "rowGroup": True, "rowGroupIndex": 1},
            *ratio_column_defs(formatted),
            *component_column_defs(),
        ],
    }


st.set_page_config(layout="wide")

df = ratio_dataframe()

st.subheader("Row grouping — no unsafe JavaScript at all")
AgGrid(
    df,
    grid_options=rowgroup_grid_options(formatted=False),
    enable_enterprise_modules=True,
    height=520,
    key="ratio_builtin_rowgroup",
)

st.subheader("Row grouping — with the consumer's existing valueFormatter")
AgGrid(
    df,
    grid_options=rowgroup_grid_options(formatted=True),
    allow_unsafe_jscode=True,
    enable_enterprise_modules=True,
    height=520,
    key="ratio_builtin_formatted",
)

# The built-in is a default, not a reservation: a caller who supplies their own
# `stRatio` keeps it. This grid returns a constant so the override is
# unmistakable on screen and in a test.
js_constant_ratio = JsCode("""
function ConstantRatio(params) {
    return 42;
}
""")

st.subheader("Row grouping — caller-supplied stRatio overrides the built-in")
AgGrid(
    df,
    grid_options={
        **rowgroup_grid_options(formatted=False),
        "aggFuncs": {"stRatio": js_constant_ratio},
    },
    allow_unsafe_jscode=True,
    enable_enterprise_modules=True,
    height=260,
    debug=True,
    key="ratio_builtin_override",
)
```

- [ ] **Step 2: Extract the DOM readers into a shared module**

`test_grid_ratio_js.py` already defines the two helpers this task's suite needs. Both suites read the same grid structure, so give them one definition rather than two copies.

Create `test/grid_dom.py`:

```python
"""Reading rendered AG-Grid cells from a Playwright page.

Row addressing goes through ``row-index``, never DOM order: AG-Grid positions
rows absolutely, so the order elements appear in the document does not track
the order they appear on screen. A probe written against DOM order produced a
false "sorting is broken" result once already.

Shared by every ratio e2e suite so the two never drift apart on what "the
grand-total row" or "row 4" means.
"""

from playwright.sync_api import Page

_READ_ROWS = """
(gridIndex) => {
  const grid = document.querySelectorAll('.ag-root-wrapper')[gridIndex];
  const rows = {};
  for (const row of grid.querySelectorAll('.ag-row')) {
    const section = row.closest('.ag-floating-bottom') ? 'bottom'
                  : row.closest('.ag-floating-top') ? 'top' : 'body';
    const key = section + ':' + row.getAttribute('row-index');
    // A row is split across pinned/centre containers; merge the fragments.
    const cells = rows[key] || (rows[key] = {});
    for (const cell of row.querySelectorAll('.ag-cell')) {
      cells[cell.getAttribute('col-id')] = cell.textContent.trim();
    }
  }
  return rows;
}
"""


def read_rows(page: Page, grid_index: int) -> dict[str, dict[str, str]]:
    """Every rendered cell of one grid, keyed ``"<section>:<row-index>"`` then
    col-id. The ratio apps suppress virtualisation, so this returns the whole
    grid rather than the visible window."""
    return page.evaluate(_READ_ROWS, grid_index)


def grand_total_row(
    rows: dict[str, dict[str, str]], group_col_id: str = "ag-Grid-AutoColumn-campaign"
) -> dict[str, str]:
    """The ``grandTotalRow: "bottom"`` row.

    AG-Grid renders it either in the pinned-bottom container or as the last
    body row depending on whether the grid is scrolled, so locate it by its
    group label rather than by a fixed key.
    """
    for cells in rows.values():
        if cells.get(group_col_id) == "Total":
            return cells
    raise AssertionError(f"no grand-total row among {sorted(rows)}")
```

Then in `test/test_grid_ratio_js.py`, delete the local `_READ_ROWS`, `read_rows` and `grand_total_row` definitions and import them instead:

```python
from grid_dom import grand_total_row, read_rows
```

Run the baseline suite to prove the extraction was behaviour-preserving:

```bash
timeout 600 .venv/bin/python -m pytest test/test_grid_ratio_js.py -q
```

Expected: 9 passed, exactly as before.

- [ ] **Step 3: Write the failing test**

Create `test/test_grid_ratio_builtin.py`:

```python
"""The built-in `stRatio` aggregator, measured against the reference arithmetic.

Where `test_grid_ratio_js.py` pins what the JavaScript *does*, this suite
asserts what the replacement *should* do: `ratio_fixture.evaluate`, at every
level, with no exemptions.

Two grids, two reading styles. Grid 0 has no valueFormatter, so its cells carry
the value object's own `toString()` — parsed back to a float, which sidesteps
the difference between JavaScript's number-to-string and Python's. Grid 1 uses
the consumer's four-decimal formatter, so its cells compare literally against
`as_text()` and line up with the JavaScript baseline's assertions.

Bulk assertions derive their expectations from `ratio_fixture`. The handful of
literal numbers are deliberate anchors: a suite that only checks grid against
`evaluate()` passes just as happily when both are wrong.
"""

from pathlib import Path

import pytest
from playwright.sync_api import Page

from e2e_utils import StreamlitRunner
from grid_dom import grand_total_row, read_rows
from ratio_fixture import RATIO_ROWS, RATIO_SPECS, as_text, evaluate, expected

ROOT_DIRECTORY = Path(__file__).parent.parent.absolute()
BUILTIN_FILE = ROOT_DIRECTORY / "test" / "grid_ratio_builtin.py"

RATIO_COL_IDS = tuple(spec.col_id for spec in RATIO_SPECS)

RAW_GRID = 0
FORMATTED_GRID = 1
OVERRIDE_GRID = 2

# Body row indices of the fully expanded row-group grids:
#   0 A            4 A/DE          8  B/US        12 B/DE row 0
#   1 A/US         5 A/DE row 0    9  B/US row 0  13 B/DE row 1
#   2 A/US row 0   6 A/DE row 1    10 B/US row 1
#   3 A/US row 1   7 B            11 B/DE
# The grand total follows; find it with `grand_total_row`.
GROUP_ROW_DIMS = {
    0: {"campaign": "A"},
    1: {"campaign": "A", "country": "US"},
    4: {"campaign": "A", "country": "DE"},
    7: {"campaign": "B"},
    8: {"campaign": "B", "country": "US"},
    11: {"campaign": "B", "country": "DE"},
}
LEAF_ROW_SOURCE = {2: 0, 3: 1, 5: 2, 6: 3, 9: 4, 10: 5, 12: 6, 13: 7}

def assert_number(text: str, reference: float | None, where: str) -> None:
    """Compare an unformatted cell against a reference number."""
    if reference is None:
        assert text == "", f"{where}: expected an empty cell, got {text!r}"
    else:
        assert text != "", f"{where}: expected {reference}, got an empty cell"
        assert float(text) == pytest.approx(reference), where


@pytest.fixture(autouse=True, scope="module")
def streamlit_app():
    with StreamlitRunner(BUILTIN_FILE) as runner:
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
    page.wait_for_selector('[row-index="14"]', timeout=60000)


def test_group_rows_are_the_sum_ratio_at_both_levels(page: Page):
    rows = read_rows(page, RAW_GRID)

    for row_index, dims in GROUP_ROW_DIMS.items():
        cells = rows[f"body:{row_index}"]
        for col_id in RATIO_COL_IDS:
            assert_number(
                cells[col_id], expected(col_id, **dims), f"row {row_index} {dims} {col_id}"
            )


def test_grand_total_row_is_the_sum_ratio(page: Page):
    cells = grand_total_row(read_rows(page, RAW_GRID))

    for col_id in RATIO_COL_IDS:
        assert_number(cells[col_id], expected(col_id), f"total {col_id}")


def test_leaf_rows_still_show_the_per_row_ratio(page: Page):
    rows = read_rows(page, RAW_GRID)

    for row_index, source_index in LEAF_ROW_SOURCE.items():
        source_row = RATIO_ROWS[source_index]
        cells = rows[f"body:{row_index}"]
        for spec in RATIO_SPECS:
            assert_number(
                cells[spec.col_id],
                evaluate(spec, [source_row]),
                f"leaf {row_index} {spec.col_id}",
            )


def test_signed_numerator_subtracts_its_negative_term(page: Page):
    """The gap the flat `{num, num2, den}` shape could not express. The
    JavaScript baseline reads 11.2000 here."""
    rows = read_rows(page, RAW_GRID)

    assert float(rows["body:0"]["net_cpi"]) == pytest.approx(8.8)
    assert float(rows["body:1"]["net_cpi"]) == pytest.approx(79.0)
    assert float(grand_total_row(rows)["net_cpi"]) == pytest.approx(2.99)


def test_multiplier_and_scale_are_applied(page: Page):
    rows = read_rows(page, RAW_GRID)

    assert float(rows["body:0"]["cpm"]) == pytest.approx(1000 / 30000 * 1000)
    assert float(rows["body:0"]["sess_min"]) == pytest.approx(0.8)


def test_a_collapsed_denominator_uses_fill_null(page: Page):
    """Campaign B has no payers at all. The explicit `fill_null=0.0` column
    renders a zero; the column that leaves `fill_null` at its default renders
    an empty cell, which is what the JavaScript renders today."""
    rows = read_rows(page, RAW_GRID)

    assert float(rows["body:7"]["arpp"]) == pytest.approx(0.0)
    assert float(rows["body:8"]["arpp"]) == pytest.approx(0.0)
    assert rows["body:7"]["arpp_blank"] == ""
    assert rows["body:8"]["arpp_blank"] == ""


def test_group_values_are_not_the_average_of_their_children(page: Page):
    """Campaign A's children are 90.0000 and 1.1111; their average is 45.5556
    and the correct rollup is 10.0000. The fixture separates the two at every
    level so this cannot pass by coincidence."""
    rows = read_rows(page, RAW_GRID)

    assert float(rows["body:0"]["cpi"]) == pytest.approx(10.0)
    assert float(rows["body:1"]["cpi"]) == pytest.approx(90.0)
    assert float(rows["body:4"]["cpi"]) == pytest.approx(1.1111, rel=1e-4)


def test_existing_value_formatters_keep_working_unchanged(page: Page):
    """The consumer's formatter branches on `typeof v === 'object'` and reads
    `v.value`. It was copied over with no edit; every cell must render."""
    rows = read_rows(page, FORMATTED_GRID)

    for row_index, dims in GROUP_ROW_DIMS.items():
        cells = rows[f"body:{row_index}"]
        for col_id in RATIO_COL_IDS:
            assert cells[col_id] == as_text(expected(col_id, **dims)), (
                f"row {row_index} {dims} {col_id}"
            )

    total = grand_total_row(rows)
    assert total["cpi"] == "3.4000"
    assert total["net_cpi"] == "2.9900"


def test_the_unformatted_grid_needs_no_unsafe_jscode(page: Page):
    """Grid 0 is built without `allow_unsafe_jscode`. If the ratio still
    renders, no JavaScript crossed the boundary to produce it."""
    rows = read_rows(page, RAW_GRID)

    assert rows["body:0"]["cpi"] != ""
    assert float(rows["body:0"]["cpi"]) == pytest.approx(10.0)


def test_a_caller_supplied_aggfunc_of_the_same_name_wins(page: Page):
    """The built-in is a default, not a reservation. Grid 2 registers its own
    `stRatio` returning a constant; every group row must show it."""
    rows = read_rows(page, OVERRIDE_GRID)

    assert rows["body:0"]["cpi"] == "42"
    assert rows["body:1"]["cpi"] == "42"
    assert rows["body:0"]["net_cpi"] == "42"
    # Leaf rows read the dataframe, so the override touches group rows only.
    assert float(rows["body:2"]["cpi"]) == pytest.approx(400.0)
```

- [ ] **Step 4: Run the test to verify it fails**

```bash
timeout 600 .venv/bin/python -m pytest test/test_grid_ratio_builtin.py -q
```

Expected: FAIL. `stRatio` is not a registered aggregator, so AG-Grid produces no value and the ratio cells are empty — `assert_number` reports "expected 10.0, got an empty cell".

- [ ] **Step 5: Write the aggregator**

Create `st_aggrid/frontend/src/aggFuncs/stRatio.ts`:

```ts
import type { ColDef, GridOptions, IAggFuncParams } from "ag-grid-community"

/** Name callers reference from `colDef.aggFunc`, and the key their parameters
 * are nested under inside `colDef.context` so they cannot collide with other
 * uses of that field. */
export const ST_RATIO = "stRatio"

export interface StRatioConfig {
  num: string[]
  den: string[]
  num_signs?: number[]
  multiplier?: number
  scale?: number
  /** Value when the denominator sums to zero. Defaults to null — an empty
   * cell — which is what the JavaScript this replaces already renders. */
  fill_null?: number | null
}

/**
 * AG-Grid 36's `IAggFuncResult` shape. `toNumber` is what the framework calls
 * for sorting, for `RowNode.getValue`, and when unwrapping the value for
 * export and charts, so it is the hook that matters — `valueOf` is not on any
 * of those paths.
 */
export interface StRatioValue {
  value: number | null
  /** Component sums for this node's subtree. Carried so a parent group can
   * fold its children instead of rescanning leaves; mechanism, not API. */
  sums: Record<string, number>
  toNumber(): number | null
  toString(): string
}

function asNumber(raw: unknown): number {
  const parsed = Number(raw)
  return Number.isFinite(parsed) ? parsed : 0
}

export function readStRatioConfig(colDef?: ColDef | null): StRatioConfig | null {
  const config = (colDef?.context as Record<string, unknown> | undefined)?.[ST_RATIO]
  if (!config || typeof config !== "object") return null
  const candidate = config as StRatioConfig
  if (!Array.isArray(candidate.num) || !Array.isArray(candidate.den)) return null
  return candidate
}

/**
 * `(Σ signᵢ·numᵢ · multiplier / Σden) · scale`, where every field name resolves
 * to the sum of that field over the node's subtree.
 *
 * Each node is visited once. A leaf group's `aggregatedChildren` are data rows,
 * so their components are read straight off `row.data`; a higher group's
 * children are groups, so their already-computed `sums` are folded instead.
 * Re-walking `allLeafChildren` at every level would be correct but quadratic in
 * depth — and, being blind to pivot keys, wrong in a pivot cell.
 */
export function stRatioAggFunc(params: IAggFuncParams): StRatioValue | null {
  const config = readStRatioConfig(params.colDef)
  if (!config) return null

  const fields = [...config.num, ...config.den]
  const sums: Record<string, number> = {}
  for (const field of fields) sums[field] = 0

  const colId = params.column.getColId()

  for (const child of params.aggregatedChildren ?? []) {
    if (child.data) {
      for (const field of fields) sums[field] += asNumber(child.data[field])
    } else {
      const stored = (child.aggData ?? {})[colId] as StRatioValue | undefined
      if (stored?.sums) {
        for (const field of fields) sums[field] += asNumber(stored.sums[field])
      }
    }
  }

  const signs = config.num_signs ?? config.num.map(() => 1)
  let numerator = 0
  for (let i = 0; i < config.num.length; i++) {
    numerator += signs[i] * sums[config.num[i]]
  }

  let denominator = 0
  for (const field of config.den) denominator += sums[field]

  const multiplier = config.multiplier ?? 1
  const scale = config.scale ?? 1
  // `?? null` and not `|| null`: an explicit fill_null of 0 must survive.
  const fillNull = config.fill_null ?? null

  const value =
    denominator !== 0
      ? ((numerator * multiplier) / denominator) * scale
      : fillNull

  return {
    value,
    sums,
    toNumber: () => value,
    toString: () => (value == null ? "" : String(value)),
  }
}

/**
 * Merge the built-in aggregator into `gridOptions.aggFuncs`.
 *
 * A caller-supplied entry of the same name wins: the built-in is a default,
 * not a reservation. The override is logged under `debug` because a silently
 * shadowed aggregator would be baffling to track down.
 */
export function registerStRatio(
  gridOptions: GridOptions,
  debug: boolean = false
): GridOptions {
  const supplied = gridOptions.aggFuncs ?? {}

  if (ST_RATIO in supplied) {
    if (debug) {
      console.log(
        `[st_aggrid] gridOptions.aggFuncs["${ST_RATIO}"] was supplied by the ` +
          `caller and overrides the built-in ratio aggregator.`
      )
    }
  } else {
    gridOptions.aggFuncs = { ...supplied, [ST_RATIO]: stRatioAggFunc }
  }

  return gridOptions
}
```

- [ ] **Step 6: Register it from `parseGridOptions`**

`parseGridOptions` is the single funnel every `gridOptions` object passes through — both the mount-time memo and the live `updateGridOptions` path — so registering there covers both without touching `AgGridComponent.tsx`.

In `st_aggrid/frontend/src/utils/parsers.ts`, add the import beside the existing ones:

```ts
import { registerStRatio } from "../aggFuncs/stRatio"
```

and insert the call after the `columnTypes` merge, before the theme block:

```ts
  // Built-in aggregators. A caller-supplied `aggFuncs` entry of the same name
  // wins — see registerStRatio.
  registerStRatio(gridOptions, data.debug === true)
```

`gridOptions` is already a `cloneDeep` of the incoming payload at this point, so mutating it is safe.

- [ ] **Step 7: Rebuild the frontend**

```bash
cd st_aggrid/frontend && COREPACK_ENABLE_DOWNLOAD_PROMPT=0 corepack yarn build
```

Expected: `tsc` clean, then `vite build` writes exactly one `index-<hash>.js` and one `index-<hash>.css` into `build/`. Confirm with `ls st_aggrid/frontend/build/` — two files, no more.

- [ ] **Step 8: Run the test to verify it passes**

```bash
timeout 600 .venv/bin/python -m pytest test/test_grid_ratio_builtin.py -q
```

Expected: PASS. If ratio cells are still empty, check the browser console via a temporary `page.on("console", print)` — a thrown error inside an aggFunc surfaces there, not in the test output.

- [ ] **Step 9: Verify the JavaScript baseline still passes**

```bash
timeout 600 .venv/bin/python -m pytest test/test_grid_ratio_js.py -q
```

Expected: PASS, unchanged. Registering a new aggregator must not disturb a grid that supplies its own.

- [ ] **Step 10: Commit**

```bash
git add st_aggrid/frontend/src/aggFuncs/stRatio.ts \
        st_aggrid/frontend/src/utils/parsers.ts \
        st_aggrid/frontend/build \
        test/grid_dom.py test/test_grid_ratio_js.py \
        test/grid_ratio_builtin.py test/test_grid_ratio_builtin.py
git commit -m "Add the built-in stRatio aggregator for row-grouped ratios"
```

---

### Task 3: Pivot support

One line of the aggregator changes. In pivot mode the value is produced for a *pivot result* column, and a child group stores its own aggregation under that column's id — not the source column's — so folding through the source id finds nothing and every ratio collapses to `fill_null`.

**Files:**
- Modify: `st_aggrid/frontend/src/aggFuncs/stRatio.ts` (the `colId` line)
- Modify: `test/grid_ratio_builtin.py` (append the pivot grid)
- Modify: `test/test_grid_ratio_builtin.py` (pivot assertions)
- Rebuild: `st_aggrid/frontend/build/`

**Interfaces:**
- Consumes: everything from Task 2.
- Produces: no new exports. `stRatioAggFunc` becomes pivot-correct.

- [ ] **Step 1: Add the pivot grid to the app**

Append to `test/grid_ratio_builtin.py`:

```python
def pivot_grid_options() -> dict:
    """Campaign down the rows, country across the columns, with pivot row
    totals and a grand-total row — the shape the consumer's marketing
    dashboard runs."""
    return {
        **COMMON_OPTIONS,
        "pivotMode": True,
        "groupDisplayType": "multipleColumns",
        "pivotRowTotals": "after",
        "columnDefs": [
            {"colId": ROW_DIM, "field": ROW_DIM, "rowGroup": True, "rowGroupIndex": 0},
            {"colId": PIVOT_DIM, "field": PIVOT_DIM, "pivot": True, "pivotIndex": 0},
            *ratio_column_defs(formatted=False),
            *component_column_defs(),
        ],
    }


st.subheader("Pivot — campaign down, country across")
AgGrid(
    df,
    grid_options=pivot_grid_options(),
    enable_enterprise_modules=True,
    height=320,
    key="ratio_builtin_pivot",
)
```

- [ ] **Step 2: Write the failing test**

Append to `test/test_grid_ratio_builtin.py`:

```python
# --------------------------------------------------------------------------
# Pivot
# --------------------------------------------------------------------------

PIVOT_GRID = 3


def pivot_col(country: str, col_id: str) -> str:
    return f"pivot_country_{country}_{col_id}"


def pivot_total_col(col_id: str) -> str:
    return f"PivotRowTotal_pivot_country__{col_id}"


def test_pivot_cells_are_split_by_the_pivot_key(page: Page):
    """The defect that motivates the feature. The JavaScript shows the row's
    total in both country columns; each cell must show its own ratio."""
    rows = read_rows(page, PIVOT_GRID)
    campaign_a = rows["body:0"]

    for country in ("US", "DE"):
        for col_id in RATIO_COL_IDS:
            assert_number(
                campaign_a[pivot_col(country, col_id)],
                expected(col_id, campaign="A", country=country),
                f"A/{country} {col_id}",
            )

    assert float(campaign_a[pivot_col("US", "cpi")]) == pytest.approx(90.0)
    assert float(campaign_a[pivot_col("DE", "cpi")]) == pytest.approx(1.1111, rel=1e-4)


def test_pivot_row_totals_are_the_ratio_across_all_pivot_keys(page: Page):
    rows = read_rows(page, PIVOT_GRID)

    for row_index, campaign in ((0, "A"), (1, "B")):
        for col_id in RATIO_COL_IDS:
            assert_number(
                rows[f"body:{row_index}"][pivot_total_col(col_id)],
                expected(col_id, campaign=campaign),
                f"{campaign} row total {col_id}",
            )


def test_pivot_grand_total_row_is_split_by_the_pivot_key(page: Page):
    """One level up: each country column of the total row carries that
    country's ratio, and the row total carries the overall one."""
    rows = read_rows(page, PIVOT_GRID)
    total = rows["body:2"]

    for country in ("US", "DE"):
        for col_id in RATIO_COL_IDS:
            assert_number(
                total[pivot_col(country, col_id)],
                expected(col_id, country=country),
                f"total/{country} {col_id}",
            )

    assert float(total[pivot_col("US", "cpi")]) == pytest.approx(8.2727, rel=1e-4)
    assert float(total[pivot_col("DE", "cpi")]) == pytest.approx(0.5789, rel=1e-4)
    assert float(total[pivot_total_col("cpi")]) == pytest.approx(3.4)
```

Also widen the readiness wait in `go_to_app` from `>= 3` to `>= 4`:

```python
    page.wait_for_function(
        "() => document.querySelectorAll('.ag-root-wrapper').length >= 4",
        timeout=60000,
    )
```

- [ ] **Step 3: Run the test to verify it fails**

```bash
timeout 600 .venv/bin/python -m pytest test/test_grid_ratio_builtin.py -q -k pivot
```

Expected: FAIL — and specifically on the total row.

The campaign rows already pass: their `aggregatedChildren` are data rows, read straight off `row.data`, and `aggregatedChildren` is already filtered to the pivot key. The total row's children are campaign *groups*, so it folds stored sums through `params.column.getColId()` — the source column's id, `"cpi"` — while each child actually stored its aggregation under the pivot result column's id, `"pivot_country_US_cpi"`. The lookup finds nothing, every sum stays `0`, and the cell falls to `fill_null`: empty for most columns, `0.0000` for the one that sets `fill_null=0.0`. The pivot row-total cell of that row fails the same way, under `"PivotRowTotal_pivot_country__cpi"`.

- [ ] **Step 4: Resolve the pivot result column**

In `stRatioAggFunc`, replace:

```ts
  const colId = params.column.getColId()
```

with:

```ts
  // In pivot mode the value is produced for a pivot result column, and a child
  // group stores its aggregation under *that* column's id. Folding through the
  // source column's id would find nothing and collapse every group to
  // fill_null. `aggregatedChildren` is already filtered to the pivot key, so
  // the two compose: each child contributes only its own cell's components.
  const colId = (params.pivotResultColumn ?? params.column).getColId()
```

- [ ] **Step 5: Rebuild and run the test to verify it passes**

```bash
cd st_aggrid/frontend && COREPACK_ENABLE_DOWNLOAD_PROMPT=0 corepack yarn build
cd ../.. && timeout 600 .venv/bin/python -m pytest test/test_grid_ratio_builtin.py -q
```

Expected: PASS, all of them — the row-grouping tests from Task 2 included.

- [ ] **Step 6: Commit**

```bash
git add st_aggrid/frontend/src/aggFuncs/stRatio.ts st_aggrid/frontend/build \
        test/grid_ratio_builtin.py test/test_grid_ratio_builtin.py
git commit -m "Make stRatio pivot-aware via pivotResultColumn"
```

---

### Task 4: Sorting — `toNumber()` and nulls last in both directions

`toNumber()` already ships from Task 2, so numeric sorting works. What is missing is null placement: AG-Grid's native handling puts nulls first ascending, and this feature puts them last in both directions. That needs a comparator, which the fork installs itself so no application ever writes one.

**Files:**
- Modify: `st_aggrid/frontend/src/aggFuncs/stRatio.ts` (add `stRatioComparator`, install it in `registerStRatio`)
- Modify: `test/test_grid_ratio_builtin.py` (sort assertions)
- Rebuild: `st_aggrid/frontend/build/`

**Interfaces:**
- Consumes: `StRatioValue` from Task 2.
- Produces: `stRatioComparator(a: unknown, b: unknown, nodeA: IRowNode, nodeB: IRowNode, isDescending: boolean): number`.

- [ ] **Step 1: Write the failing test**

Append to `test/test_grid_ratio_builtin.py`:

```python
# --------------------------------------------------------------------------
# Sorting
# --------------------------------------------------------------------------


def campaign_order(page: Page, grid_index: int) -> list[str]:
    """Group labels top to bottom, read by row-index. The grand-total row is
    dropped — it stays put regardless of sort."""
    rows = read_rows(page, grid_index)
    ordered = sorted(
        ((key, cells) for key, cells in rows.items() if key.startswith("body:")),
        key=lambda item: int(item[0].split(":")[1]),
    )
    labels = [cells.get("ag-Grid-AutoColumn-campaign", "") for _, cells in ordered]
    return [label for label in labels if label in ("A", "B")]


def click_header(page: Page, grid_index: int, col_id: str, expect_sort: str) -> None:
    """Click a header and wait for AG-Grid to report the new direction.

    Waiting on `aria-sort` rather than on a timeout matters here: several of
    these assertions expect an order that is also the *unsorted* order, so a
    click that silently failed to register would let the test pass without
    sorting anything.
    """
    grid = page.locator(".ag-root-wrapper").nth(grid_index)
    header = grid.locator(f'.ag-header-cell[col-id="{col_id}"]')
    header.click()
    page.wait_for_function(
        """([gridIndex, colId, direction]) => {
             const grid = document.querySelectorAll('.ag-root-wrapper')[gridIndex];
             const cell = grid.querySelector(`.ag-header-cell[col-id="${colId}"]`);
             return cell && cell.getAttribute('aria-sort') === direction;
           }""",
        [grid_index, col_id, expect_sort],
        timeout=10000,
    )


def test_sorting_a_ratio_column_orders_by_its_number(page: Page):
    """Campaign A is 10.0000 and campaign B is 0.1000. Proves `toNumber()` is
    reached — an object with no numeric hook would not reorder at all."""
    assert campaign_order(page, RAW_GRID) == ["A", "B"]

    click_header(page, RAW_GRID, "cpi", "ascending")
    assert campaign_order(page, RAW_GRID) == ["B", "A"]

    click_header(page, RAW_GRID, "cpi", "descending")
    assert campaign_order(page, RAW_GRID) == ["A", "B"]


def test_nulls_sort_last_in_both_directions(page: Page):
    """`arpp_blank` is 12.6667 for campaign A and empty for campaign B.

    Ascending is the discriminating direction: AG-Grid's native handling puts
    the empty row first, giving ["B", "A"]. Descending agrees with native, and
    is asserted so a regression that drops the comparator entirely still shows
    up as a diff in exactly one of the two.
    """
    click_header(page, RAW_GRID, "arpp_blank", "ascending")
    assert campaign_order(page, RAW_GRID) == ["A", "B"], "ascending: nulls last"

    click_header(page, RAW_GRID, "arpp_blank", "descending")
    assert campaign_order(page, RAW_GRID) == ["A", "B"], "descending: nulls last"


def test_a_caller_supplied_comparator_is_left_alone(page: Page):
    """Grid 1 declares its own comparator on `cpi`, which orders backwards.
    Both directions are the opposite of what the fork's comparator produces,
    so this cannot pass if the fork overwrote it."""
    click_header(page, FORMATTED_GRID, "cpi", "ascending")
    assert campaign_order(page, FORMATTED_GRID) == ["A", "B"]

    click_header(page, FORMATTED_GRID, "cpi", "descending")
    assert campaign_order(page, FORMATTED_GRID) == ["B", "A"]
```

Give grid 1 a comparator so the last test has something to check. In `test/grid_ratio_builtin.py`, extend `ratio_column_defs`:

```python
# A deliberately backwards comparator, only on the formatted grid's `cpi`. It
# exists so a test can prove the fork leaves a caller-supplied comparator
# alone; the fork's own comparator would sort the other way.
js_reversed_comparator = JsCode("""
function(a, b) {
    const x = (a && typeof a.toNumber === 'function') ? a.toNumber() : a;
    const y = (b && typeof b.toNumber === 'function') ? b.toNumber() : b;
    if (x == null || y == null) { return 0; }
    return x > y ? -1 : (x < y ? 1 : 0);
}
""")
```

and inside the loop, after the `formatted` branch:

```python
        if formatted and spec.col_id == "cpi":
            column["comparator"] = js_reversed_comparator
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
timeout 600 .venv/bin/python -m pytest test/test_grid_ratio_builtin.py -q -k "sort or null or comparator"
```

Expected: `test_nulls_sort_last_in_both_directions` FAILS — ascending gives `["B", "A"]`, AG-Grid's native nulls-first. The other two pass already.

- [ ] **Step 3: Write the comparator**

Add to `st_aggrid/frontend/src/aggFuncs/stRatio.ts`, after `stRatioAggFunc`:

```ts
/** The number a value sorts by: the aggregation's `toNumber()` on a group row,
 * the raw cell value on a leaf. Anything non-finite — including the NaN a
 * dataframe carries for a missing precomputed ratio — sorts as absent. */
function sortValue(raw: unknown): number | null {
  const unwrapped =
    raw && typeof (raw as StRatioValue).toNumber === "function"
      ? (raw as StRatioValue).toNumber()
      : raw
  return typeof unwrapped === "number" && Number.isFinite(unwrapped)
    ? unwrapped
    : null
}

/**
 * Orders ratio values numerically and puts empty cells last in **both**
 * directions.
 *
 * AG-Grid negates a comparator's result for a descending sort, so "last in
 * both directions" cannot be expressed by the return value alone — the null
 * branch reads `isDescending` and flips to compensate.
 */
export function stRatioComparator(
  a: unknown,
  b: unknown,
  _nodeA: unknown,
  _nodeB: unknown,
  isDescending: boolean
): number {
  const left = sortValue(a)
  const right = sortValue(b)

  if (left === null && right === null) return 0
  if (left === null) return isDescending ? -1 : 1
  if (right === null) return isDescending ? 1 : -1

  return left > right ? 1 : left < right ? -1 : 0
}
```

- [ ] **Step 4: Install it during registration**

Widen the type import at the top of `stRatio.ts` — `ColGroupDef` is new:

```ts
import type {
  ColDef,
  ColGroupDef,
  GridOptions,
  IAggFuncParams,
} from "ag-grid-community"
```

Add the colDef walk above `registerStRatio`:

```ts
/** Visit every leaf colDef, descending into column groups. A walk that stopped
 * at the top level would miss every column on a grouped grid — and the
 * consumer wraps all of its metric columns in groups. */
function eachColDef(
  defs: (ColDef | ColGroupDef)[] | null | undefined,
  visit: (def: ColDef) => void
): void {
  for (const def of defs ?? []) {
    const children = (def as ColGroupDef).children
    if (children) eachColDef(children, visit)
    else visit(def as ColDef)
  }
}
```

Then, in `registerStRatio`, before `return gridOptions`:

```ts
  // A ratio column's value is an object, so the default comparator would need
  // `toNumber` unwrapping *and* would place empty cells first ascending. Both
  // are handled here rather than by every application. A caller who supplied a
  // comparator meant it, so theirs is left alone.
  eachColDef(gridOptions.columnDefs, (def) => {
    if (def.aggFunc === ST_RATIO && !def.comparator) {
      def.comparator = stRatioComparator
    }
  })
```

- [ ] **Step 5: Rebuild and run the tests to verify they pass**

```bash
cd st_aggrid/frontend && COREPACK_ENABLE_DOWNLOAD_PROMPT=0 corepack yarn build
cd ../.. && timeout 600 .venv/bin/python -m pytest test/test_grid_ratio_builtin.py -q
```

Expected: PASS, all of them.

- [ ] **Step 6: Run every ratio suite plus the fast loop**

```bash
.venv/bin/python -m pytest -m "not e2e" -q
timeout 900 .venv/bin/python -m pytest test/test_grid_ratio_js.py test/test_grid_ratio_builtin.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add st_aggrid/frontend/src/aggFuncs/stRatio.ts st_aggrid/frontend/build \
        test/grid_ratio_builtin.py test/test_grid_ratio_builtin.py
git commit -m "Sort stRatio columns numerically with empty cells last"
```

---

### Task 5: Regression sweep and documentation

The aggregator now touches every grid through `parseGridOptions`. Prove it changed nothing else, then write down what a caller has to know.

**Files:**
- Modify: `README.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Run the full browser suite**

```bash
timeout 3600 .venv/bin/python -m pytest -q
```

Expected: PASS. This excludes the 1M-row performance suite (`addopts = -m 'not slow'`). Every grid in the repo now goes through `registerStRatio`; a failure here means the registration disturbed something it should not have.

- [ ] **Step 2: Confirm the build is exactly two files**

```bash
ls st_aggrid/frontend/build/
git status --short st_aggrid/frontend/build/
```

Expected: one `index-<hash>.js`, one `index-<hash>.css`. Each glob in `st_aggrid/component.py` must match exactly one file, and `git status` shows a delete plus an add because filenames are content-hashed.

- [ ] **Step 3: Document the feature in `README.md`**

Add a section (place it beside the other feature sections):

````markdown
### Ratio aggregation without JavaScript

A ratio cannot be rolled up by rolling up the ratio: a group's value is
`Σnumerator / Σdenominator`, never the average of its children's ratios. The
built-in `stRatio` aggregator computes that from a declaration, so a grid that
needed `allow_unsafe_jscode` only for its ratio columns no longer needs it.

```python
{
    "colId": "cpi",
    "aggFunc": "stRatio",
    "context": {"stRatio": {"num": ["cost"], "den": ["installs"]}},
}
```

| Key | Required | Default | Meaning |
|---|---|---|---|
| `num` | yes | — | Field names summed to form the numerator |
| `den` | yes | — | Field names summed to form the denominator |
| `num_signs` | no | all `1` | Per-term signs, e.g. `[1, -1]` for `(a − b)/c` |
| `multiplier` | no | `1.0` | Applied inside the numerator (CPM uses `1000`) |
| `scale` | no | `1.0` | Applied to the final value (sec→min uses `1/60`) |
| `fill_null` | no | `None` | Value when `Σden == 0`; `None` renders an empty cell |

The value is `((Σ signᵢ·numᵢ) · multiplier / Σden) · scale`, where each field
name resolves to the sum of that field over the node's subtree. It is correct at
every grouping level, in pivot cells, in pivot row totals and in total rows.

Field names are read from the **row data**, so a component needs no column of
its own — but it must be in the DataFrame. A name that is not raises a
`ValueError` when the grid is built, because a missing component would
otherwise contribute `0` and skew the ratio silently.

Ratio columns sort numerically, with empty cells last in both directions. A
`comparator` you set yourself is left alone. Supplying your own
`aggFuncs["stRatio"]` overrides the built-in; run with `debug=True` to see that
logged.

Working examples: `test/grid_ratio_builtin.py` (built-in) and
`test/grid_ratio_js.py` (the JavaScript approach it replaces), both over the
same fixture in `test/ratio_fixture.py`.
````

- [ ] **Step 4: Note it in `CLAUDE.md`**

Under **Architecture**, extend the source tree listing:

```
    │   ├── aggFuncs/stRatio.ts        # Built-in ratio aggregator + comparator
```

and add to the same file's `st_aggrid/` listing:

```
├── ratio.py                 # Validation for stRatio column declarations
```

Then add a bullet under **Key Design Decisions**:

```markdown
- **Built-in `stRatio` aggregator**: `Σnum/Σden` rollups declared as data in
  `colDef.context["stRatio"]`, registered from `parseGridOptions` so both the
  mount and the live-update paths get it. Correct under row grouping and pivot;
  the value object implements AG-Grid 36's `IAggFuncResult` (`toNumber`, not
  `valueOf` — `valueOf` leaves a column containing a null unsorted). Python
  validates the declaration against the DataFrame, never against `columnDefs`.
```

And under **Conventions**, after the tests bullet:

```markdown
- Ratio tests never hand-type an expected number: `test/ratio_fixture.py` owns
  the data and the arithmetic, and declares the nodes it cannot discriminate.
```

- [ ] **Step 5: Commit**

```bash
git add README.md CLAUDE.md
git commit -m "Document the stRatio declarative ratio aggregator"
```

---

## Follow-up: consumer migration (separate repository)

Not part of this plan's tasks — `hitapps_analytics` is a different repo — but the work this feature exists for, recorded so it is not lost. Do it only after the tasks above are merged.

1. Rewrite `MetricSpec.to_agg_context()` (`web_app/src/bi_core/charts/metric_spec.py`) to emit the declarative shape: `num`/`den` as lists, `num_signs` passed through, `fill_null` passed through **explicitly** — the two defaults differ (`MetricSpec` says `0.0`, `stRatio` says `None`), so relying on either would change what renders. Delete the docstring's `len(num) <= 2 and num_signs all positive` restriction; it no longer applies.
2. Point ratio columns at `aggFunc="stRatio"` in `marketing/grid_builder.py` and `ad_placements/grid_builder.py`, and nest the payload under `context["stRatio"]` in `configure_metric_column`.
3. Delete `js_ratio_sum` and its `aggFuncs` registration. `js_growth_ratio` stays — `growthRatio` is a ratio of two ratios and out of scope.
4. Drop `allow_unsafe_jscode` only from grids that no longer pass any `JsCode`. Value formatters and `cellStyle` are still `JsCode`, so most grids keep the flag; check before removing.
5. **Expect pivot numbers to change, and check them.** Every pivot cell in those dashboards currently shows its row's total rather than the cell's own ratio — measured, not suspected. The migration fixes that, which means users will see different numbers in pivot cells. Row-grouping values, pivot row totals and grand totals are unchanged.
6. **Expect signed-numerator columns to change.** Any spec with `num_signs` containing `-1` currently rolls up as if every term were added. Those group values will move.
7. `funnel_saj` keeps `ratioAgg` and its valueGetter machinery — out of scope.
