# Declarative Colour Scales Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a grid paint a column's cells as a heat map from a declaration in `colDef.context["stColorScale"]`, with no `JsCode`, replacing the five hand-written cell stylers in the consumer.

**Architecture:** A declaration in `context` — grid-level defaults, per-column opt-in — resolved in the browser, exactly mirroring how the built-in aggregators read `context["stRatio"]`. `parseGridOptions` attaches one built-in `cellStyle` to every declared column; that function reads the live declaration on each call, pulls a memoised per-column-per-group-level statistic, and returns an `rgba` background. Python's job is validation only.

**Tech Stack:** Python 3 (hatchling, pytest), TypeScript + React (Vite, Yarn 4 via corepack), AG-Grid 36.0.0, Playwright for e2e.

**Spec:** `docs/superpowers/specs/2026-08-29-grid-color-scale-design.md`

## Global Constraints

- **Context key:** `stColorScale`, at `gridOptions["context"]` (defaults only) and `colDef["context"]` (opt-in). A column paints only when its own colDef carries an entry that is not `False`.
- **Schemes:** exactly `"neutral"`, `"positive"`, `"diverging"`. **Modes:** exactly `"minmax"`, `"zscore"`.
- **Declaration keys in v1:** `scheme`, `mode`, `skip_non_positive`. Nothing else. `reverse` is phase 2 and must be **rejected** by validation.
- **Gate constants:** `CV_FLOOR = 0.001`, `Z_DEAD = 0.5`, `Z_CAP = 3`. Standard deviation is the **population** one (divisor `N`).
- **Rounding, both languages:** `floor(x + 0.5)`. Never Python's built-in `round` (half-to-even) — it disagrees with JavaScript's `Math.round` on a `.5` and the fixture must match the frontend exactly. Alpha is emitted rounded to 3 decimals as `floor(alpha * 1000 + 0.5) / 1000`.
- **The fill is always `rgba(...)`** over the cell's own background. Never an opaque colour: an opaque ramp paints a light cell under the dark theme's light text and the number disappears.
- **No AG-Grid version bump.** Stay on `36.0.0`.
- **`yarn` is not on PATH.** Always `corepack yarn …`, with `COREPACK_ENABLE_DOWNLOAD_PROMPT=0`.
- **e2e row addressing goes through `row-index` / `col-id` attributes**, never DOM order — AG-Grid positions rows absolutely.
- Run the fast loop with `pytest -m "not e2e"`; `test/conftest.py` auto-marks everything outside `test/unit/` as `e2e`.

---

### Task 1: Shared colDef walk

`ratio.py` owns a depth-first colDef walk and an error-label helper that the new
validator needs verbatim. Extract them before writing the second caller, so
there is never a second hand-written copy.

**Files:**
- Create: `st_aggrid/_coldefs.py`
- Modify: `st_aggrid/ratio.py` (delete `_iter_column_defs` and `_label`, import the new names, update 5 call sites)
- Test: `test/unit/test_coldefs.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `st_aggrid._coldefs.iter_column_defs(column_defs: Any) -> Iterator[dict]` and `st_aggrid._coldefs.label(column: dict) -> str`.

- [ ] **Step 1: Write the failing test**

Create `test/unit/test_coldefs.py`:

```python
"""The colDef walk shared by the built-in validators.

Both `ratio.py` and `color_scale.py` must see every column on a grouped grid;
a walk that stopped at the top level would cover nothing there, and the
consumer this feature exists for wraps all of its metric columns in groups.
"""

from st_aggrid._coldefs import iter_column_defs, label


def test_walk_yields_leaf_columns():
    defs = [{"field": "a"}, {"field": "b"}]
    assert [c["field"] for c in iter_column_defs(defs)] == ["a", "b"]


def test_walk_descends_into_column_groups():
    defs = [{"headerName": "G", "children": [{"field": "a"}, {"field": "b"}]}]
    # The group itself is yielded too — a declaration on a group colDef is
    # malformed rather than invisible, and the validators must be able to say so.
    assert [c.get("field") for c in iter_column_defs(defs)] == [None, "a", "b"]


def test_walk_nests_arbitrarily_deep():
    defs = [{"children": [{"children": [{"field": "deep"}]}]}]
    assert [c.get("field") for c in iter_column_defs(defs)] == [None, None, "deep"]


def test_walk_tolerates_a_non_list_and_non_dict_entries():
    assert list(iter_column_defs(None)) == []
    assert list(iter_column_defs("columnDefs")) == []
    assert [c["field"] for c in iter_column_defs([None, 7, {"field": "a"}])] == ["a"]


def test_label_prefers_col_id_then_field():
    assert label({"colId": "cpi", "field": "cost"}) == "column 'cpi'"
    assert label({"field": "cost"}) == "column 'cost'"
    assert label({}) == "unnamed aggregation column"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest test/unit/test_coldefs.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'st_aggrid._coldefs'`

- [ ] **Step 3: Create the module**

Create `st_aggrid/_coldefs.py`:

```python
"""Walking a ``columnDefs`` tree, shared by the built-in validators.

``ratio.py`` and ``color_scale.py`` both need every leaf and group colDef, and
both name a column the same way in their error messages. A walk that stopped
at the top level would cover nothing on a grouped grid — and the consumer this
exists for wraps every metric column in a group — so a second, independently
written copy of it is exactly the thing that drifts once only one of the two
callers is still being edited.
"""

from __future__ import annotations

from typing import Any, Iterator


def iter_column_defs(column_defs: Any) -> Iterator[dict]:
    """Every leaf and group colDef, depth first. Column groups nest their
    columns under ``children``."""
    if not isinstance(column_defs, (list, tuple)):
        return
    for column in column_defs:
        if not isinstance(column, dict):
            continue
        yield column
        yield from iter_column_defs(column.get("children"))


def label(column: dict) -> str:
    """How a colDef is named in a validation error."""
    name = column.get("colId") or column.get("field")
    return f"column {name!r}" if name else "unnamed aggregation column"
```

- [ ] **Step 4: Run the new test to verify it passes**

Run: `uv run pytest test/unit/test_coldefs.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Point `ratio.py` at the shared helpers**

In `st_aggrid/ratio.py`, delete the `_iter_column_defs` and `_label` function
definitions (they sit together just below the `_is_number` helper), and add
this import below the existing `from typing import ...` line:

```python
from st_aggrid._coldefs import iter_column_defs, label
```

Then rename the call sites:

```bash
sed -i 's/\b_iter_column_defs(/iter_column_defs(/g; s/\b_label(/label(/g' st_aggrid/ratio.py
```

- [ ] **Step 6: Verify no stale references remain**

Run: `grep -n "_iter_column_defs\|_label" st_aggrid/ratio.py`
Expected: no output.

Run: `grep -rn "_iter_column_defs\|_label" --include=*.py st_aggrid/ test/`
Expected: no output (these were private to `ratio.py` and nothing else imported them).

- [ ] **Step 7: Run the full unit suite**

Run: `uv run pytest -m "not e2e" -q`
Expected: PASS, no new failures. The ratio validation suite exercises both
helpers heavily, so it is the real regression gate for this move.

- [ ] **Step 8: Commit**

```bash
git add st_aggrid/_coldefs.py st_aggrid/ratio.py test/unit/test_coldefs.py
git commit -m "Extract the shared colDef walk into st_aggrid/_coldefs"
```

---

### Task 2: Python validation

The declaration is validated before it reaches the browser, and its names
become public. Unlike the ratio validator this one needs no DataFrame — a
colour scale names no data fields — so it runs for every grid.

**Files:**
- Create: `st_aggrid/color_scale.py`
- Modify: `st_aggrid/aggrid.py` (import + one call after `validate_ratio_columns`)
- Modify: `st_aggrid/__init__.py` (imports, docstring note, `__all__`)
- Test: `test/unit/test_color_scale_validation.py`
- Test: `test/unit/test_public_exports.py` (append)

**Interfaces:**
- Consumes: `st_aggrid._coldefs.iter_column_defs`, `st_aggrid._coldefs.label` (Task 1).
- Produces: `COLOR_SCALE_CONTEXT_KEY = "stColorScale"`, `COLOR_SCALE_SCHEMES = ("neutral", "positive", "diverging")`, `COLOR_SCALE_MODES = ("minmax", "zscore")`, `validate_color_scale_columns(grid_options: Optional[dict]) -> None`. All four re-exported from `st_aggrid`.

- [ ] **Step 1: Write the failing test**

Create `test/unit/test_color_scale_validation.py`:

```python
"""Validation rules for the built-in `stColorScale` declaration.

The failure this exists to prevent is a column that quietly paints nothing:
an unknown scheme name, or a `color_scale=True` with no grid-level default to
inherit from, both reach the browser as "no resolvable scheme" and are
indistinguishable from the feature simply being off. Every rule here turns
that silence into a loud error.

Unlike `ratio.py`'s validator this one takes no data columns — a colour scale
names no fields — so it applies to every grid, including one built entirely
from `grid_options["rowData"]`.
"""

import pytest

from st_aggrid.color_scale import (
    COLOR_SCALE_CONTEXT_KEY,
    COLOR_SCALE_MODES,
    COLOR_SCALE_SCHEMES,
    validate_color_scale_columns,
)


def grid_options(column_declaration, grid_declaration=None):
    """One painted column plus a plain dimension column, and optionally a
    grid-level default."""
    column = {"colId": "cpi", "field": "cpi"}
    if column_declaration is not None:
        column["context"] = {COLOR_SCALE_CONTEXT_KEY: column_declaration}
    options = {"columnDefs": [{"field": "campaign", "rowGroup": True}, column]}
    if grid_declaration is not None:
        options["context"] = {COLOR_SCALE_CONTEXT_KEY: grid_declaration}
    return options


def test_constants_are_the_literals_the_frontend_uses():
    assert COLOR_SCALE_CONTEXT_KEY == "stColorScale"
    assert COLOR_SCALE_SCHEMES == ("neutral", "positive", "diverging")
    assert COLOR_SCALE_MODES == ("minmax", "zscore")


def test_a_full_column_declaration_passes():
    validate_color_scale_columns(
        grid_options({"scheme": "diverging", "mode": "minmax", "skip_non_positive": False})
    )


def test_true_inherits_a_grid_level_scheme():
    validate_color_scale_columns(grid_options(True, {"scheme": "positive"}))


def test_false_is_accepted_and_needs_no_scheme():
    validate_color_scale_columns(grid_options(False))


def test_a_grid_level_default_alone_is_legal():
    # Defaults with nothing opted in paint nothing. That is a valid grid, not
    # an error — the switch simply happens to be off.
    validate_color_scale_columns({"columnDefs": [{"field": "a"}], "context":
                                  {COLOR_SCALE_CONTEXT_KEY: {"scheme": "neutral"}}})


def test_true_without_a_grid_level_default_is_rejected():
    with pytest.raises(ValueError, match="scheme"):
        validate_color_scale_columns(grid_options(True))


def test_a_column_override_wins_over_the_grid_default():
    validate_color_scale_columns(
        grid_options({"scheme": "neutral"}, {"scheme": "positive", "mode": "minmax"})
    )


def test_unknown_scheme_is_rejected():
    with pytest.raises(ValueError, match="scheme"):
        validate_color_scale_columns(grid_options({"scheme": "green"}))


def test_unknown_mode_is_rejected():
    with pytest.raises(ValueError, match="mode"):
        validate_color_scale_columns(grid_options({"scheme": "neutral", "mode": "zed"}))


def test_unknown_key_is_rejected():
    with pytest.raises(ValueError, match="alpha"):
        validate_color_scale_columns(grid_options({"scheme": "neutral", "alpha": 0.4}))


def test_reverse_is_rejected_until_phase_two():
    # Accepting a key the frontend ignores would let a consumer come to depend
    # on behaviour that does not exist.
    with pytest.raises(ValueError, match="reverse"):
        validate_color_scale_columns(grid_options({"scheme": "neutral", "reverse": True}))


def test_skip_non_positive_must_be_a_bool_not_an_int():
    # `bool` is an `int` subclass, so an `isinstance(..., int)` check would
    # let `1` through — the same trap `ratio.py`'s `_is_number` documents.
    with pytest.raises(ValueError, match="skip_non_positive"):
        validate_color_scale_columns(
            grid_options({"scheme": "neutral", "skip_non_positive": 1})
        )


def test_a_non_dict_column_declaration_is_rejected():
    with pytest.raises(ValueError, match="True, False or a dict"):
        validate_color_scale_columns(grid_options("positive"))


def test_a_bare_true_at_the_grid_level_is_rejected():
    # The grid level carries defaults only; `True` there activates nothing and
    # is a misunderstanding worth naming.
    with pytest.raises(ValueError, match="must be a dict"):
        validate_color_scale_columns(grid_options({"scheme": "neutral"}, True))


def test_a_declaration_inside_a_column_group_is_validated():
    options = {
        "columnDefs": [
            {
                "headerName": "Metrics",
                "children": [
                    {"colId": "cpi", "context": {COLOR_SCALE_CONTEXT_KEY: {"scheme": "nope"}}}
                ],
            }
        ]
    }
    with pytest.raises(ValueError, match="cpi"):
        validate_color_scale_columns(options)


def test_a_sibling_context_key_is_left_alone():
    # A metric column commonly carries both declarations; the colour-scale
    # validator must not trip over the ratio one.
    options = grid_options({"scheme": "neutral"})
    options["columnDefs"][1]["context"]["stRatio"] = {"num": ["cost"], "den": ["installs"]}
    validate_color_scale_columns(options)


def test_non_dict_grid_options_is_a_no_op():
    validate_color_scale_columns(None)
    validate_color_scale_columns("not grid options")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest test/unit/test_color_scale_validation.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'st_aggrid.color_scale'`

- [ ] **Step 3: Write the validator**

Create `st_aggrid/color_scale.py`:

```python
"""Validation for the built-in colour scales' declarations.

The arithmetic lives in the frontend (``frontend/src/colorScales/``). Python's
only job here is to reject a declaration that would otherwise paint nothing
with nothing raised — which is indistinguishable, on screen, from the feature
being switched off.

Unlike ``ratio.py``'s validator this one needs no DataFrame: a colour scale
names no data fields, only a shape. So it runs for every grid, including one
fed entirely through ``grid_options["rowData"]``.

A declaration lives under ``context['stColorScale']`` at two levels. The grid
level (``gridOptions['context']``) carries **defaults only** and never
activates painting; a column is painted when its own colDef carries an entry
that is not ``False``. The two are merged per key with the column winning, and
it is the **merged** result that must name a valid scheme. That is how
``color_scale=True`` with no grid-level default is caught here instead of
silently painting nothing in the browser.

The frontend implements the same merge again, as a guard, because it has to
cope with grid options that never went through ``GridOptionsBuilder`` — but
returning ``null`` inside a cell renderer is a worse error than raising here,
so this copy is the one that talks to the developer.
"""

from __future__ import annotations

from typing import Optional

from st_aggrid._coldefs import iter_column_defs, label

#: Where a declaration lives inside ``context``, at both levels.
COLOR_SCALE_CONTEXT_KEY = "stColorScale"

#: Palette names. The colours and ramps live in
#: ``frontend/src/colorScales/schemes.ts``; these strings must match its
#: ``SCHEMES`` keys exactly.
COLOR_SCALE_SCHEMES = ("neutral", "positive", "diverging")

#: Normalisation names, matching ``frontend/src/colorScales/normalize.ts``.
COLOR_SCALE_MODES = ("minmax", "zscore")

#: Every key a v1 declaration may carry. ``reverse`` is deliberately absent:
#: it is phase 2's metric-direction flag, and accepting it now would let a
#: consumer come to depend on a key the frontend ignores.
_KNOWN_KEYS = ("scheme", "mode", "skip_non_positive")


def _validate_declaration(declaration: dict, where: str) -> None:
    """The rules shared by the grid-level and the column-level declaration."""
    unknown = sorted(key for key in declaration if key not in _KNOWN_KEYS)
    if unknown:
        raise ValueError(
            f"{where}: unknown key(s) {unknown} in the colour scale "
            f"declaration. Available: {list(_KNOWN_KEYS)}."
        )

    if "scheme" in declaration and declaration["scheme"] not in COLOR_SCALE_SCHEMES:
        raise ValueError(
            f"{where}['scheme'] must be one of {COLOR_SCALE_SCHEMES}, got "
            f"{declaration['scheme']!r}."
        )

    if "mode" in declaration and declaration["mode"] not in COLOR_SCALE_MODES:
        raise ValueError(
            f"{where}['mode'] must be one of {COLOR_SCALE_MODES}, got "
            f"{declaration['mode']!r}."
        )

    if "skip_non_positive" in declaration and not isinstance(
        declaration["skip_non_positive"], bool
    ):
        # Checked against `bool` specifically: `bool` is an `int` subclass, so
        # an `isinstance(..., int)` test would accept `1`. Same trap
        # `ratio.py`'s `_is_number` documents from the other direction.
        raise ValueError(
            f"{where}['skip_non_positive'] must be a bool, got "
            f"{declaration['skip_non_positive']!r}."
        )


def validate_color_scale_columns(grid_options: Optional[dict]) -> None:
    """Raise ``ValueError`` for a malformed or unresolvable colour-scale
    declaration.

    Parameters
    ----------
    grid_options:
        The built grid options. Ignored when not a dict.
    """
    if not isinstance(grid_options, dict):
        return

    raw_grid_context = grid_options.get("context")
    grid_context = raw_grid_context if isinstance(raw_grid_context, dict) else {}
    grid_declaration = grid_context.get(COLOR_SCALE_CONTEXT_KEY)

    if grid_declaration is not None:
        if not isinstance(grid_declaration, dict):
            raise ValueError(
                f"gridOptions context['{COLOR_SCALE_CONTEXT_KEY}'] must be a "
                f"dict, got {type(grid_declaration).__name__}. The grid level "
                f"carries defaults only; a column opts in with its own entry."
            )
        _validate_declaration(
            grid_declaration, f"gridOptions context['{COLOR_SCALE_CONTEXT_KEY}']"
        )

    for column in iter_column_defs(grid_options.get("columnDefs")):
        raw_context = column.get("context")
        context = raw_context if isinstance(raw_context, dict) else {}
        if COLOR_SCALE_CONTEXT_KEY not in context:
            continue

        own = context[COLOR_SCALE_CONTEXT_KEY]
        where = f"{label(column)}: context['{COLOR_SCALE_CONTEXT_KEY}']"

        if own is False:
            continue
        if own is True:
            own = {}
        elif not isinstance(own, dict):
            raise ValueError(
                f"{where} must be True, False or a dict, got "
                f"{type(own).__name__}."
            )

        _validate_declaration(own, where)

        merged = {**(grid_declaration or {}), **own}
        if merged.get("scheme") not in COLOR_SCALE_SCHEMES:
            raise ValueError(
                f"{where} resolves to no valid 'scheme'. Set one on the "
                f"column, or supply a grid-level default with "
                f"GridOptionsBuilder.configure_color_scale(scheme=...). "
                f"Available: {COLOR_SCALE_SCHEMES}."
            )
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest test/unit/test_color_scale_validation.py -v`
Expected: PASS (18 tests)

- [ ] **Step 5: Call the validator from `AgGrid`**

In `st_aggrid/aggrid.py`, add next to the existing ratio import near line 11:

```python
from st_aggrid.color_scale import validate_color_scale_columns
```

and immediately after the existing `validate_ratio_columns(...)` call (it ends
with `column_types.index if column_types is not None else None,` and a closing
`)` around line 418), add:

```python
    # A colour-scale declaration names no data fields, only a shape, so unlike
    # the ratio check above this one needs no column set and runs for every
    # grid — including one built entirely from `grid_options["rowData"]`.
    validate_color_scale_columns(grid_options)
```

- [ ] **Step 6: Re-export the names**

In `st_aggrid/__init__.py`, add below the `from st_aggrid.column_state import (...)` block:

```python
from st_aggrid.color_scale import (
    COLOR_SCALE_CONTEXT_KEY,
    COLOR_SCALE_MODES,
    COLOR_SCALE_SCHEMES,
    validate_color_scale_columns,
)
```

and add these four entries to `__all__`, keeping it alphabetically sorted —
`"COLOR_SCALE_CONTEXT_KEY"`, `"COLOR_SCALE_MODES"`, `"COLOR_SCALE_SCHEMES"` go
after `"CONTEXT_KEY"`, and `"validate_color_scale_columns"` goes immediately
before `"validate_ratio_columns"`.

Also append this paragraph to the module docstring, after the paragraph about
the `RATIO_*` names:

```
The colour-scale names follow the prefixed convention from the start:
``COLOR_SCALE_CONTEXT_KEY``, ``COLOR_SCALE_SCHEMES`` and ``COLOR_SCALE_MODES``
have no unprefixed aliases, and new code should not add any.
```

- [ ] **Step 7: Pin the exports**

Append to `test/unit/test_public_exports.py`:

```python
def test_color_scale_names_are_importable_from_the_package_root():
    from st_aggrid import (
        COLOR_SCALE_CONTEXT_KEY,
        COLOR_SCALE_MODES,
        COLOR_SCALE_SCHEMES,
        validate_color_scale_columns,
    )
    from st_aggrid import color_scale as color_scale_module

    assert st_aggrid.COLOR_SCALE_CONTEXT_KEY is color_scale_module.COLOR_SCALE_CONTEXT_KEY
    assert st_aggrid.COLOR_SCALE_SCHEMES is color_scale_module.COLOR_SCALE_SCHEMES
    assert st_aggrid.COLOR_SCALE_MODES is color_scale_module.COLOR_SCALE_MODES
    assert st_aggrid.validate_color_scale_columns is validate_color_scale_columns


def test_color_scale_literals_match_what_the_frontend_registers_under():
    # `colorScales/index.ts` uses "stColorScale" as its context key and
    # `colorScales/schemes.ts` keys `SCHEMES` by these exact names. Nothing
    # mechanical keeps the two languages in step, so the literals are pinned
    # here by hand.
    assert st_aggrid.COLOR_SCALE_CONTEXT_KEY == "stColorScale"
    assert st_aggrid.COLOR_SCALE_SCHEMES == ("neutral", "positive", "diverging")
    assert st_aggrid.COLOR_SCALE_MODES == ("minmax", "zscore")


def test_every_public_name_is_in_dunder_all():
    for name in (
        "COLOR_SCALE_CONTEXT_KEY",
        "COLOR_SCALE_MODES",
        "COLOR_SCALE_SCHEMES",
        "validate_color_scale_columns",
    ):
        assert name in st_aggrid.__all__
```

- [ ] **Step 8: Run the unit suite**

Run: `uv run pytest -m "not e2e" -q`
Expected: PASS, no new failures.

- [ ] **Step 9: Commit**

```bash
git add st_aggrid/color_scale.py st_aggrid/aggrid.py st_aggrid/__init__.py \
        test/unit/test_color_scale_validation.py test/unit/test_public_exports.py
git commit -m "Validate stColorScale declarations and export their names"
```

---

### Task 3: GridOptionsBuilder support

Give the consumer the two call sites it will actually use, and make the
`context` merge safe — a metric column commonly carries a `stRatio`
declaration in the very dict this writes into.

**Files:**
- Modify: `st_aggrid/grid_options_builder.py` (`configure_column` signature and body; new `configure_color_scale`)
- Test: `test/unit/test_grid_options_builder.py` (append)

**Interfaces:**
- Consumes: `st_aggrid.color_scale.COLOR_SCALE_CONTEXT_KEY` (Task 2).
- Produces: `GridOptionsBuilder.configure_color_scale(scheme, mode=None, skip_non_positive=None)` and the new `color_scale` keyword on `GridOptionsBuilder.configure_column(field, header_name=None, color_scale=None, **other_column_properties)`.

- [ ] **Step 1: Write the failing test**

Append to `test/unit/test_grid_options_builder.py`:

```python
from st_aggrid.color_scale import COLOR_SCALE_CONTEXT_KEY


def _col(options, field):
    return {c["field"]: c for c in options["columnDefs"]}[field]


def test_configure_color_scale_writes_grid_level_defaults():
    gb = GridOptionsBuilder()
    gb.configure_color_scale(scheme="positive")
    options = gb.build()
    assert options["context"][COLOR_SCALE_CONTEXT_KEY] == {"scheme": "positive"}


def test_configure_color_scale_omits_unset_keys():
    # An unset key must be absent, not None: the scheme's own default has to
    # survive, and a written null would override it.
    gb = GridOptionsBuilder()
    gb.configure_color_scale(scheme="neutral")
    declaration = gb.build()["context"][COLOR_SCALE_CONTEXT_KEY]
    assert "mode" not in declaration and "skip_non_positive" not in declaration


def test_configure_color_scale_writes_the_keys_it_is_given():
    gb = GridOptionsBuilder()
    gb.configure_color_scale(scheme="neutral", mode="minmax", skip_non_positive=False)
    assert gb.build()["context"][COLOR_SCALE_CONTEXT_KEY] == {
        "scheme": "neutral",
        "mode": "minmax",
        "skip_non_positive": False,
    }


def test_configure_color_scale_preserves_an_existing_grid_context():
    gb = GridOptionsBuilder()
    gb.configure_grid_options(context={"myAppState": 1})
    gb.configure_color_scale(scheme="positive")
    context = gb.build()["context"]
    assert context["myAppState"] == 1
    assert context[COLOR_SCALE_CONTEXT_KEY] == {"scheme": "positive"}


def test_configure_column_writes_the_column_declaration():
    gb = GridOptionsBuilder()
    gb.configure_column("cpi", color_scale=True)
    assert _col(gb.build(), "cpi")["context"] == {COLOR_SCALE_CONTEXT_KEY: True}


def test_configure_column_accepts_false_and_a_dict():
    gb = GridOptionsBuilder()
    gb.configure_column("installs", color_scale=False)
    gb.configure_column("arppu", color_scale={"scheme": "diverging"})
    options = gb.build()
    assert _col(options, "installs")["context"][COLOR_SCALE_CONTEXT_KEY] is False
    assert _col(options, "arppu")["context"][COLOR_SCALE_CONTEXT_KEY] == {
        "scheme": "diverging"
    }


def test_color_scale_does_not_clobber_a_ratio_declaration_from_an_earlier_call():
    # The exact collision this merge exists for: the consumer's metric columns
    # carry both declarations, and a replaced `context` would delete the
    # aggregation the column depends on.
    gb = GridOptionsBuilder()
    gb.configure_column("cpi", context={"stRatio": {"num": ["cost"], "den": ["installs"]}})
    gb.configure_column("cpi", color_scale=True)
    context = _col(gb.build(), "cpi")["context"]
    assert context["stRatio"] == {"num": ["cost"], "den": ["installs"]}
    assert context[COLOR_SCALE_CONTEXT_KEY] is True


def test_color_scale_does_not_clobber_a_context_passed_in_the_same_call():
    gb = GridOptionsBuilder()
    gb.configure_column(
        "cpi",
        color_scale=True,
        context={"stRatio": {"num": ["cost"], "den": ["installs"]}},
    )
    context = _col(gb.build(), "cpi")["context"]
    assert context["stRatio"] == {"num": ["cost"], "den": ["installs"]}
    assert context[COLOR_SCALE_CONTEXT_KEY] is True


def test_configure_column_without_color_scale_writes_no_context():
    gb = GridOptionsBuilder()
    gb.configure_column("cpi", width=120)
    assert "context" not in _col(gb.build(), "cpi")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest test/unit/test_grid_options_builder.py -v`
Expected: FAIL — `AttributeError: 'GridOptionsBuilder' object has no attribute 'configure_color_scale'`, and `configure_column() got an unexpected keyword argument 'color_scale'` reported as a `TypeError`.

- [ ] **Step 3: Implement**

In `st_aggrid/grid_options_builder.py`, add to the imports at the top:

```python
from st_aggrid.color_scale import COLOR_SCALE_CONTEXT_KEY
```

Replace the whole `configure_column` method with:

```python
    def configure_column(
        self, field, header_name=None, color_scale=None, **other_column_properties
    ):
        """Configures an individual column
        check https://www.ag-grid.com/javascript-grid-column-properties/ for more information.

        Args:
            field (String): field name, usually equals the column header.
            header_name (String, optional): [description]. Defaults to None.
            color_scale (bool | dict, optional): opt this column into a
                built-in colour scale. ``True`` inherits every setting from
                the grid-level defaults set by `configure_color_scale`; a dict
                overrides them key by key (``scheme``, ``mode``,
                ``skip_non_positive``); ``False`` switches the column off
                explicitly. ``None`` (the default) writes nothing.
        """
        if not self._grid_options.get("columnDefs", None):
            self._grid_options["columnDefs"] = defaultdict(dict)

        col_def = {
            "headerName": field if header_name is None else header_name,
            "field": field,
        }

        if other_column_properties:
            col_def = {**col_def, **other_column_properties}

        if color_scale is not None:
            # Merged, never assigned: a metric column commonly carries a
            # `stRatio` declaration in this same dict — from an earlier
            # `configure_column` call or from a `context=` in this one — and
            # replacing it would delete the aggregation the column depends on.
            existing = self._grid_options["columnDefs"].get(field) or {}
            col_def["context"] = {
                **(existing.get("context") or {}),
                **(col_def.get("context") or {}),
                COLOR_SCALE_CONTEXT_KEY: color_scale,
            }

        self._grid_options["columnDefs"][field].update(col_def)
```

Then add this method immediately after `configure_column`:

```python
    def configure_color_scale(
        self, scheme: str, mode: str = None, skip_non_positive: bool = None
    ):
        """Grid-level defaults for the built-in colour scales.

        This activates nothing on its own — a column is painted only when it
        carries its own `color_scale=` opt-in. What it does is let that opt-in
        be a bare `True` instead of repeating the scheme on every one of a
        dashboard's metric columns.

        Args:
            scheme (str): "neutral", "positive" or "diverging".
            mode (str, optional): "minmax" or "zscore". Defaults to the
                scheme's own default when omitted.
            skip_non_positive (bool, optional): leave zero and negative values
                unpainted and out of the population. Defaults to the scheme's
                own default when omitted.
        """
        declaration = {"scheme": scheme}
        # An unset key is omitted rather than written as None: the scheme's own
        # default has to survive, and a null would override it.
        if mode is not None:
            declaration["mode"] = mode
        if skip_non_positive is not None:
            declaration["skip_non_positive"] = skip_non_positive

        context = dict(self._grid_options.get("context") or {})
        context[COLOR_SCALE_CONTEXT_KEY] = declaration
        self._grid_options["context"] = context
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest test/unit/test_grid_options_builder.py -v`
Expected: PASS

- [ ] **Step 5: Run the unit suite**

Run: `uv run pytest -m "not e2e" -q`
Expected: PASS, no new failures.

- [ ] **Step 6: Commit**

```bash
git add st_aggrid/grid_options_builder.py test/unit/test_grid_options_builder.py
git commit -m "Add configure_color_scale and configure_column(color_scale=...)"
```

---

### Task 4: Reference arithmetic fixture

The fixture owns the data **and** the expected colours, so no e2e assertion
ever hand-types an `rgba` — the convention `ratio_fixture.py` established. It
is a second, independently written implementation of the spec's formulas, and
that is the point: it is what catches a transcription error in a ramp.

**Files:**
- Create: `test/color_scale_fixture.py`
- Test: `test/unit/test_color_scale_fixture.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `COLOR_SCALE_ROWS`, `color_scale_dataframe()`, `ROW_DIM`, `LEAF_DIM`, `SCHEMES`, `CV_FLOOR`, `Z_DEAD`, `Z_CAP`, `half_up(x)`, `population(values, skip_non_positive)`, `stats(values)`, `expected_rgba(scheme_name, values, value, *, mode=None, skip_non_positive=None)`, `is_scheme_color(rgba, scheme_name)`, `column_values(field)`, `region_totals()`.

- [ ] **Step 1: Write the failing test**

Create `test/unit/test_color_scale_fixture.py`:

```python
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
    # u = 1.46385/3 = 0.48795; 240 - 15u = 232.681 -> 233
    assert expected_rgba("diverging", METRIC_A, 100) == (233, 18, 15, 0.366)
    # 190 - 15u = 182.681 -> 183
    assert expected_rgba("diverging", METRIC_A, 600) == (35, 183, 40, 0.366)


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest test/unit/test_color_scale_fixture.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'color_scale_fixture'`

- [ ] **Step 3: Write the fixture**

Create `test/color_scale_fixture.py`:

```python
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
    {"region": "EU", "country": "DE", "metric_a": 100, "metric_b": -5, "metric_c": 7},
    {"region": "EU", "country": "FR", "metric_a": 200, "metric_b": 0, "metric_c": 7},
    {"region": "EU", "country": "IT", "metric_a": 300, "metric_b": 10, "metric_c": 7},
    {"region": "US", "country": "CA", "metric_a": 400, "metric_b": 20, "metric_c": 7},
    {"region": "US", "country": "NY", "metric_a": 500, "metric_b": 30, "metric_c": 7},
    {"region": "US", "country": "TX", "metric_a": 600, "metric_b": 40, "metric_c": 7},
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


def expected_rgba(
    scheme_name: str,
    values: Iterable,
    value,
    *,
    mode: Optional[str] = None,
    skip_non_positive: Optional[bool] = None,
) -> Optional[tuple[int, int, int, float]]:
    """The ``(r, g, b, alpha)`` a cell must be painted, or ``None`` when it is
    left unpainted.

    ``values`` is the raw population — every value of the same column at the
    same group level, before the skip rule, which is applied here.
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

    pop = population(values, skip)
    if not pop:
        return None
    low, high, mean, sd = stats(pop)

    if mode == "minmax":
        if high <= low:
            return None
        t = (v - low) / (high - low)
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
        signed = z
        u = min(abs(z) / Z_CAP, 1.0)
        if scheme_name == "neutral":
            alpha = _neutral_z_alpha(abs(z))
        elif scheme_name == "diverging":
            alpha = _diverging_z_alpha(abs(z))
        else:
            alpha = scheme.alpha_min + u * (scheme.alpha_max - scheme.alpha_min)

    if scheme_name == "neutral":
        rgb = (51, 120, 200)
    elif scheme_name == "positive":
        rgb = (29, 158, 117)
    elif signed < 0:
        rgb = (half_up(240 - 15 * u), 18, 15)
    else:
        rgb = (35, half_up(190 - 15 * u), 40)

    return (*rgb, half_up(alpha * 1000) / 1000)


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
    return (g == 18 and b == 15) or (r == 35 and b == 40)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest test/unit/test_color_scale_fixture.py -v`
Expected: PASS (16 tests)

- [ ] **Step 5: Commit**

```bash
git add test/color_scale_fixture.py test/unit/test_color_scale_fixture.py
git commit -m "Add the colour-scale reference fixture and its anchors"
```

---

### Task 5: Pure frontend arithmetic

`normalize.ts` and `schemes.ts` hold every number in the spec and import
nothing — not from AG-Grid, not from each other. That is what lets them run
directly under `node`, which Node 22 does for `.ts` files with no test runner,
no new dependency and no change to `package.json`.

**Files:**
- Modify: `st_aggrid/frontend/tsconfig.json` (add `allowImportingTsExtensions`)
- Create: `st_aggrid/frontend/src/colorScales/normalize.ts`
- Create: `st_aggrid/frontend/src/colorScales/schemes.ts`
- Create: `st_aggrid/frontend/src/colorScales/__checks__/normalize.check.ts`
- Create: `st_aggrid/frontend/src/colorScales/__checks__/schemes.check.ts`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `normalize.ts`: `CV_FLOOR`, `Z_DEAD`, `Z_CAP`, `interface Stats { count, min, max, mean, sd }`, `popStats(values: number[]): Stats`, `minmaxT(stats: Stats, value: number): number | null`, `zScore(stats: Stats, value: number): number | null`, `zIntensity(z: number): number`.
  - `schemes.ts`: `type SchemeName`, `type ColorScaleMode`, `interface Normalized { mode, raw, intensity }`, `interface Scheme`, `SCHEMES: Record<SchemeName, Scheme>`, `colorFor(scheme: Scheme, n: Normalized): string`, `SCHEME_NAMES`, `MODE_NAMES`.

- [ ] **Step 1: Allow `.ts` import specifiers**

The check scripts must name their imports with a `.ts` extension for `node` to
resolve them; the production modules keep their extensionless imports. TypeScript
rejects the extension unless told otherwise, and the flag is legal here only
because this tsconfig already sets `"noEmit": true`.

In `st_aggrid/frontend/tsconfig.json`, add `"allowImportingTsExtensions": true,`
immediately after the `"noEmit": true,` line.

- [ ] **Step 2: Write the failing check for `normalize.ts`**

Create `st_aggrid/frontend/src/colorScales/__checks__/normalize.check.ts`:

```ts
/** Runnable check for `normalize.ts`. Run it with:
 *
 *     node st_aggrid/frontend/src/colorScales/__checks__/normalize.check.ts
 *
 * Node 22 strips the types and runs the module directly, so the pure
 * arithmetic gets a fast test cycle without adding a test runner to a package
 * that ships to the browser. Anything that needs a live grid is covered by
 * `test/test_grid_color_scale.py` instead.
 */
import assert from "node:assert/strict"
import { minmaxT, popStats, zIntensity, zScore } from "../normalize.ts"

const RAMP = [100, 200, 300, 400, 500, 600]
const stats = popStats(RAMP)

// Population standard deviation (divisor N), matching the JavaScript being
// replaced: sqrt(175000 / 6).
assert.equal(stats.count, 6)
assert.equal(stats.min, 100)
assert.equal(stats.max, 600)
assert.equal(stats.mean, 350)
assert.equal(stats.sd, 170.78251276599332)

assert.equal(minmaxT(stats, 100), 0)
assert.equal(minmaxT(stats, 600), 1)
assert.equal(minmaxT(stats, 300), 0.4)

// No spread: nothing to show.
assert.equal(minmaxT(popStats([7, 7, 7]), 7), null)
assert.equal(zScore(popStats([7, 7, 7]), 7), null)

// Dead zone: |z| = 0.29277 for 300.
assert.equal(zScore(stats, 300), null)
assert.equal(zScore(stats, 400), null)
assert.ok(Math.abs(zScore(stats, 100)! + 1.4638501094227998) < 1e-12)

// Uniformity floor uses |mean|, so a negative-mean column still paints.
const negative = popStats([-100, -200, -300, -400, -500, -600])
assert.ok(zScore(negative, -600) !== null)

// mean === 0 skips the floor rather than dividing by zero.
assert.ok(zScore(popStats([-10, 0, 10]), 10) !== null)

assert.equal(zIntensity(0), 0)
assert.equal(zIntensity(-1.5), 0.5)
assert.equal(zIntensity(9), 1)

console.log("normalize.check.ts ok")
```

- [ ] **Step 3: Run the check to verify it fails**

Run: `node st_aggrid/frontend/src/colorScales/__checks__/normalize.check.ts`
Expected: FAIL — `ERR_MODULE_NOT_FOUND` for `../normalize.ts`

- [ ] **Step 4: Write `normalize.ts`**

Create `st_aggrid/frontend/src/colorScales/normalize.ts`:

```ts
/** Statistics and gates for the built-in colour scales.
 *
 * Deliberately imports nothing — not AG-Grid, not a sibling module. That keeps
 * every number in the design reviewable on its own and lets
 * `__checks__/normalize.check.ts` run it directly under `node`.
 */

/** Below this coefficient of variation the column is treated as uniform and
 * nothing is painted. */
export const CV_FLOOR = 0.001

/** Values within this many standard deviations of the mean are left
 * unpainted — the dead zone around the average. */
export const Z_DEAD = 0.5

/** |z| at and beyond which a scale is fully saturated. */
export const Z_CAP = 3

export interface Stats {
  count: number
  min: number
  max: number
  mean: number
  /** The **population** standard deviation (divisor `count`, not `count - 1`).
   * That is what all three stylers this replaces compute, and using the sample
   * one instead would shift every z-score. */
  sd: number
}

/** Summary of one column's population. `values` must be non-empty — the caller
 * (`population.ts`) returns `null` for an empty population rather than calling
 * this with one. */
export function popStats(values: number[]): Stats {
  let min = Infinity
  let max = -Infinity
  let total = 0
  for (const value of values) {
    if (value < min) min = value
    if (value > max) max = value
    total += value
  }
  const mean = total / values.length
  let squares = 0
  for (const value of values) squares += (value - mean) * (value - mean)
  return { count: values.length, min, max, mean, sd: Math.sqrt(squares / values.length) }
}

/** Position in `[0, 1]` between the population's extremes, or `null` when the
 * column has no spread to show. */
export function minmaxT(stats: Stats, value: number): number | null {
  if (!(stats.max > stats.min)) return null
  return (value - stats.min) / (stats.max - stats.min)
}

/** Signed standard scores, or `null` when the column is uniform or the value
 * sits inside the dead zone.
 *
 * The uniformity floor divides by `|mean|`. The JavaScript this replaces
 * divides by the signed mean, which makes the coefficient negative for a
 * negative-mean column — always below the floor, so such a column would never
 * paint. Unreachable while every z-score scheme skips non-positive values, and
 * reachable the moment `skip_non_positive: false` is paired with `zscore`.
 */
export function zScore(stats: Stats, value: number): number | null {
  if (stats.sd === 0) return null
  if (stats.mean !== 0 && stats.sd / Math.abs(stats.mean) < CV_FLOOR) return null
  const z = (value - stats.mean) / stats.sd
  return Math.abs(z) < Z_DEAD ? null : z
}

/** How far out of the ordinary a z-score is, capped into `[0, 1]`. */
export function zIntensity(z: number): number {
  return Math.min(Math.abs(z) / Z_CAP, 1)
}
```

- [ ] **Step 5: Run the check to verify it passes**

Run: `node st_aggrid/frontend/src/colorScales/__checks__/normalize.check.ts`
Expected: `normalize.check.ts ok`

- [ ] **Step 6: Write the failing check for `schemes.ts`**

Create `st_aggrid/frontend/src/colorScales/__checks__/schemes.check.ts`:

```ts
/** Runnable check for `schemes.ts`. Run it with:
 *
 *     node st_aggrid/frontend/src/colorScales/__checks__/schemes.check.ts
 *
 * The expected colours are the same anchors
 * `test/unit/test_color_scale_fixture.py` pins on the Python side; if these
 * two ever disagree, one of them transcribed a ramp wrong.
 */
import assert from "node:assert/strict"
import { SCHEMES, colorFor } from "../schemes.ts"
import { zIntensity } from "../normalize.ts"

const Z = -1.4638501094227998 // metric_a = 100 against the 100..600 ramp

const minmax = (raw: number) => ({ mode: "minmax" as const, raw, intensity: 0 })
const zscore = (raw: number) => ({
  mode: "zscore" as const,
  raw,
  intensity: zIntensity(raw),
})

assert.equal(colorFor(SCHEMES.positive, minmax(0)), "rgba(29, 158, 117, 0.06)")
assert.equal(colorFor(SCHEMES.positive, minmax(1)), "rgba(29, 158, 117, 0.55)")
assert.equal(colorFor(SCHEMES.positive, minmax(0.4)), "rgba(29, 158, 117, 0.256)")

assert.equal(colorFor(SCHEMES.neutral, zscore(Z)), "rgba(51, 120, 200, 0.241)")
assert.equal(colorFor(SCHEMES.neutral, zscore(-0.87831006565368)), "rgba(51, 120, 200, 0.125)")
assert.equal(colorFor(SCHEMES.neutral, minmax(0)), "rgba(51, 120, 200, 0.08)")
assert.equal(colorFor(SCHEMES.neutral, minmax(1)), "rgba(51, 120, 200, 0.55)")

assert.equal(colorFor(SCHEMES.diverging, zscore(Z)), "rgba(233, 18, 15, 0.366)")
assert.equal(colorFor(SCHEMES.diverging, zscore(-Z)), "rgba(35, 183, 40, 0.366)")
assert.equal(colorFor(SCHEMES.diverging, minmax(0)), "rgba(225, 18, 15, 0.7)")
assert.equal(colorFor(SCHEMES.diverging, minmax(1)), "rgba(35, 175, 40, 0.7)")
assert.equal(colorFor(SCHEMES.diverging, minmax(0.4)), "rgba(237, 18, 15, 0.22)")

// positive has no piecewise ramp, so zscore interpolates its own endpoints.
assert.equal(colorFor(SCHEMES.positive, zscore(Z)), "rgba(29, 158, 117, 0.299)")

// Defaults, which `index.ts` fills in when the declaration omits them.
assert.equal(SCHEMES.neutral.defaultMode, "zscore")
assert.equal(SCHEMES.positive.defaultMode, "minmax")
assert.equal(SCHEMES.diverging.defaultMode, "zscore")
assert.equal(SCHEMES.neutral.defaultSkipNonPositive, true)
assert.equal(SCHEMES.positive.defaultSkipNonPositive, false)
assert.equal(SCHEMES.diverging.defaultSkipNonPositive, true)

console.log("schemes.check.ts ok")
```

- [ ] **Step 7: Run the check to verify it fails**

Run: `node st_aggrid/frontend/src/colorScales/__checks__/schemes.check.ts`
Expected: FAIL — `ERR_MODULE_NOT_FOUND` for `../schemes.ts`

- [ ] **Step 8: Write `schemes.ts`**

Create `st_aggrid/frontend/src/colorScales/schemes.ts`:

```ts
/** The three built-in palettes.
 *
 * Each scheme reproduces one of the hand-written stylers this feature
 * replaces, exactly: `neutral` the blue statistical wash from `funnel_saj`,
 * `positive` the green min/max ramp from `payers_intelligence`, `diverging`
 * the red/green split from the cohort report.
 *
 * Two invariants hold for all three. The fill is always `rgba(...)` over the
 * cell's own background and never an opaque colour — an opaque ramp paints a
 * light cell under the dark theme's light text and the number disappears,
 * which is a bug that already shipped once. And `diverging` reaches alpha 0.7,
 * above the 0.55 the other two stop at; that is what the cohort report draws
 * today, and it stays a named endpoint here so changing it later is one edit.
 *
 * Imports nothing, so `__checks__/schemes.check.ts` can run it under `node`.
 */

export type SchemeName = "neutral" | "positive" | "diverging"
export type ColorScaleMode = "minmax" | "zscore"

/** Must stay in step with `st_aggrid/color_scale.py`'s COLOR_SCALE_SCHEMES /
 * COLOR_SCALE_MODES, which `test/unit/test_public_exports.py` pins. */
export const SCHEME_NAMES: readonly SchemeName[] = ["neutral", "positive", "diverging"]
export const MODE_NAMES: readonly ColorScaleMode[] = ["minmax", "zscore"]

export interface Normalized {
  mode: ColorScaleMode
  /** `minmax`: `t` in `[0, 1]`. `zscore`: the signed z. */
  raw: number
  /** `zscore` only: `zIntensity(z)`. Ignored under `minmax`, where the
   * intensity depends on whether the scheme is diverging and so is derived
   * from `raw` here. */
  intensity: number
}

export interface Scheme {
  name: SchemeName
  defaultMode: ColorScaleMode
  defaultSkipNonPositive: boolean
  /** Endpoints of the linear ramp, used whenever `zRamp` does not apply. Not
   * invented numbers: they are the endpoints of each scheme's own piecewise
   * ramp, so a non-default `scheme x mode` pairing stays inside the palette
   * the scheme already draws. */
  alphaMin: number
  alphaMax: number
  /** `true` when the scheme splits below/above rather than running one hue. */
  diverging: boolean
  /** Alpha as a function of `|z|`, when the scheme reproduces a piecewise
   * ramp. Absent means the linear `alphaMin..alphaMax` ramp is used in both
   * modes. */
  zRamp?: (absZ: number) => number
  /** `sign` is -1 below the midpoint and +1 at or above it; `u` is the
   * intensity in `[0, 1]`. */
  rgb: (sign: number, u: number) => [number, number, number]
}

/** `floor(x + 0.5)` — `Math.round`'s exact semantics, spelled out because the
 * Python fixture that owns the expected colours must round the same way, and
 * Python's built-in `round` is half-to-even. */
function halfUp(x: number): number {
  return Math.floor(x + 0.5)
}

export const SCHEMES: Record<SchemeName, Scheme> = {
  neutral: {
    name: "neutral",
    defaultMode: "zscore",
    defaultSkipNonPositive: true,
    alphaMin: 0.08,
    alphaMax: 0.55,
    diverging: false,
    // Discontinuous at |z| = 1 (0.14 -> 0.2) and at |z| = 3 (0.319 -> 0.55).
    // Reproduced as-is: smoothing it is a product decision, not this one.
    zRamp: (z) =>
      z < 1 ? 0.08 + 0.12 * (z - 0.5) : z < 3 ? 0.2 + 0.25 * Math.log10(z) : 0.55,
    rgb: () => [51, 120, 200],
  },
  positive: {
    name: "positive",
    defaultMode: "minmax",
    defaultSkipNonPositive: false,
    alphaMin: 0.06,
    alphaMax: 0.55,
    diverging: false,
    rgb: () => [29, 158, 117],
  },
  diverging: {
    name: "diverging",
    defaultMode: "zscore",
    defaultSkipNonPositive: true,
    alphaMin: 0.1,
    alphaMax: 0.7,
    diverging: true,
    zRamp: (z) => (z < 1 ? 0.1 + 0.2 * (z - 0.5) : z < 3 ? 0.2 + Math.log10(z) : 0.7),
    rgb: (sign, u) =>
      sign < 0 ? [halfUp(240 - 15 * u), 18, 15] : [35, halfUp(190 - 15 * u), 40],
  },
}

/** The `rgba(...)` string for one normalised value.
 *
 * Alpha is rounded to three decimals so the same cell always serialises to the
 * same string — sub-perceptual, and it is what lets the e2e suite compare
 * against an exact number.
 */
export function colorFor(scheme: Scheme, n: Normalized): string {
  let u: number
  let sign: number

  if (n.mode === "minmax") {
    if (scheme.diverging) {
      const signed = 2 * n.raw - 1
      u = Math.abs(signed)
      sign = signed < 0 ? -1 : 1
    } else {
      u = n.raw
      sign = 1
    }
  } else {
    u = n.intensity
    sign = n.raw < 0 ? -1 : 1
  }

  const alpha =
    n.mode === "zscore" && scheme.zRamp
      ? scheme.zRamp(Math.abs(n.raw))
      : scheme.alphaMin + u * (scheme.alphaMax - scheme.alphaMin)

  const [r, g, b] = scheme.rgb(sign, u)
  return `rgba(${r}, ${g}, ${b}, ${halfUp(alpha * 1000) / 1000})`
}
```

- [ ] **Step 9: Run both checks to verify they pass**

```bash
node st_aggrid/frontend/src/colorScales/__checks__/normalize.check.ts
node st_aggrid/frontend/src/colorScales/__checks__/schemes.check.ts
```
Expected: `normalize.check.ts ok` and `schemes.check.ts ok`

- [ ] **Step 10: Typecheck**

Run: `cd st_aggrid/frontend && COREPACK_ENABLE_DOWNLOAD_PROMPT=0 corepack yarn tsc --noEmit`
Expected: no output.

- [ ] **Step 11: Commit**

```bash
git add st_aggrid/frontend/tsconfig.json st_aggrid/frontend/src/colorScales/
git commit -m "Add the colour scales' pure arithmetic and its node checks"
```

---

### Task 6: Frontend wiring and the first painted grid

Attach the built-in `cellStyle`, memoise the population statistics, invalidate
them when the model changes, and stand up the e2e app with one assertion that
proves the whole path works end to end.

**Files:**
- Create: `st_aggrid/frontend/src/colorScales/population.ts`
- Create: `st_aggrid/frontend/src/colorScales/index.ts`
- Modify: `st_aggrid/frontend/src/utils/parsers.ts` (import + one call)
- Modify: `st_aggrid/frontend/src/AgGridComponent.tsx` (ref, attach in `onGridReady`, tear down on unmount)
- Create: `test/grid_color_scale.py`
- Create: `test/test_grid_color_scale.py`
- Modify: `test/grid_dom.py` (add `parse_rgba` and `cell_backgrounds`)

**Interfaces:**
- Consumes: `popStats`, `minmaxT`, `zScore`, `zIntensity`, `Stats` (Task 5, `normalize.ts`); `SCHEMES`, `colorFor`, `Scheme`, `ColorScaleMode`, `SchemeName`, `Normalized` (Task 5, `schemes.ts`); `eachColDef` from `../aggFuncs/foldSums`; `color_scale_fixture` (Task 4); `GridOptionsBuilder.configure_color_scale` / `configure_column(color_scale=…)` (Task 3).
- Produces:
  - `population.ts`: `extractValue(raw: unknown): number | null`, `statsFor(api, column, level, skipNonPositive): Stats | null`, `clearStats(api): void`.
  - `index.ts`: `ST_COLOR_SCALE = "stColorScale"`, `readColorScaleConfig(colDef, gridContext): ResolvedColorScale | null`, `stColorScaleCellStyle(params): { backgroundColor: string } | null`, `registerColorScales(gridOptions, debug?): GridOptions`, `attachColorScaleInvalidation(api): () => void`.
  - `test/grid_dom.py`: `parse_rgba(text) -> tuple[int, int, int, float] | None`, `cell_backgrounds(page, grid_index) -> dict[str, dict[str, tuple | None]]`.

- [ ] **Step 1: Write `population.ts`**

Create `st_aggrid/frontend/src/colorScales/population.ts`:

```ts
import type { Column, GridApi, IRowNode } from "ag-grid-community"
import { popStats, Stats } from "./normalize"

/** The number behind a cell, whatever wrapper it arrives in.
 *
 * A strict superset of `foldSums.ts`'s private `sortValue`, and deliberately a
 * separate function: widening `sortValue` to also unwrap `.value` and the
 * legacy `{numerator, denominator}` shape would change the **sort order** of
 * any column carrying that shape, which is a separate decision and not a side
 * effect of adding colour.
 */
export function extractValue(raw: unknown): number | null {
  if (raw === null || raw === undefined || raw === "") return null

  if (typeof raw === "object") {
    const object = raw as Record<string, any>
    if (typeof object.toNumber === "function") return finite(object.toNumber())
    if (object.value !== undefined) return finite(object.value)
    if (object.numerator !== undefined && object.denominator !== undefined) {
      return object.denominator > 0
        ? finite(object.numerator / object.denominator)
        : null
    }
    return null
  }

  return typeof raw === "number" ? finite(raw) : null
}

function finite(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null
}

/** Per-grid, per-`colId:level` statistics for the current model generation.
 * A `WeakMap` so a destroyed grid's entry goes with it. */
const statsCache = new WeakMap<GridApi, Map<string, Stats | null>>()

/** Drop everything cached for one grid. Called when the model changes. */
export function clearStats(api: GridApi): void {
  statsCache.delete(api)
}

/**
 * The population statistics for one column at one group level, computed once
 * per model generation.
 *
 * The population is deliberately level-scoped: a group row's aggregate and a
 * leaf's own value are not comparable quantities, and pooling them lets a
 * group total set the maximum and wash every leaf out — which is what the
 * summed columns of the styler this replaces do today.
 *
 * Values are read through `api.getCellValue` rather than
 * `row.data[colId]` / `row.aggData[colId]`: that resolves `field`,
 * `valueGetter` and pivot result columns the way the grid itself does, so a
 * column whose `colId` differs from its `field` is not silently blank.
 *
 * `skipNonPositive` is not part of the cache key. It is fixed per column by
 * the resolved declaration, so `colId` already implies it.
 */
export function statsFor(
  api: GridApi,
  column: Column,
  level: number,
  skipNonPositive: boolean
): Stats | null {
  let byKey = statsCache.get(api)
  if (!byKey) {
    byKey = new Map()
    statsCache.set(api, byKey)
  }

  // `has`, not truthiness: `null` — "this column has no population at this
  // level" — is a stable answer for the generation and is memoised too.
  const key = `${column.getColId()}:${level}`
  if (byKey.has(key)) return byKey.get(key) ?? null

  const values: number[] = []
  api.forEachNodeAfterFilterAndSort((row: IRowNode) => {
    // The grand total is a window-wide aggregate, not a comparable row:
    // neither painted nor scanned. Same for a pinned row.
    if (row.footer || row.rowPinned != null) return
    if (row.level !== level) return
    const value = extractValue(api.getCellValue({ rowNode: row, colKey: column }))
    if (value === null) return
    if (skipNonPositive && value <= 0) return
    values.push(value)
  })

  const stats = values.length ? popStats(values) : null
  byKey.set(key, stats)
  return stats
}
```

- [ ] **Step 2: Write `index.ts`**

Create `st_aggrid/frontend/src/colorScales/index.ts`:

```ts
import type {
  CellClassParams,
  Column,
  ColDef,
  GridApi,
  GridOptions,
} from "ag-grid-community"
import { eachColDef } from "../aggFuncs/foldSums"
import { minmaxT, zIntensity, zScore } from "./normalize"
import {
  ColorScaleMode,
  Normalized,
  SCHEMES,
  Scheme,
  SchemeName,
  colorFor,
} from "./schemes"
import { clearStats, extractValue, statsFor } from "./population"

/** The key a declaration lives under inside `context`, at both levels.
 * Matches `st_aggrid/color_scale.py`'s COLOR_SCALE_CONTEXT_KEY. */
export const ST_COLOR_SCALE = "stColorScale"

export interface ResolvedColorScale {
  scheme: Scheme
  mode: ColorScaleMode
  skipNonPositive: boolean
}

/**
 * Merge a column's declaration over the grid-level defaults.
 *
 * A column is painted only when its own colDef carries an entry that is not
 * `false`; the grid level supplies defaults and never activates anything. The
 * merge is per key with the column winning, which is what will let phase 2's
 * `reverse` be one more key rather than a change to the shape of the API.
 *
 * Python's `validate_color_scale_columns` implements the same merge and is the
 * copy that produces an actionable error. This one exists because grid options
 * do not always come from `GridOptionsBuilder`, and returning `null` inside a
 * cell renderer is a better failure than throwing there.
 */
export function readColorScaleConfig(
  colDef: ColDef | null | undefined,
  gridContext: unknown
): ResolvedColorScale | null {
  const own = (colDef?.context as Record<string, unknown> | undefined)?.[ST_COLOR_SCALE]
  if (own === undefined || own === null || own === false) return null

  const gridDefaults = (gridContext as Record<string, unknown> | undefined)?.[
    ST_COLOR_SCALE
  ]
  const base = gridDefaults && typeof gridDefaults === "object" ? gridDefaults : {}
  const overrides = own === true ? {} : typeof own === "object" ? own : {}
  const merged = { ...base, ...overrides } as {
    scheme?: SchemeName
    mode?: ColorScaleMode
    skip_non_positive?: boolean
  }

  const scheme = merged.scheme ? SCHEMES[merged.scheme] : undefined
  if (!scheme) return null

  return {
    scheme,
    mode: merged.mode ?? scheme.defaultMode,
    skipNonPositive: merged.skip_non_positive ?? scheme.defaultSkipNonPositive,
  }
}

/** The built-in `cellStyle`. Returns `null` — not `{}` — for an unpainted cell,
 * so the theme paints it as it normally would. */
export function stColorScaleCellStyle(
  params: CellClassParams
): { backgroundColor: string } | null {
  const node = params.node
  if (!node || node.footer || node.rowPinned != null) return null

  const config = readColorScaleConfig(params.colDef, params.context)
  if (!config) return null

  const value = extractValue(params.value)
  if (value === null) return null
  if (config.skipNonPositive && value <= 0) return null

  const stats = statsFor(
    params.api,
    params.column as Column,
    node.level,
    config.skipNonPositive
  )
  if (!stats) return null

  const raw = config.mode === "minmax" ? minmaxT(stats, value) : zScore(stats, value)
  if (raw === null) return null

  const normalized: Normalized = {
    mode: config.mode,
    raw,
    intensity: config.mode === "zscore" ? zIntensity(raw) : 0,
  }
  return { backgroundColor: colorFor(config.scheme, normalized) }
}

/**
 * Attach `stColorScaleCellStyle` to every column carrying a declaration.
 *
 * A caller-supplied `cellStyle` wins and the built-in is not attached, logged
 * under `debug` — the same rule, for the same reason, that `registerAggFunc`
 * applies to a caller-supplied aggregator: a built-in is a default, not a
 * reservation, and a silently shadowed one would be baffling to track down.
 *
 * The attached function does not close over the declaration; it re-reads it
 * per call from `params.colDef.context` and `params.context`. Phase 2's
 * runtime toggle therefore only has to change a declaration and refresh, with
 * nothing re-attached.
 *
 * Pivot needs no handling here: AG-Grid copies `cellStyle` from the source
 * value colDef onto the pivot result column it generates.
 */
export function registerColorScales(
  gridOptions: GridOptions,
  debug: boolean = false
): GridOptions {
  eachColDef(gridOptions.columnDefs, (def) => {
    const declaration = (def.context as Record<string, unknown> | undefined)?.[
      ST_COLOR_SCALE
    ]
    if (declaration === undefined || declaration === null || declaration === false) {
      return
    }
    if (def.cellStyle) {
      if (debug) {
        console.log(
          `[st_aggrid] cellStyle on "${def.colId ?? def.field}" was supplied ` +
            `by the caller and overrides the built-in colour scale.`
        )
      }
      return
    }
    def.cellStyle = stColorScaleCellStyle
  })

  return gridOptions
}

/** Every displayed column that the colour scale paints. Derived on demand
 * rather than cached at attach time so it stays correct across
 * `updateGridOptions` and across pivot mode being toggled. */
function paintedColumnIds(api: GridApi): string[] {
  const columns = (api.isPivotMode() ? api.getPivotResultColumns() : api.getColumns()) ?? []
  const context = api.getGridOption("context")
  return columns
    .filter((column) => readColorScaleConfig(column.getColDef(), context) !== null)
    .map((column) => column.getColId())
}

/**
 * Keep the cached statistics honest across filtering, sorting and new data.
 * Returns its own teardown.
 *
 * Clearing the cache would be enough if this listener were guaranteed to run
 * before AG-Grid re-renders its rows, but listener ordering is not ours to
 * control — so the refresh is the safety net that repaints anything already
 * drawn from stale statistics. `refreshCells` does not raise `modelUpdated`,
 * so this cannot loop; the `refreshing` flag says so explicitly rather than
 * leaving it implicit. Only the rendered viewport is repainted, so the cost is
 * a few dozen rows however large the grid is.
 */
export function attachColorScaleInvalidation(api: GridApi): () => void {
  let frame = 0
  let refreshing = false

  const onModelUpdated = () => {
    if (refreshing) return
    clearStats(api)
    if (frame) return
    frame = requestAnimationFrame(() => {
      frame = 0
      if (api.isDestroyed()) return
      const columns = paintedColumnIds(api)
      if (!columns.length) return
      refreshing = true
      try {
        api.refreshCells({ force: true, columns })
      } finally {
        refreshing = false
      }
    })
  }

  api.addEventListener("modelUpdated", onModelUpdated)

  return () => {
    if (frame) {
      cancelAnimationFrame(frame)
      frame = 0
    }
    if (!api.isDestroyed()) api.removeEventListener("modelUpdated", onModelUpdated)
  }
}
```

- [ ] **Step 3: Register from `parseGridOptions`**

In `st_aggrid/frontend/src/utils/parsers.ts`, add to the imports:

```ts
import { registerColorScales } from "../colorScales"
```

and immediately after the existing `registerStWeightedAvg(gridOptions, data.debug === true)` line (about line 42), add:

```ts
  // Built-in colour scales. Same site as the aggregators above for the same
  // reason: both the mount path and the live-update path go through here, so a
  // runtime config change never leaves a declared column unpainted.
  registerColorScales(gridOptions, data.debug === true)
```

- [ ] **Step 4: Attach the invalidation listener**

In `st_aggrid/frontend/src/AgGridComponent.tsx`:

1. Add to the imports, next to the other local imports:

```ts
import { attachColorScaleInvalidation } from "./colorScales"
```

2. Below the `const findCleanupRef = useRef<(() => void) | null>(null)` line
   (about line 160), add:

```ts
  const colorScaleCleanupRef = useRef<(() => void) | null>(null)
```

3. Inside `onGridReady`, after the `findCleanupRef.current = () => {...}` block
   closes (about line 812), add:

```ts
      // Colour-scale statistics are memoised per column per model generation;
      // this drops them and repaints when filtering, sorting or new data
      // changes what the population is. Torn down in the unmount effect.
      colorScaleCleanupRef.current = attachColorScaleInvalidation(event.api)
```

4. In the unmount effect (about line 777), after the two `findCleanupRef` lines,
   add:

```ts
      colorScaleCleanupRef.current?.()
      colorScaleCleanupRef.current = null
```

- [ ] **Step 5: Typecheck and build**

```bash
cd st_aggrid/frontend && COREPACK_ENABLE_DOWNLOAD_PROMPT=0 corepack yarn tsc --noEmit
COREPACK_ENABLE_DOWNLOAD_PROMPT=0 corepack yarn build
```
Expected: `tsc` silent; the build writes exactly one `index-<hash>.js` and one
`index-<hash>.css` into `st_aggrid/frontend/build/`. `git status` will show a
delete plus an add for those files, not a modify — filenames are content-hashed.

- [ ] **Step 6: Add the DOM reading helpers**

Append to `test/grid_dom.py`:

```python
_READ_CELL_BACKGROUNDS = """
(gridIndex) => {
  const grid = document.querySelectorAll('.ag-root-wrapper')[gridIndex];
  const rows = {};
  for (const row of grid.querySelectorAll('.ag-row')) {
    const section = row.closest('.ag-floating-bottom') ? 'bottom'
                  : row.closest('.ag-floating-top') ? 'top' : 'body';
    const key = section + ':' + row.getAttribute('row-index');
    const cells = rows[key] || (rows[key] = {});
    for (const cell of row.querySelectorAll('.ag-cell')) {
      cells[cell.getAttribute('col-id')] = getComputedStyle(cell).backgroundColor;
    }
  }
  return rows;
}
"""


def cell_backgrounds(page: Page, grid_index: int) -> dict[str, dict[str, tuple | None]]:
    """Every rendered cell's computed background, keyed the way `read_rows`
    keys its text: ``"<section>:<row-index>"`` then col-id.

    Parsed into ``(r, g, b, alpha)`` here rather than left as browser strings,
    because the browser reserialises alpha at its own precision and a string
    comparison would be comparing formatting rather than colour.
    """
    raw = page.evaluate(_READ_CELL_BACKGROUNDS, grid_index)
    return {
        key: {col_id: parse_rgba(text) for col_id, text in cells.items()}
        for key, cells in raw.items()
    }


def parse_rgba(text: str) -> tuple[int, int, int, float] | None:
    """``"rgba(29, 158, 117, 0.06)"`` or ``"rgb(29, 158, 117)"`` as
    ``(r, g, b, alpha)``. ``None`` for anything else, including the
    ``"transparent"`` some engines return."""
    match = re.fullmatch(
        r"\s*rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)"
        r"(?:[,/\s]+([\d.]+))?\s*\)\s*",
        text or "",
    )
    if not match:
        return None
    r, g, b, a = match.groups()
    return (int(float(r)), int(float(g)), int(float(b)), float(a) if a is not None else 1.0)
```

and add `import re` to the top of the file, above `import pytest`.

- [ ] **Step 7: Write the Streamlit app**

Create `test/grid_color_scale.py`:

```python
"""Streamlit app: the built-in declarative colour scales.

Three grids over one fixture (`color_scale_fixture.py`, which also owns the
expected colours):

  0  flat — every scheme at its default mode, every non-default `scheme x mode`
     pairing, both `skip_non_positive` settings, a uniform column, and a column
     whose own `cellStyle` must win over the built-in. A floating text filter on
     `region` is what the re-scaling test drives.
  1  row-grouped by region with a grand total — the level-scoped population and
     the unpainted footer.
  2  row-grouped by country, pivoted on region — group rows painted per pivot
     result column.

Run standalone with:  streamlit run test/grid_color_scale.py
"""

import streamlit as st

from st_aggrid import AgGrid, GridOptionsBuilder, JsCode

from color_scale_fixture import LEAF_DIM, ROW_DIM, color_scale_dataframe

df = color_scale_dataframe()

#: Virtualisation off so `cell_backgrounds` sees every row rather than the
#: window, matching what the ratio apps do.
COMMON_OPTIONS = {
    "suppressColumnVirtualisation": True,
    "suppressRowVirtualisation": True,
    "animateRows": False,
}

#: A styler the built-in must not displace. Flat grey, nothing a scheme would
#: ever produce, so the assertion cannot pass by coincidence.
OWN_STYLE = JsCode("function(params) { return {backgroundColor: 'rgb(1, 2, 3)'}; }")


def metric_column(col_id, field, header, color_scale, **extra):
    return {
        "colId": col_id,
        "field": field,
        "headerName": header,
        "type": "numericColumn",
        "context": {"stColorScale": color_scale},
        "width": 130,
        **extra,
    }


st.subheader("Flat — every scheme, every mode, both skip settings")
AgGrid(
    df,
    grid_options={
        **COMMON_OPTIONS,
        "columnDefs": [
            {
                "colId": ROW_DIM,
                "field": ROW_DIM,
                "filter": "agTextColumnFilter",
                "floatingFilter": True,
            },
            {"colId": LEAF_DIM, "field": LEAF_DIM},
            metric_column("pos_minmax", "metric_a", "positive", {"scheme": "positive"}),
            metric_column("neu_zscore", "metric_a", "neutral", {"scheme": "neutral"}),
            metric_column("div_zscore", "metric_a", "diverging", {"scheme": "diverging"}),
            metric_column(
                "neu_minmax", "metric_a", "neutral/minmax",
                {"scheme": "neutral", "mode": "minmax"},
            ),
            metric_column(
                "pos_zscore", "metric_a", "positive/zscore",
                {"scheme": "positive", "mode": "zscore"},
            ),
            metric_column(
                "div_minmax", "metric_a", "diverging/minmax",
                {"scheme": "diverging", "mode": "minmax"},
            ),
            metric_column(
                "skip_on", "metric_b", "skip on",
                {"scheme": "positive", "skip_non_positive": True},
            ),
            metric_column(
                "skip_off", "metric_b", "skip off",
                {"scheme": "neutral", "skip_non_positive": False},
            ),
            metric_column("uniform", "metric_c", "uniform", {"scheme": "positive"}),
            metric_column(
                "own_style", "metric_a", "own cellStyle",
                {"scheme": "positive"}, cellStyle=OWN_STYLE,
            ),
        ],
    },
    allow_unsafe_jscode=True,
    enable_enterprise_modules=True,
    height=320,
    key="color_scale_flat",
)

st.subheader("Row grouping — level-scoped population, unpainted grand total")
AgGrid(
    df,
    grid_options={
        **COMMON_OPTIONS,
        "groupDefaultExpanded": -1,
        "grandTotalRow": "bottom",
        "columnDefs": [
            {"colId": ROW_DIM, "field": ROW_DIM, "rowGroup": True, "rowGroupIndex": 0},
            {"colId": LEAF_DIM, "field": LEAF_DIM},
            metric_column(
                "grouped", "metric_a", "positive", {"scheme": "positive"},
                aggFunc="sum",
            ),
        ],
    },
    enable_enterprise_modules=True,
    height=320,
    key="color_scale_grouped",
)

st.subheader("Pivot — group rows painted per pivot result column")
AgGrid(
    df,
    grid_options={
        **COMMON_OPTIONS,
        "pivotMode": True,
        "groupDefaultExpanded": -1,
        "pivotDefaultExpanded": -1,
        "suppressAggFuncInHeader": True,
        "columnDefs": [
            {"colId": LEAF_DIM, "field": LEAF_DIM, "rowGroup": True, "rowGroupIndex": 0},
            {"colId": ROW_DIM, "field": ROW_DIM, "pivot": True},
            metric_column(
                "pivoted", "metric_a", "positive", {"scheme": "positive"},
                aggFunc="sum",
            ),
        ],
    },
    enable_enterprise_modules=True,
    height=320,
    key="color_scale_pivot",
)
```

- [ ] **Step 8: Write the smoke test**

Create `test/test_grid_color_scale.py`:

```python
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

from color_scale_fixture import column_values, expected_rgba
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
    # The grand total on the grouped grid is the last thing to render.
    page.wait_for_selector('[row-index="7"]', timeout=60000)


def test_positive_minmax_paints_the_flat_ramp(page: Page):
    """The end-to-end smoke: a declaration in `context` alone, with no JsCode,
    paints the column the fixture says it should."""
    painted = cell_backgrounds(page, FLAT_GRID)
    for key, value in zip(FLAT_ROWS, METRIC_A):
        assert painted[key]["pos_minmax"] == expected_rgba("positive", METRIC_A, value), key
```

- [ ] **Step 9: Run the smoke test**

Run: `uv run pytest test/test_grid_color_scale.py -v`
Expected: PASS.

If it fails on `api.getCellValue`, that is the one call in `population.ts` this
plan has not exercised before now — check the error, and if the signature
differs on 36.0.0 fall back to
`row.group ? row.aggData?.[colId] : row.data?.[colDef.field ?? colId]`,
keeping the `field`-before-`colId` order (the flat grid's metric columns all
have a `colId` that differs from their `field`, which is exactly what a
`colId`-only lookup gets wrong).

- [ ] **Step 10: Run the whole suite**

Run: `uv run pytest -q`
Expected: PASS, with the pre-existing drag-and-drop skip and no new failures.

- [ ] **Step 11: Commit**

```bash
git add st_aggrid/frontend/src/colorScales/ st_aggrid/frontend/src/utils/parsers.ts \
        st_aggrid/frontend/src/AgGridComponent.tsx st_aggrid/frontend/build \
        test/grid_color_scale.py test/test_grid_color_scale.py test/grid_dom.py
git commit -m "Paint declared columns with the built-in colour scales"
```

---

### Task 7: Full end-to-end coverage

The smoke test proves the path. These prove the arithmetic, the scoping and
the gates.

**Files:**
- Modify: `test/test_grid_color_scale.py` (append)

**Interfaces:**
- Consumes: everything Task 6 produced, plus `color_scale_fixture.is_scheme_color`, `column_values`, `region_totals`.
- Produces: nothing new.

- [ ] **Step 1: Write the scheme and mode tests**

First widen the import block at the top of `test/test_grid_color_scale.py` to:

```python
from color_scale_fixture import (
    column_values,
    expected_rgba,
    is_scheme_color,
    region_totals,
)
from e2e_utils import StreamlitRunner
from grid_dom import cell_backgrounds, read_rows
```

Then append:

```python
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
            assert not is_scheme_color(actual, scheme), f"{key}: {col_id} should be unpainted"
        else:
            assert actual == expected, f"{key}: {col_id}"


def test_the_zscore_dead_zone_leaves_the_middle_rows_alone(page: Page):
    # 300 and 400 sit within 0.5 sd of the mean 350. Pinned explicitly rather
    # than left to the parametrised loop: it is the one gate whose *absence*
    # would still produce plausible-looking colours.
    painted = cell_backgrounds(page, FLAT_GRID)
    assert not is_scheme_color(painted["body:2"]["neu_zscore"], "neutral")
    assert not is_scheme_color(painted["body:3"]["neu_zscore"], "neutral")
    assert is_scheme_color(painted["body:1"]["neu_zscore"], "neutral")
    assert is_scheme_color(painted["body:4"]["neu_zscore"], "neutral")


def test_a_uniform_column_is_never_painted(page: Page):
    painted = cell_backgrounds(page, FLAT_GRID)
    for key in FLAT_ROWS:
        assert not is_scheme_color(painted[key]["uniform"], "positive"), key


def test_skip_non_positive_excludes_the_zero_and_the_negative(page: Page):
    painted = cell_backgrounds(page, FLAT_GRID)
    # DE is -5 and FR is 0: unpainted, and out of the population, so IT (10) is
    # the column minimum rather than a mid-ramp value.
    assert not is_scheme_color(painted["body:0"]["skip_on"], "positive")
    assert not is_scheme_color(painted["body:1"]["skip_on"], "positive")
    for key, value in zip(FLAT_ROWS, METRIC_B):
        expected = expected_rgba("positive", METRIC_B, value, skip_non_positive=True)
        if expected is not None:
            assert painted[key]["skip_on"] == expected, key


def test_without_the_skip_the_negative_is_painted(page: Page):
    painted = cell_backgrounds(page, FLAT_GRID)
    for key, value in zip(FLAT_ROWS, METRIC_B):
        expected = expected_rgba("neutral", METRIC_B, value, skip_non_positive=False)
        actual = painted[key]["skip_off"]
        if expected is None:
            assert not is_scheme_color(actual, "neutral"), key
        else:
            assert actual == expected, key


def test_a_caller_supplied_cell_style_wins(page: Page):
    # Same declaration as `pos_minmax`, but the column carries its own
    # cellStyle: the built-in must not be attached at all.
    painted = cell_backgrounds(page, FLAT_GRID)
    for key in FLAT_ROWS:
        assert painted[key]["own_style"] == (1, 2, 3, 1.0), key
```

- [ ] **Step 2: Run them**

Run: `uv run pytest test/test_grid_color_scale.py -v`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add test/test_grid_color_scale.py
git commit -m "Cover every scheme, mode and gate on the flat colour-scale grid"
```

- [ ] **Step 4: Write the scoping and re-scaling tests**

Append to `test/test_grid_color_scale.py`:

```python
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
    assert painted["body:0"]["grouped"] == expected_rgba("positive", totals, 600.0)
    assert painted["body:4"]["grouped"] == expected_rgba("positive", totals, 1500.0)

    # And the leaves keep their own 100..600 scale.
    assert painted["body:1"]["grouped"] == expected_rgba("positive", METRIC_A, 100.0)
    assert painted["body:3"]["grouped"] == expected_rgba("positive", METRIC_A, 300.0)

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
    rows = read_rows(page, GROUPED_GRID)
    key = next(
        key
        for key, cells in rows.items()
        if cells.get("ag-Grid-AutoColumn-region") == "Total"
    )
    painted = cell_backgrounds(page, GROUPED_GRID)
    assert not is_scheme_color(painted[key].get("grouped"), "positive")


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

    assert painted[by_country["DE"]][eu_col] == expected_rgba("positive", eu, 100.0)
    assert painted[by_country["IT"]][eu_col] == expected_rgba("positive", eu, 300.0)
    assert painted[by_country["CA"]][us_col] == expected_rgba("positive", us, 400.0)
    assert painted[by_country["TX"]][us_col] == expected_rgba("positive", us, 600.0)

    # A country belongs to one region, so its cell in the other region's column
    # is empty — unpainted, and absent from that column's population, which the
    # three-value scales asserted above already depend on.
    assert not is_scheme_color(painted[by_country["DE"]].get(us_col), "positive")
    assert not is_scheme_color(painted[by_country["TX"]].get(eu_col), "positive")

    pooled = eu + us
    assert expected_rgba("positive", pooled, 300.0) != expected_rgba("positive", eu, 300.0)


def group_row_keys(page: Page, grid_index: int) -> dict[str, str]:
    """Group label -> ``"<section>:<row-index>"``.

    Read rather than assumed: AG-Grid orders groups by first encounter in the
    data, not alphabetically, and hard-coding either order would make this
    suite fail for a reason that has nothing to do with colour.
    """
    keys = {}
    for key, cells in read_rows(page, grid_index).items():
        label = cells.get("ag-Grid-AutoColumn-country", "")
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
    assert before["body:0"]["pos_minmax"] == expected_rgba("positive", METRIC_A, 100.0)

    grid = page.locator(".ag-root-wrapper").nth(FLAT_GRID)
    grid.locator('.ag-floating-filter[col-id="region"] input').fill("EU")
    page.wait_for_function(
        """(gridIndex) => {
             const grid = document.querySelectorAll('.ag-root-wrapper')[gridIndex];
             return grid.querySelectorAll('.ag-center-cols-container .ag-row').length === 3;
           }""",
        arg=FLAT_GRID,
        timeout=10000,
    )

    after = cell_backgrounds(page, FLAT_GRID)
    eu_only = [100.0, 200.0, 300.0]
    assert after["body:0"]["pos_minmax"] == expected_rgba("positive", eu_only, 100.0)
    # IT was mid-ramp over six rows and is the maximum over three.
    assert after["body:2"]["pos_minmax"] == expected_rgba("positive", eu_only, 300.0)
    assert after["body:2"]["pos_minmax"] != before["body:2"]["pos_minmax"]
```

- [ ] **Step 5: Run them**

Run: `uv run pytest test/test_grid_color_scale.py -v`
Expected: PASS.

The pivot result column ids, the pivot grid's group rows and the grand total
row are all read from the live grid rather than assumed. The one thing still
hard-coded is the **grouped** grid's body indices — `body:0` EU group,
`body:1`–`body:3` its DE/FR/IT leaves, `body:4` US group, `body:5`–`body:7` its
leaves, which is the fully expanded tree in fixture order. If that is wrong,
print `read_rows(page, GROUPED_GRID)` to see the actual layout and correct the
constants; do not loosen an assertion to make it pass.

- [ ] **Step 6: Run the whole suite**

Run: `uv run pytest -q`
Expected: PASS, no new failures.

- [ ] **Step 7: Commit**

```bash
git add test/test_grid_color_scale.py
git commit -m "Cover level scoping, pivot columns, the grand total and re-scaling"
```

---

### Task 8: Documentation and version

**Files:**
- Modify: `README.md` (new section)
- Modify: `pyproject.toml` (version)
- Modify: `st_aggrid/pyproject.toml` (version)
- Modify: `CLAUDE.md` (architecture tree and key design decisions)
- Test: `test/unit/test_component_manifest.py` (already asserts the two versions match — run it)

**Interfaces:**
- Consumes: everything above.
- Produces: nothing.

- [ ] **Step 1: Bump both versions**

Both files currently read `2.3.0`. Set both to `2.4.0` — the in-wheel component
manifest's version must match the root project's on every bump, and
`test/unit/test_component_manifest.py` enforces it.

```bash
sed -i '0,/^version = "2.3.0"$/s//version = "2.4.0"/' pyproject.toml
sed -i '0,/^version = "2.3.0"$/s//version = "2.4.0"/' st_aggrid/pyproject.toml
grep -n '^version' pyproject.toml st_aggrid/pyproject.toml
```
Expected: both print `version = "2.4.0"`.

- [ ] **Step 2: Verify the manifest test still passes**

Run: `uv run pytest test/unit/test_component_manifest.py -v`
Expected: PASS.

- [ ] **Step 3: Add the README section**

Add a section titled **"Declarative colour scales without JavaScript"**
immediately after the existing "Declarative aggregation without JavaScript"
section. Its content, verbatim (the outer fence below is four backticks so the
nested Python block survives; do not copy the outer fence into the README):

````markdown
## Declarative colour scales without JavaScript

A numeric column can be painted as a heat map from a declaration, with no
`JsCode` and no `allow_unsafe_jscode`.

```python
gb = GridOptionsBuilder.from_dataframe(df)
gb.configure_color_scale(scheme="positive")          # grid-level defaults
gb.configure_column("revenue", color_scale=True)     # inherit them
gb.configure_column("arppu", color_scale={"scheme": "diverging"})
gb.configure_column("installs", color_scale=False)   # explicitly off
AgGrid(df, gridOptions=gb.build())
```

A grid-level declaration paints nothing on its own — it supplies defaults, and
a column opts in with its own entry.

### Schemes

| `scheme` | Default `mode` | Reads as |
|---|---|---|
| `neutral` | `zscore` | one blue hue, intensity = distance from the column mean |
| `positive` | `minmax` | one green hue, palest at the column minimum |
| `diverging` | `zscore` | red below the mean, green above it |

### Keys

| Key | Values | Default |
|---|---|---|
| `scheme` | `"neutral"`, `"positive"`, `"diverging"` | required at one of the two levels |
| `mode` | `"minmax"`, `"zscore"` | the scheme's own |
| `skip_non_positive` | `bool` | the scheme's own |

`minmax` ramps linearly between the column's extremes. `zscore` measures
distance from the column's mean in standard deviations, leaves values within
half a deviation of the mean unpainted, and paints nothing at all when the
column is effectively uniform.

### What a column is compared against

The rows of the same column **at the same group level**, after the current
filter and sort. A group row's aggregate and a leaf's own value are not
comparable quantities, so they are never pooled — pooling them lets a group
total set the maximum and wash every leaf out. The grand total and pinned rows
are neither painted nor counted.

Because the population is read after filtering, hiding rows re-scales the
column rather than leaving a dead ramp.

### Interaction with `cellStyle`

A column that declares its own `cellStyle` keeps it; the built-in is not
attached. Pass `debug=True` to `AgGrid` to log when that happens.
````

- [ ] **Step 4: Update CLAUDE.md**

In the architecture tree, add below the `aggFuncs/` entries:

```
    │   ├── colorScales/normalize.ts   # popStats, min-max / z-score gates
    │   ├── colorScales/schemes.ts     # the three palettes and their alpha ramps
    │   ├── colorScales/population.ts  # level-scoped population + memoised stats
    │   └── colorScales/index.ts       # declaration resolution, cellStyle, registration
```

and add below the `ratio.py` line in the Python section:

```
├── color_scale.py           # Validation for stColorScale declarations
├── _coldefs.py              # colDef walk shared by both validators
```

Add to **Key Design Decisions**:

```
- **Three built-in colour schemes**: `neutral`, `positive`, `diverging` —
  declared in `colDef.context["stColorScale"]` with grid-level defaults in
  `gridOptions["context"]`, sharing one statistics pass
  (`colorScales/population.ts`). A column's population is the same column at
  the same group level after filter and sort; a caller-supplied `cellStyle`
  wins over the built-in, as with the aggregators. See the README's
  "Declarative colour scales without JavaScript".
```

Add to **Conventions**:

```
- The two pure colour-scale modules (`colorScales/normalize.ts`,
  `colorScales/schemes.ts`) import nothing and are exercised by
  `src/colorScales/__checks__/*.check.ts`, run with plain
  `node <path>.check.ts` — Node 22 strips the types, so the arithmetic has a
  fast test cycle without a JS test runner in a package that ships to the
  browser. `tsconfig.json` sets `allowImportingTsExtensions` for those checks'
  `.ts` import specifiers.
```

- [ ] **Step 5: Run everything one last time**

```bash
uv run pytest -q
node st_aggrid/frontend/src/colorScales/__checks__/normalize.check.ts
node st_aggrid/frontend/src/colorScales/__checks__/schemes.check.ts
cd st_aggrid/frontend && COREPACK_ENABLE_DOWNLOAD_PROMPT=0 corepack yarn tsc --noEmit
```
Expected: pytest passes with only the pre-existing drag-and-drop skip; both
checks print `ok`; `tsc` is silent.

- [ ] **Step 6: Commit**

```bash
git add README.md CLAUDE.md pyproject.toml st_aggrid/pyproject.toml
git commit -m "Document the declarative colour scales and bump to 2.4.0"
```

---

## Out of scope

Recorded so nobody adds them mid-plan:

- **`reverse`** (metric direction). Phase 2. Validation must reject it today —
  `test_reverse_is_rejected_until_phase_two` pins that.
- **Activation from the columns tool panel.** Needs AG-Grid 36.1;
  `getColumnMenuItems()` with `params.source === "columnsToolPanel"` does not
  exist in 36.0.
- **Custom colours.** `SCHEMES` is a data structure, so adding one later is a
  row, not a redesign.
- **The consumer migration.** `hitapps_analytics` swaps its five stylers for
  `scheme="neutral"` / `"positive"` / `"diverging"` in its own repo, on its own
  change.
