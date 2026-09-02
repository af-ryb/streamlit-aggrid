# Declarative Colour Scales, Phase 2 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the built-in colour scales with a fixed-anchor mode, a best-in-population `rank` scheme, a constant `fill` scheme, the `reverse` direction flag, and an opt-in parent-scoped population — so the consumer's last four hand-written cell stylers become declarations — and ship it as 2.4.1.

**Architecture:** Every addition is one more key in the existing `context["stColorScale"]` per-key merge; Python validates, the frontend resolves the merged declaration into a `kind`-discriminated config (`ramp` / `anchor` / `rank` / `fill`) and the one built-in `cellStyle` dispatches on it. The level-scoped population walk is not edited; parent scoping is a second walk that fills every parent's cache entry in one pass. The e2e fixture stays the single owner of the reference arithmetic.

**Tech Stack:** Python 3 (hatchling, pytest), TypeScript + React (Vite, Yarn 4 via corepack), AG-Grid 36.0.0, Playwright for e2e, Node 22 for the type-stripped `__checks__`.

**Spec:** `docs/superpowers/specs/2026-09-02-color-scale-phase-2-design.md`

## Global Constraints

- **Additive.** Any declaration valid under 2.4.0 paints exactly the same colours. The level-scoped walk in `population.ts` (`row.level !== level` filter, key `${colId}:${level}:${skip}`) is **not edited**.
- **Context key:** `stColorScale`, at `gridOptions["context"]` (defaults only) and `colDef["context"]` (opt-in). Per-key shallow merge, column wins.
- **Schemes:** exactly `"neutral"`, `"positive"`, `"diverging"`, `"rank"`, `"fill"`. **Modes:** exactly `"minmax"`, `"zscore"`, `"anchor"`. **Scopes:** exactly `"level"`, `"parent"`. These literals are pinned in both languages by `test/unit/test_public_exports.py` and `__checks__/schemes.check.ts`.
- **Declaration keys:** `scheme`, `mode`, `scope`, `reverse`, `skip_non_positive`, `anchor`, `span`, `color`. Nothing else. A key a scheme does not read is **ignored, not rejected**.
- **Scheme default under `mode: "anchor"`:** `diverging`, only when no scheme resolves at either level.
- **Anchor arithmetic:** `d = clamp((value − anchor) / span, −1, 1)`; `reverse` negates `d`; `d == 0` is unpainted; alpha is the scheme's linear `alphaMin..alphaMax` ramp — never `zRamp`.
- **`rank`:** population of `count < 2` is unpainted; equality is exact; ties all paint; style is `{backgroundColor: rgba(35, 175, 40, 0.35), fontWeight: 600}` where the RGB is `SCHEMES.diverging.rgb(+1, 1)`.
- **`fill`:** paints every cell including footer and pinned rows; the colour string is passed through verbatim.
- **`scope: "parent"`:** rows whose parent is the root (`level === -1`) are neither painted nor counted by population-based kinds; `anchor` and `fill` ignore `scope`. Cache key for a parent is `JSON.stringify` of its group-key chain upward. One walk fills every parent.
- **Rounding, both languages:** `floor(x + 0.5)`; alpha emitted as `floor(alpha * 1000 + 0.5) / 1000`.
- **No AG-Grid version bump.** Stay on `36.0.0`.
- **`yarn` is not on PATH.** Always `COREPACK_ENABLE_DOWNLOAD_PROMPT=0 corepack yarn …` from `st_aggrid/frontend`.
- **e2e row addressing goes through `row-index` / `col-id`**, never DOM order.
- Fast loop: `uv run pytest -m "not e2e"`. Full e2e: `uv run pytest test/test_grid_color_scale.py` for the file, `uv run pytest` for everything.
- **Version:** both `pyproject.toml` files and `uv.lock` go to `2.4.1` in the last task; tag through `scripts/release.sh` only from `main` after merge.

---

### Task 1: Shared number predicate

`ratio.py` owns a two-line `_is_number` (int/float, not bool). The colour-scale validator needs the same rule plus finiteness. Hoist it so there is one copy.

**Files:**
- Create: `st_aggrid/_numbers.py`
- Modify: `st_aggrid/ratio.py:66-71` (delete `_NUMERIC` and `_is_number`, import instead)
- Test: `test/unit/test_numbers.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `st_aggrid._numbers.is_number(value: Any) -> bool`, `st_aggrid._numbers.is_finite_number(value: Any) -> bool`.

- [ ] **Step 1: Write the failing test**

Create `test/unit/test_numbers.py`:

```python
"""The number predicate shared by the built-in validators.

`bool` is an `int` subclass, so a plain `isinstance(x, int)` accepts `True`
as a multiplier or an anchor. Both validators need the strict rule; the
colour-scale one additionally needs finiteness, because NaN and infinity
would pass JSON serialisation and then paint nothing in the browser.
"""

from st_aggrid._numbers import is_finite_number, is_number


def test_ints_and_floats_are_numbers():
    assert is_number(1)
    assert is_number(1.5)
    assert is_number(-0.0)


def test_bools_and_strings_are_not_numbers():
    assert not is_number(True)
    assert not is_number(False)
    assert not is_number("1")
    assert not is_number(None)


def test_nan_and_infinity_are_numbers_but_not_finite():
    assert is_number(float("nan"))
    assert is_number(float("inf"))
    assert not is_finite_number(float("nan"))
    assert not is_finite_number(float("inf"))
    assert not is_finite_number(float("-inf"))


def test_finite_numbers_pass_both():
    assert is_finite_number(0)
    assert is_finite_number(-1.25)
    assert not is_finite_number(True)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest test/unit/test_numbers.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'st_aggrid._numbers'`

- [ ] **Step 3: Write the module and switch `ratio.py` to it**

Create `st_aggrid/_numbers.py`:

```python
"""Number predicates shared by the built-in validators.

``ratio.py`` and ``color_scale.py`` both need "an int or a float that is not
a bool": ``bool`` is an ``int`` subclass, so ``isinstance(x, int)`` would let
a ``True`` multiplier or anchor through as ``1``. ``color_scale.py`` also
needs finiteness — ``float("nan")`` serialises to JSON and then paints
nothing in the browser, which is the silent failure that validator exists
to prevent.
"""

from __future__ import annotations

from math import isfinite
from typing import Any


def is_number(value: Any) -> bool:
    """An ``int`` or ``float`` that is not a ``bool``."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def is_finite_number(value: Any) -> bool:
    """``is_number`` and neither NaN nor infinite."""
    return is_number(value) and isfinite(value)
```

In `st_aggrid/ratio.py`, delete these lines (currently 66–71):

```python
_NUMERIC = (int, float)


def _is_number(value: Any) -> bool:
    # bool is an int subclass; a True multiplier is a mistake, not a 1.
    return isinstance(value, _NUMERIC) and not isinstance(value, bool)
```

and add to the imports at the top of `ratio.py` (below the existing `from st_aggrid._coldefs import ...` line):

```python
from st_aggrid._numbers import is_number as _is_number
```

The five call sites in `ratio.py` (`_is_number(...)`) are unchanged.

- [ ] **Step 4: Run the unit suite to verify it passes**

Run: `uv run pytest test/unit/test_numbers.py test/unit/test_ratio_validation.py -v`
Expected: all PASS — the ratio validator's behaviour is unchanged.

- [ ] **Step 5: Commit**

```bash
git add st_aggrid/_numbers.py st_aggrid/ratio.py test/unit/test_numbers.py
git commit -m "Hoist the strict number predicate out of ratio.py into _numbers.py"
```

---

### Task 2: Python validation

Widen `color_scale.py` to the full key set and the two resolution rules, and re-export the new `COLOR_SCALE_SCOPES` constant.

**Files:**
- Modify: `st_aggrid/color_scale.py` (whole file — replacement below)
- Modify: `st_aggrid/__init__.py` (import + `__all__`)
- Test: `test/unit/test_color_scale_validation.py`, `test/unit/test_public_exports.py`

**Interfaces:**
- Consumes: `st_aggrid._numbers.is_finite_number`.
- Produces: `COLOR_SCALE_SCHEMES` (5-tuple), `COLOR_SCALE_MODES` (3-tuple), `COLOR_SCALE_SCOPES = ("level", "parent")`, `validate_color_scale_columns(grid_options) -> None` with the new rules; all four names importable from `st_aggrid`.

- [ ] **Step 1: Update the two existing tests that pin the old contract**

In `test/unit/test_color_scale_validation.py`, replace `test_constants_are_the_literals_the_frontend_uses` with:

```python
def test_constants_are_the_literals_the_frontend_uses():
    assert COLOR_SCALE_CONTEXT_KEY == "stColorScale"
    assert COLOR_SCALE_SCHEMES == ("neutral", "positive", "diverging", "rank", "fill")
    assert COLOR_SCALE_MODES == ("minmax", "zscore", "anchor")
    assert COLOR_SCALE_SCOPES == ("level", "parent")
```

and add `COLOR_SCALE_SCOPES` to the module's `from st_aggrid.color_scale import (...)` list.

Replace `test_reverse_is_rejected_until_phase_two` with:

```python
def test_reverse_is_accepted_as_a_bool():
    validate_color_scale_columns(grid_options({"scheme": "neutral", "reverse": True}))
    validate_color_scale_columns(grid_options({"scheme": "neutral", "reverse": False}))


def test_reverse_must_be_a_bool_not_an_int():
    with pytest.raises(ValueError, match="reverse"):
        validate_color_scale_columns(grid_options({"scheme": "neutral", "reverse": 1}))
```

- [ ] **Step 2: Write the failing tests for the new keys and rules**

Append to `test/unit/test_color_scale_validation.py`, before the `_merge_declaration` block:

```python
# --- Phase 2 keys -----------------------------------------------------------


def test_scope_accepts_level_and_parent():
    validate_color_scale_columns(grid_options({"scheme": "neutral", "scope": "level"}))
    validate_color_scale_columns(grid_options({"scheme": "neutral", "scope": "parent"}))


def test_unknown_scope_is_rejected():
    with pytest.raises(ValueError, match="scope"):
        validate_color_scale_columns(grid_options({"scheme": "neutral", "scope": "depth"}))


def test_anchor_mode_with_both_keys_passes():
    validate_color_scale_columns(
        grid_options({"scheme": "diverging", "mode": "anchor", "anchor": 1.0, "span": 1.0})
    )


def test_anchor_mode_defaults_the_scheme_to_diverging():
    # No scheme at either level: the one asymmetry in resolution.
    validate_color_scale_columns(grid_options({"mode": "anchor", "anchor": 1.0, "span": 1.0}))


def test_anchor_mode_without_anchor_is_rejected():
    with pytest.raises(ValueError, match="anchor"):
        validate_color_scale_columns(grid_options({"scheme": "diverging", "mode": "anchor", "span": 1.0}))


def test_anchor_mode_without_span_is_rejected():
    with pytest.raises(ValueError, match="span"):
        validate_color_scale_columns(grid_options({"scheme": "diverging", "mode": "anchor", "anchor": 1.0}))


def test_anchor_mode_resolved_through_the_grid_default_still_needs_its_keys():
    # `mode` comes from the grid level, the keys from nowhere: still an error,
    # because the *merged* declaration is what has to be complete.
    with pytest.raises(ValueError, match="anchor"):
        validate_color_scale_columns(grid_options(True, {"scheme": "diverging", "mode": "anchor"}))


def test_anchor_keys_can_come_from_the_grid_default():
    validate_color_scale_columns(
        grid_options({"scheme": "positive"}, {"mode": "anchor", "anchor": 100, "span": 40})
    )


@pytest.mark.parametrize("anchor", [True, "1", None, float("nan"), float("inf")])
def test_anchor_must_be_a_finite_number(anchor):
    with pytest.raises(ValueError, match="anchor"):
        validate_color_scale_columns(
            grid_options({"scheme": "diverging", "mode": "anchor", "anchor": anchor, "span": 1.0})
        )


@pytest.mark.parametrize("span", [0, -1, True, "1", float("nan")])
def test_span_must_be_a_positive_finite_number(span):
    with pytest.raises(ValueError, match="span"):
        validate_color_scale_columns(
            grid_options({"scheme": "diverging", "mode": "anchor", "anchor": 1.0, "span": span})
        )


def test_anchor_keys_are_type_checked_even_when_the_mode_is_not_anchor():
    # Present keys are always type-checked, at both levels; only *relevance*
    # is lenient.
    with pytest.raises(ValueError, match="span"):
        validate_color_scale_columns(grid_options({"scheme": "positive", "span": -3}))


def test_rank_scheme_passes_with_and_without_direction():
    validate_color_scale_columns(grid_options({"scheme": "rank"}))
    validate_color_scale_columns(grid_options({"scheme": "rank", "reverse": True, "scope": "parent"}))


def test_rank_ignores_an_explicit_mode():
    # `rank` reads no mode. An explicit one validates and is ignored — a
    # grid-level `mode` default must not break a rank column.
    validate_color_scale_columns(grid_options({"scheme": "rank"}, {"mode": "minmax"}))
    validate_color_scale_columns(grid_options({"scheme": "rank", "mode": "anchor"}))


def test_fill_with_a_colour_passes():
    validate_color_scale_columns(grid_options({"scheme": "fill", "color": "rgb(4, 5, 6)"}))
    validate_color_scale_columns(
        grid_options({"scheme": "fill", "color": "var(--secondary-background-color)"})
    )


def test_fill_without_a_colour_is_rejected():
    with pytest.raises(ValueError, match="color"):
        validate_color_scale_columns(grid_options({"scheme": "fill"}))


def test_fill_colour_can_come_from_the_grid_default():
    validate_color_scale_columns(grid_options({"scheme": "fill"}, {"color": "rgb(1, 2, 3)"}))


@pytest.mark.parametrize("color", ["", "   ", 7, None, ["rgb(1, 2, 3)"]])
def test_fill_colour_must_be_a_non_empty_string(color):
    with pytest.raises(ValueError, match="color"):
        validate_color_scale_columns(grid_options({"scheme": "fill", "color": color}))


def test_fill_ignores_every_population_key_from_the_grid_default():
    # The rule that keeps grid-level defaults harmless: a fill column under a
    # ramp-shaped grid default must validate.
    validate_color_scale_columns(
        grid_options(
            {"scheme": "fill", "color": "rgb(1, 2, 3)"},
            {"scheme": "diverging", "mode": "zscore", "scope": "parent",
             "skip_non_positive": True, "reverse": True},
        )
    )


def test_a_grid_level_default_may_carry_every_new_key():
    validate_color_scale_columns(
        {
            "columnDefs": [{"field": "a"}],
            "context": {
                COLOR_SCALE_CONTEXT_KEY: {
                    "scheme": "diverging", "mode": "anchor", "scope": "parent",
                    "reverse": False, "skip_non_positive": False,
                    "anchor": 1.0, "span": 1.0, "color": "rgb(0, 0, 0)",
                }
            },
        }
    )


def test_true_with_a_defaults_only_grid_entry_and_no_scheme_is_still_rejected():
    # `configure_color_scale()` with no arguments writes `{}`; a bare opt-in
    # under it resolves to nothing, exactly as with no grid entry at all.
    with pytest.raises(ValueError, match="scheme"):
        validate_color_scale_columns(grid_options(True, {}))
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest test/unit/test_color_scale_validation.py -v`
Expected: the constants test fails on the tuple lengths, every new test fails with `ValueError: ... unknown key(s)` or `ImportError` for `COLOR_SCALE_SCOPES`.

- [ ] **Step 4: Replace `st_aggrid/color_scale.py`**

Full new content:

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
it is the **merged** result that must resolve. That is how ``color_scale=True``
with no grid-level default is caught here instead of silently painting nothing
in the browser.

Two rules keep grid-level defaults harmless. Every key that is *present* is
type-checked, at both levels — a typo never survives. But a key a scheme does
not *read* is ignored, not rejected: a grid default of ``mode: "minmax"`` must
not break a column that says ``scheme: "fill"``.

The frontend implements the same resolution again, as a guard, because it has
to cope with grid options that never went through ``GridOptionsBuilder`` — but
returning ``null`` inside a cell renderer is a worse error than raising here,
so this copy is the one that talks to the developer.
"""

from __future__ import annotations

from typing import Optional

from st_aggrid._coldefs import column_label, iter_column_defs
from st_aggrid._numbers import is_finite_number

#: Where a declaration lives inside ``context``, at both levels.
COLOR_SCALE_CONTEXT_KEY = "stColorScale"

#: Scheme names. The three ramps' colours live in
#: ``frontend/src/colorScales/schemes.ts``; ``rank`` is a predicate (the best
#: value in the population) and ``fill`` a constant colour. These strings
#: must match ``schemes.ts``'s ``SCHEME_NAMES`` exactly.
COLOR_SCALE_SCHEMES = ("neutral", "positive", "diverging", "rank", "fill")

#: The schemes that run a ramp and so read ``mode``.
_RAMP_SCHEMES = ("neutral", "positive", "diverging")

#: Normalisation names, matching ``frontend/src/colorScales/normalize.ts``.
#: ``anchor`` measures deviation from a fixed value rather than from a
#: population statistic.
COLOR_SCALE_MODES = ("minmax", "zscore", "anchor")

#: What a population-based scheme is compared against: every row at the same
#: group depth (``level``), or only the row's siblings under one parent
#: (``parent``). Matches ``schemes.ts``'s ``SCOPE_NAMES``.
COLOR_SCALE_SCOPES = ("level", "parent")

#: Every key a declaration may carry.
_KNOWN_KEYS = (
    "scheme",
    "mode",
    "scope",
    "reverse",
    "skip_non_positive",
    "anchor",
    "span",
    "color",
)


def _validate_declaration(declaration: dict, where: str) -> None:
    """The rules shared by the grid-level and the column-level declaration:
    every present key has the right shape. Relevance is not checked here."""
    unknown = sorted(key for key in declaration if key not in _KNOWN_KEYS)
    if unknown:
        raise ValueError(
            f"{where}: unknown key(s) {unknown} in the colour scale "
            f"declaration. Available: {list(_KNOWN_KEYS)}."
        )

    for key, allowed in (
        ("scheme", COLOR_SCALE_SCHEMES),
        ("mode", COLOR_SCALE_MODES),
        ("scope", COLOR_SCALE_SCOPES),
    ):
        if key in declaration and declaration[key] not in allowed:
            raise ValueError(
                f"{where}['{key}'] must be one of {allowed}, got "
                f"{declaration[key]!r}."
            )

    for flag in ("reverse", "skip_non_positive"):
        # Checked against `bool` specifically: `bool` is an `int` subclass, so
        # an `isinstance(..., int)` test would accept `1`. Same trap
        # `_numbers.is_number` guards from the other direction.
        if flag in declaration and not isinstance(declaration[flag], bool):
            raise ValueError(
                f"{where}['{flag}'] must be a bool, got {declaration[flag]!r}."
            )

    if "anchor" in declaration and not is_finite_number(declaration["anchor"]):
        raise ValueError(
            f"{where}['anchor'] must be a finite number, got "
            f"{declaration['anchor']!r}."
        )

    if "span" in declaration and not (
        is_finite_number(declaration["span"]) and declaration["span"] > 0
    ):
        raise ValueError(
            f"{where}['span'] must be a finite number greater than zero, got "
            f"{declaration['span']!r}."
        )

    if "color" in declaration and not (
        isinstance(declaration["color"], str) and declaration["color"].strip()
    ):
        # No attempt to parse CSS: the browser is the only authority on what a
        # colour string means, and `var(--x)` cannot be checked from here.
        raise ValueError(
            f"{where}['color'] must be a non-empty CSS colour string, got "
            f"{declaration['color']!r}."
        )


def _merge_declaration(grid_declaration: Optional[dict], own: dict) -> dict:
    """The single place the column-over-grid-defaults rule lives: per key,
    the column's own declaration wins over the grid-level default. The
    frontend implements the same rule again in ``colorScales/index.ts``.
    """
    return {**(grid_declaration or {}), **own}


def _resolved_scheme(merged: dict) -> Optional[str]:
    """The scheme a merged declaration paints with. ``mode: "anchor"`` with no
    scheme at either level defaults to ``diverging`` — an anchored scale is
    almost always "above or below a reference" — and that is the one
    asymmetry in resolution. An explicit scheme always wins."""
    scheme = merged.get("scheme")
    if scheme is None and merged.get("mode") == "anchor":
        return "diverging"
    return scheme


def _validate_resolution(merged: dict, where: str) -> None:
    """The rules that only make sense on the merged declaration: it must
    resolve to a scheme, and that scheme's required keys must be present."""
    scheme = _resolved_scheme(merged)
    if scheme not in COLOR_SCALE_SCHEMES:
        raise ValueError(
            f"{where} resolves to no valid 'scheme'. Set one on the column, "
            f"or supply a grid-level default with "
            f"GridOptionsBuilder.configure_color_scale(scheme=...), or use "
            f"mode='anchor' (which defaults to 'diverging'). "
            f"Available: {COLOR_SCALE_SCHEMES}."
        )

    if scheme == "fill" and "color" not in merged:
        raise ValueError(
            f"{where} resolves to scheme 'fill' but no 'color'. Set one on "
            f"the column or as a grid-level default, e.g. "
            f"'var(--secondary-background-color)'."
        )

    if scheme in _RAMP_SCHEMES and merged.get("mode") == "anchor":
        missing = [key for key in ("anchor", "span") if key not in merged]
        if missing:
            raise ValueError(
                f"{where} resolves to mode 'anchor' but is missing {missing}. "
                f"An anchored scale needs the reference value ('anchor') and "
                f"the deviation that reaches full intensity ('span')."
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
        where = f"{column_label(column)}: context['{COLOR_SCALE_CONTEXT_KEY}']"

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
        _validate_resolution(_merge_declaration(grid_declaration, own), where)
```

- [ ] **Step 5: Re-export `COLOR_SCALE_SCOPES`**

In `st_aggrid/__init__.py`, extend the `from st_aggrid.color_scale import (...)` block:

```python
from st_aggrid.color_scale import (
    COLOR_SCALE_CONTEXT_KEY,
    COLOR_SCALE_MODES,
    COLOR_SCALE_SCHEMES,
    COLOR_SCALE_SCOPES,
    validate_color_scale_columns,
)
```

add `"COLOR_SCALE_SCOPES",` to `__all__` directly after `"COLOR_SCALE_SCHEMES",`, and in the module docstring change

```
``COLOR_SCALE_CONTEXT_KEY``, ``COLOR_SCALE_SCHEMES`` and ``COLOR_SCALE_MODES``
have no unprefixed aliases, and new code should not add any.
```

to

```
``COLOR_SCALE_CONTEXT_KEY``, ``COLOR_SCALE_SCHEMES``, ``COLOR_SCALE_MODES`` and
``COLOR_SCALE_SCOPES`` have no unprefixed aliases, and new code should not add
any.
```

- [ ] **Step 6: Update the public-export pins**

In `test/unit/test_public_exports.py`:

- Add `COLOR_SCALE_SCOPES` to the import list inside `test_color_scale_names_are_importable_from_the_package_root` and add the line `assert COLOR_SCALE_SCOPES is color_scale_module.COLOR_SCALE_SCOPES`.
- Replace the body of `test_color_scale_literals_match_what_the_frontend_registers_under` with:

```python
    # `colorScales/index.ts` uses "stColorScale" as its context key and
    # `colorScales/schemes.ts` exports SCHEME_NAMES / MODE_NAMES / SCOPE_NAMES
    # with these exact literals. Nothing mechanical keeps the two languages in
    # step, so they are pinned here by hand.
    assert st_aggrid.COLOR_SCALE_CONTEXT_KEY == "stColorScale"
    assert st_aggrid.COLOR_SCALE_SCHEMES == ("neutral", "positive", "diverging", "rank", "fill")
    assert st_aggrid.COLOR_SCALE_MODES == ("minmax", "zscore", "anchor")
    assert st_aggrid.COLOR_SCALE_SCOPES == ("level", "parent")
```

- Add `"COLOR_SCALE_SCOPES",` to the tuple in `test_every_public_name_is_in_dunder_all`.

- [ ] **Step 7: Run the unit suite to verify it passes**

Run: `uv run pytest -m "not e2e" -v`
Expected: all PASS, including every pre-existing colour-scale, ratio and builder test.

- [ ] **Step 8: Commit**

```bash
git add st_aggrid/color_scale.py st_aggrid/__init__.py test/unit/test_color_scale_validation.py test/unit/test_public_exports.py
git commit -m "Validate the phase 2 colour-scale keys: scope, reverse, anchor, span, color"
```

---

### Task 3: GridOptionsBuilder support

`configure_color_scale` gains the new keys as optional grid-level defaults, and `scheme` becomes optional.

**Files:**
- Modify: `st_aggrid/grid_options_builder.py:128-199` (`configure_column` docstring, `configure_color_scale`)
- Test: `test/unit/test_grid_options_builder.py`

**Interfaces:**
- Consumes: `COLOR_SCALE_CONTEXT_KEY`.
- Produces: `GridOptionsBuilder.configure_color_scale(scheme=None, mode=None, skip_non_positive=None, *, scope=None, reverse=None, anchor=None, span=None, color=None)`.

- [ ] **Step 1: Write the failing tests**

Append to `test/unit/test_grid_options_builder.py`:

```python
def test_configure_color_scale_writes_every_phase_two_key():
    gb = GridOptionsBuilder()
    gb.configure_color_scale(
        scheme="diverging", mode="anchor", skip_non_positive=False,
        scope="parent", reverse=True, anchor=1.0, span=0.5, color="rgb(1, 2, 3)",
    )
    assert gb.build()["context"][COLOR_SCALE_CONTEXT_KEY] == {
        "scheme": "diverging",
        "mode": "anchor",
        "skip_non_positive": False,
        "scope": "parent",
        "reverse": True,
        "anchor": 1.0,
        "span": 0.5,
        "color": "rgb(1, 2, 3)",
    }


def test_configure_color_scale_omits_unset_phase_two_keys():
    gb = GridOptionsBuilder()
    gb.configure_color_scale(scheme="neutral", reverse=False)
    declaration = gb.build()["context"][COLOR_SCALE_CONTEXT_KEY]
    assert declaration == {"scheme": "neutral", "reverse": False}
    for absent in ("scope", "anchor", "span", "color"):
        assert absent not in declaration


def test_configure_color_scale_scheme_is_optional():
    # `mode="anchor"` with no scheme is a complete default set — the
    # validator resolves it to `diverging`.
    gb = GridOptionsBuilder()
    gb.configure_color_scale(mode="anchor", anchor=1.0, span=1.0)
    assert gb.build()["context"][COLOR_SCALE_CONTEXT_KEY] == {
        "mode": "anchor",
        "anchor": 1.0,
        "span": 1.0,
    }


def test_configure_color_scale_with_no_arguments_writes_an_empty_default():
    gb = GridOptionsBuilder()
    gb.configure_color_scale()
    assert gb.build()["context"][COLOR_SCALE_CONTEXT_KEY] == {}


def test_configure_color_scale_keeps_scheme_positional():
    gb = GridOptionsBuilder()
    gb.configure_color_scale("positive", "minmax", False)
    assert gb.build()["context"][COLOR_SCALE_CONTEXT_KEY] == {
        "scheme": "positive",
        "mode": "minmax",
        "skip_non_positive": False,
    }
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest test/unit/test_grid_options_builder.py -v -k "phase_two or optional or no_arguments or positional"`
Expected: FAIL with `TypeError: ... unexpected keyword argument 'scope'` / `missing 1 required positional argument: 'scheme'`.

- [ ] **Step 3: Rewrite `configure_color_scale`**

Replace the whole `configure_color_scale` method in `st_aggrid/grid_options_builder.py` with:

```python
    def configure_color_scale(
        self,
        scheme: Optional[str] = None,
        mode: Optional[str] = None,
        skip_non_positive: Optional[bool] = None,
        *,
        scope: Optional[str] = None,
        reverse: Optional[bool] = None,
        anchor: Optional[float] = None,
        span: Optional[float] = None,
        color: Optional[str] = None,
    ):
        """Grid-level defaults for the built-in colour scales.

        This activates nothing on its own — a column is painted only when it
        carries its own `color_scale=` opt-in. What it does is let that opt-in
        be a bare `True` instead of repeating the scheme on every one of a
        dashboard's metric columns.

        Args:
            scheme (str, optional): "neutral", "positive", "diverging",
                "rank" or "fill". Optional because `mode="anchor"` with no
                scheme is a complete default set (it resolves to "diverging").
            mode (str, optional): "minmax", "zscore" or "anchor". Defaults to
                the scheme's own default when omitted.
            skip_non_positive (bool, optional): leave zero and negative values
                unpainted and out of the population. Defaults to the scheme's
                own default when omitted.
            scope (str, optional): "level" (every row at the same group depth,
                the default) or "parent" (only the row's siblings under one
                parent; top-level rows are then not painted).
            reverse (bool, optional): flip the direction — palest at the
                maximum, red above the mean, the minimum as the "best" rank.
            anchor (float, optional): `mode="anchor"`'s reference value.
            span (float, optional): `mode="anchor"`'s deviation that reaches
                full intensity; must be greater than zero.
            color (str, optional): `scheme="fill"`'s colour, any CSS colour
                string, e.g. "var(--secondary-background-color)".
        """
        declaration = {}
        # An unset key is omitted rather than written as None: the scheme's own
        # default has to survive, and a null would override it.
        for key, value in (
            ("scheme", scheme),
            ("mode", mode),
            ("skip_non_positive", skip_non_positive),
            ("scope", scope),
            ("reverse", reverse),
            ("anchor", anchor),
            ("span", span),
            ("color", color),
        ):
            if value is not None:
                declaration[key] = value

        context = dict(self._grid_options.get("context") or {})
        context[COLOR_SCALE_CONTEXT_KEY] = declaration
        self._grid_options["context"] = context
```

In `configure_column`'s docstring, change the `color_scale` entry's key list from `(``scheme``, ``mode``, ``skip_non_positive``)` to `(``scheme``, ``mode``, ``scope``, ``reverse``, ``skip_non_positive``, ``anchor``, ``span``, ``color``)`.

- [ ] **Step 4: Run the builder tests to verify they pass**

Run: `uv run pytest test/unit/test_grid_options_builder.py -v`
Expected: all PASS, including the four pre-existing `configure_color_scale` tests.

- [ ] **Step 5: Commit**

```bash
git add st_aggrid/grid_options_builder.py test/unit/test_grid_options_builder.py
git commit -m "GridOptionsBuilder: accept the phase 2 colour-scale keys as grid defaults"
```

---

### Task 4: Reference arithmetic fixture

The fixture owns the expected colours. It learns the `anchor` mode, `reverse`, the `rank` predicate, and a parent-scoped population helper — as an independent second implementation of the spec, never by importing the frontend.

**Files:**
- Modify: `test/color_scale_fixture.py` (rows, helpers, `expected_rgba`, new `expected_rank`, `RANK_RGBA`, `is_scheme_color`)
- Test: `test/unit/test_color_scale_fixture.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `COLOR_SCALE_ROWS` gains `"ratio"`: `0.5, 0.9, 1.0, 1.1, 1.5, 2.5`.
  - `region_values(region: str, field: str) -> list[float]`.
  - `expected_rgba(scheme_name, values, value, *, mode=None, skip_non_positive=None, reverse=False, anchor=None, span=None) -> tuple | None`.
  - `expected_rank(values, value, *, reverse=False, skip_non_positive=False) -> bool`.
  - `RANK_ALPHA = 0.35`, `RANK_RGBA = (35, 175, 40, 0.35)`.
  - `is_scheme_color(rgba, "rank")`.

- [ ] **Step 1: Write the failing unit anchors**

Append to `test/unit/test_color_scale_fixture.py`. Add `RANK_RGBA`, `expected_rank`, `region_values` to its `from color_scale_fixture import (...)` list, and `import pytest` next to the existing `import sys`:

```python
RATIO = [0.5, 0.9, 1.0, 1.1, 1.5, 2.5]


def test_the_ratio_column_straddles_an_anchor_of_one():
    assert column_values("ratio") == RATIO


def test_region_values_are_the_parent_scoped_population():
    assert region_values("EU", "metric_a") == [100.0, 200.0, 300.0]
    assert region_values("US", "metric_a") == [400.0, 500.0, 600.0]


# --- anchor mode ------------------------------------------------------------


def test_anchor_mode_measures_deviation_from_the_anchor_in_spans():
    # d = -0.5: u = 0.5, 240 - 7.5 = 232.5 -> 233; alpha 0.1 + 0.5 * 0.6
    assert expected_rgba("diverging", RATIO, 0.5, mode="anchor", anchor=1.0, span=1.0) == (233, 18, 15, 0.4)
    # d = +0.5: 190 - 7.5 = 182.5 -> 183
    assert expected_rgba("diverging", RATIO, 1.5, mode="anchor", anchor=1.0, span=1.0) == (35, 183, 40, 0.4)
    # d = -0.1 and +0.1 in floating point: 0.9 - 1.0 = -0.09999999999999998
    # and 1.1 - 1.0 = 0.10000000000000009; both channels still land on the
    # .5 boundary's rounding side the frontend's IEEE arithmetic lands on.
    assert expected_rgba("diverging", RATIO, 0.9, mode="anchor", anchor=1.0, span=1.0) == (239, 18, 15, 0.16)
    assert expected_rgba("diverging", RATIO, 1.1, mode="anchor", anchor=1.0, span=1.0) == (35, 189, 40, 0.16)


def test_anchor_mode_clamps_at_one_span():
    assert expected_rgba("diverging", RATIO, 2.5, mode="anchor", anchor=1.0, span=1.0) == (35, 175, 40, 0.7)
    # -3.0 is non-positive, so diverging's default skip would gate it before
    # the clamp is ever reached; the override is what lets the clamp show.
    assert expected_rgba(
        "diverging", RATIO, -3.0, mode="anchor", anchor=1.0, span=1.0, skip_non_positive=False
    ) == (225, 18, 15, 0.7)


def test_the_exact_anchor_is_unpainted():
    assert expected_rgba("diverging", RATIO, 1.0, mode="anchor", anchor=1.0, span=1.0) is None


def test_anchor_mode_ignores_the_population():
    # A uniform population gates every ramp; the anchor mode never looks.
    assert expected_rgba("diverging", [7.0] * 6, 0.5, mode="anchor", anchor=1.0, span=1.0) == (233, 18, 15, 0.4)


def test_anchor_mode_uses_the_linear_ramp_not_the_z_ramp():
    # At |d| = 0.5 the linear ramp gives 0.4; diverging's z-ramp at |z| = 0.5
    # would give 0.1 + 0.2 * (0.5 - 0.5) = 0.1. The spec says linear.
    assert expected_rgba("diverging", RATIO, 1.5, mode="anchor", anchor=1.0, span=1.0)[3] == 0.4


def test_anchor_mode_under_a_single_hue_scheme():
    # positive: 0.06 + 0.5 * 0.49; neutral at the clamp: 0.55.
    assert expected_rgba("positive", RATIO, 0.5, mode="anchor", anchor=1.0, span=1.0) == (29, 158, 117, 0.305)
    assert expected_rgba("neutral", RATIO, 2.5, mode="anchor", anchor=1.0, span=1.0) == (51, 120, 200, 0.55)


def test_anchor_mode_with_another_reference_frame():
    # anchor 100, span 40: 110 is d = 0.25 -> positive 0.06 + 0.25 * 0.49;
    # 90 is d = -0.25 -> 240 - 3.75 = 236.25 -> 236, alpha 0.1 + 0.25 * 0.6.
    assert expected_rgba("positive", [], 110, mode="anchor", anchor=100, span=40) == (29, 158, 117, 0.183)
    assert expected_rgba("diverging", [], 90, mode="anchor", anchor=100, span=40) == (236, 18, 15, 0.25)


def test_anchor_mode_still_applies_skip_non_positive():
    # diverging's default skip is True: a ratio of exactly 0 is unpainted.
    assert expected_rgba("diverging", RATIO, 0.0, mode="anchor", anchor=1.0, span=1.0) is None
    assert expected_rgba("diverging", RATIO, 0.0, mode="anchor", anchor=1.0, span=1.0, skip_non_positive=False) == (225, 18, 15, 0.7)


def test_anchor_mode_requires_both_keys():
    with pytest.raises(ValueError, match="anchor"):
        expected_rgba("diverging", RATIO, 0.5, mode="anchor", span=1.0)
    with pytest.raises(ValueError, match="span"):
        expected_rgba("diverging", RATIO, 0.5, mode="anchor", anchor=1.0)


# --- reverse ----------------------------------------------------------------


def test_reverse_complements_the_minmax_position():
    assert expected_rgba("positive", METRIC_A, 100, reverse=True) == (29, 158, 117, 0.55)
    assert expected_rgba("positive", METRIC_A, 600, reverse=True) == (29, 158, 117, 0.06)
    # t = 0.4 -> 0.6: 0.06 + 0.6 * 0.49
    assert expected_rgba("positive", METRIC_A, 300, reverse=True) == (29, 158, 117, 0.354)


def test_reverse_negates_the_z_score():
    assert expected_rgba("diverging", METRIC_A, 100, reverse=True) == (35, 183, 40, 0.365)
    assert expected_rgba("diverging", METRIC_A, 600, reverse=True) == (233, 18, 15, 0.365)
    # The dead zone is symmetric, so it is unchanged.
    assert expected_rgba("diverging", METRIC_A, 300, reverse=True) is None


def test_reverse_mirrors_the_anchor():
    assert expected_rgba("diverging", RATIO, 0.5, mode="anchor", anchor=1.0, span=1.0, reverse=True) == (35, 183, 40, 0.4)
    assert expected_rgba("diverging", RATIO, 2.5, mode="anchor", anchor=1.0, span=1.0, reverse=True) == (225, 18, 15, 0.7)
    assert expected_rgba("diverging", RATIO, 1.0, mode="anchor", anchor=1.0, span=1.0, reverse=True) is None


def test_reverse_flips_a_diverging_minmax_split():
    assert expected_rgba("diverging", METRIC_A, 100, mode="minmax", reverse=True) == (35, 175, 40, 0.7)
    assert expected_rgba("diverging", METRIC_A, 600, mode="minmax", reverse=True) == (225, 18, 15, 0.7)


def test_reverse_has_no_visible_effect_on_neutral_zscore():
    # neutral's hue is a function of |z| alone.
    assert expected_rgba("neutral", METRIC_A, 100, reverse=True) == expected_rgba("neutral", METRIC_A, 100)


# --- rank -------------------------------------------------------------------


def test_expected_rank_picks_the_maximum():
    assert expected_rank(METRIC_A, 600)
    assert not expected_rank(METRIC_A, 500)
    assert not expected_rank(METRIC_A, 100)


def test_expected_rank_reverse_picks_the_minimum():
    assert expected_rank(METRIC_A, 100, reverse=True)
    assert not expected_rank(METRIC_A, 600, reverse=True)


def test_expected_rank_needs_two_values():
    assert not expected_rank([5.0], 5.0)
    assert not expected_rank([], 5.0)


def test_expected_rank_paints_every_tie():
    assert expected_rank([1.0, 3.0, 3.0], 3.0)


def test_expected_rank_respects_skip_non_positive():
    assert expected_rank(METRIC_B, 40, skip_non_positive=True)
    # -5 is the minimum only while it is in the population.
    assert expected_rank(METRIC_B, -5, reverse=True)
    assert not expected_rank(METRIC_B, -5, reverse=True, skip_non_positive=True)
    assert expected_rank(METRIC_B, 10, reverse=True, skip_non_positive=True)


def test_rank_rgba_is_the_saturated_diverging_green():
    # SCHEMES.diverging.rgb(+1, 1) = (35, 190 - 15, 40), at RANK_ALPHA.
    assert RANK_RGBA == (35, 175, 40, 0.35)
    assert is_scheme_color(RANK_RGBA, "rank")
    assert not is_scheme_color((29, 158, 117, 0.35), "rank")
```

- [ ] **Step 2: Run the fixture tests to verify they fail**

Run: `uv run pytest test/unit/test_color_scale_fixture.py -v`
Expected: `ImportError` for `RANK_RGBA` / `expected_rank` / `region_values`.

- [ ] **Step 3: Extend the fixture**

In `test/color_scale_fixture.py`:

(a) Add the `ratio` column to the rows and the docstring table:

```python
COLOR_SCALE_ROWS: tuple[dict, ...] = (
    {"region": "EU", "country": "DE", "metric_a": 100, "metric_b": -5, "metric_c": 7, "ratio": 0.5},
    {"region": "EU", "country": "FR", "metric_a": 200, "metric_b": 0, "metric_c": 7, "ratio": 0.9},
    {"region": "EU", "country": "IT", "metric_a": 300, "metric_b": 10, "metric_c": 7, "ratio": 1.0},
    {"region": "US", "country": "CA", "metric_a": 400, "metric_b": 20, "metric_c": 7, "ratio": 1.1},
    {"region": "US", "country": "NY", "metric_a": 500, "metric_b": 30, "metric_c": 7, "ratio": 1.5},
    {"region": "US", "country": "TX", "metric_a": 600, "metric_b": 40, "metric_c": 7, "ratio": 2.5},
)
```

and add to the module docstring, after the `metric_c` sentence:

```
`ratio` straddles an anchor of `1.0` with a span of `1.0`: both signs, the
exact anchor (IT), and one value past the clamp (TX).
```

(b) After `region_totals`, add:

```python
def region_values(region: str, field: str = "metric_a") -> list[float]:
    """``field``'s leaf values within one region — the parent-scoped
    population of a grid that row-groups by region."""
    return [float(row[field]) for row in COLOR_SCALE_ROWS if row[ROW_DIM] == region]
```

(c) Under `# Schemes`, after `SCHEMES`, add:

```python
#: `rank`'s single highlight: the saturated end of diverging's green, at a
#: fixed alpha. Derived, not typed, so it cannot drift from the ramp.
RANK_ALPHA = 0.35
```

(d) Replace `expected_rgba` with the version below (the `_rgb` helper is new; `stats` and `population` are unchanged):

```python
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
```

(e) Extend `is_scheme_color` — replace its last three lines with:

```python
    if scheme_name == "neutral":
        return (r, g, b) == (51, 120, 200)
    if scheme_name == "positive":
        return (r, g, b) == (29, 158, 117)
    if scheme_name == "rank":
        return (r, g, b) == RANK_RGBA[:3]
    return (g == 18 and b == 15) or (r == 35 and b == 40)
```

- [ ] **Step 4: Run the fixture tests to verify they pass**

Run: `uv run pytest test/unit/test_color_scale_fixture.py -v`
Expected: all PASS, the pre-existing anchors included — none of the 2.4.0 branches changed.

- [ ] **Step 5: Commit**

```bash
git add test/color_scale_fixture.py test/unit/test_color_scale_fixture.py
git commit -m "Fixture: anchor mode, reverse, the rank predicate and a parent-scoped population"
```

---

### Task 5: Pure frontend arithmetic

`schemes.ts` and `normalize.ts` stay import-free; their `node` checks are the test cycle.

**Files:**
- Modify: `st_aggrid/frontend/src/colorScales/schemes.ts`
- Modify: `st_aggrid/frontend/src/colorScales/normalize.ts` (append `anchorD`)
- Test: `st_aggrid/frontend/src/colorScales/__checks__/schemes.check.ts`, `__checks__/normalize.check.ts`

**Interfaces:**
- Consumes: nothing.
- Produces (from `schemes.ts`): `RampSchemeName`, `SchemeName`, `ColorScaleMode = "minmax" | "zscore" | "anchor"`, `RampMode = "minmax" | "zscore"`, `PopulationScope = "level" | "parent"`, `SCHEME_NAMES`, `MODE_NAMES`, `SCOPE_NAMES`, `SCHEMES: Record<RampSchemeName, Scheme>` (with `Scheme.defaultMode: RampMode`), `isRampScheme(name: unknown): name is RampSchemeName`, `RANK_ALPHA`, `RANK_STYLE: { backgroundColor: string; fontWeight: number }`, `colorFor` accepting `mode: "anchor"`.
- Produces (from `normalize.ts`): `anchorD(anchor: number, span: number, value: number): number`.

- [ ] **Step 1: Write the failing checks**

Append to `__checks__/normalize.check.ts` before the final `console.log`, and add `anchorD` to its import from `"../normalize.ts"`:

```ts
// Anchored deviation, in spans, clamped. The sign survives; the exact anchor
// is 0 and `index.ts` leaves it unpainted.
assert.equal(anchorD(1, 1, 0.5), -0.5)
assert.equal(anchorD(1, 1, 1.5), 0.5)
assert.equal(anchorD(1, 1, 1), 0)
assert.equal(anchorD(1, 1, 2.5), 1) // clamped
assert.equal(anchorD(1, 1, -3), -1) // clamped
assert.equal(anchorD(1, 0.5, 1.25), 0.5) // span scales the deviation
assert.equal(anchorD(100, 40, 110), 0.25)
```

In `__checks__/schemes.check.ts`, change the import to

```ts
import {
  MODE_NAMES,
  RANK_STYLE,
  SCHEME_NAMES,
  SCHEMES,
  SCOPE_NAMES,
  colorFor,
  isRampScheme,
} from "../schemes.ts"
```

replace the two `assert.deepEqual(SCHEME_NAMES, ...)` / `assert.deepEqual(MODE_NAMES, ...)` lines with

```ts
assert.deepEqual(SCHEME_NAMES, ["neutral", "positive", "diverging", "rank", "fill"])
assert.deepEqual(MODE_NAMES, ["minmax", "zscore", "anchor"])
assert.deepEqual(SCOPE_NAMES, ["level", "parent"])
```

and append before the final `console.log`:

```ts
// Anchor mode: `raw` is the clamped signed deviation, `intensity` its
// magnitude, and alpha is the scheme's *linear* ramp — never `zRamp`. The
// same numbers `test/unit/test_color_scale_fixture.py` pins.
const anchor = (raw: number) => ({ mode: "anchor" as const, raw, intensity: Math.abs(raw) })

assert.equal(colorFor(SCHEMES.diverging, anchor(-0.5)), "rgba(233, 18, 15, 0.4)")
assert.equal(colorFor(SCHEMES.diverging, anchor(0.5)), "rgba(35, 183, 40, 0.4)")
assert.equal(colorFor(SCHEMES.diverging, anchor(1)), "rgba(35, 175, 40, 0.7)")
assert.equal(colorFor(SCHEMES.diverging, anchor(-1)), "rgba(225, 18, 15, 0.7)")
// zRamp provably not consulted: diverging's z-ramp at |z| = 0.5 is 0.1, the
// linear ramp at u = 0.5 is 0.4. The line above holds 0.4.
assert.equal(colorFor(SCHEMES.diverging, anchor(-0.09999999999999998)), "rgba(239, 18, 15, 0.16)")
assert.equal(colorFor(SCHEMES.diverging, anchor(0.10000000000000009)), "rgba(35, 189, 40, 0.16)")
assert.equal(colorFor(SCHEMES.positive, anchor(-0.5)), "rgba(29, 158, 117, 0.305)")
assert.equal(colorFor(SCHEMES.positive, anchor(0.25)), "rgba(29, 158, 117, 0.183)")
assert.equal(colorFor(SCHEMES.neutral, anchor(1)), "rgba(51, 120, 200, 0.55)")
assert.equal(colorFor(SCHEMES.neutral, anchor(-0.5)), "rgba(51, 120, 200, 0.315)")

// rank's highlight is derived from diverging's saturated green.
assert.deepEqual(RANK_STYLE, { backgroundColor: "rgba(35, 175, 40, 0.35)", fontWeight: 600 })

// The ramp predicate must not be fooled by Object.prototype.
assert.ok(isRampScheme("neutral"))
assert.ok(!isRampScheme("rank"))
assert.ok(!isRampScheme("fill"))
assert.ok(!isRampScheme("toString"))
assert.ok(!isRampScheme(undefined))
```

- [ ] **Step 2: Run the checks to verify they fail**

```bash
node st_aggrid/frontend/src/colorScales/__checks__/normalize.check.ts
node st_aggrid/frontend/src/colorScales/__checks__/schemes.check.ts
```
Expected: both fail — `anchorD` is not exported; `RANK_STYLE` / `SCOPE_NAMES` / `isRampScheme` are not exported.

- [ ] **Step 3: Add `anchorD` to `normalize.ts`**

Append to `st_aggrid/frontend/src/colorScales/normalize.ts`:

```ts
/** Signed deviation from a fixed anchor, in units of `span`, clamped into
 * `[-1, 1]`. The `anchor` mode's whole reference frame: no population, no
 * statistics. The exact anchor is `0`, and `index.ts` leaves it unpainted —
 * "no deviation" must not read as a faint colour in either direction. */
export function anchorD(anchor: number, span: number, value: number): number {
  const d = (value - anchor) / span
  return d < -1 ? -1 : d > 1 ? 1 : d
}
```

- [ ] **Step 4: Rewrite `schemes.ts`**

Replace the type block, the names, the `Normalized` and `Scheme` interfaces, and `colorFor` in `st_aggrid/frontend/src/colorScales/schemes.ts`. Full new file content (the three `SCHEMES` entries are unchanged and repeated verbatim):

```ts
/** The three built-in palettes, and the two non-ramp schemes.
 *
 * Each ramp reproduces one of the hand-written stylers the feature first
 * replaced, exactly: `neutral` the blue statistical wash from `funnel_saj`,
 * `positive` the green min/max ramp from `payers_intelligence`, `diverging`
 * the red/green split from the cohort report. `rank` (the best value in a
 * population, and nothing else) and `fill` (one constant colour) are not
 * palettes; they are listed in `SCHEME_NAMES` so Python and the frontend
 * agree on the full set, and resolved in `index.ts`.
 *
 * Two invariants hold for all three ramps. The fill is always `rgba(...)`
 * over the cell's own background and never an opaque colour — an opaque
 * ramp paints a light cell under the dark theme's light text and the number
 * disappears, which is a bug that already shipped once. And `diverging`
 * reaches alpha 0.7, above the 0.55 the other two stop at; that is what the
 * cohort report draws today, and it stays a named endpoint here so changing
 * it later is one edit.
 *
 * Imports nothing, so `__checks__/schemes.check.ts` can run it under `node`.
 */

export type RampSchemeName = "neutral" | "positive" | "diverging"
export type SchemeName = RampSchemeName | "rank" | "fill"
/** The modes a ramp scheme runs in. `anchor` consults no population. */
export type ColorScaleMode = "minmax" | "zscore" | "anchor"
/** The population-based modes — the only ones a scheme can default to. */
export type RampMode = "minmax" | "zscore"
/** What a population-based scheme is compared against. */
export type PopulationScope = "level" | "parent"

/** Must stay in step with `st_aggrid/color_scale.py`'s COLOR_SCALE_SCHEMES /
 * COLOR_SCALE_MODES / COLOR_SCALE_SCOPES, which
 * `test/unit/test_public_exports.py` pins. */
export const SCHEME_NAMES: readonly SchemeName[] = [
  "neutral",
  "positive",
  "diverging",
  "rank",
  "fill",
]
export const MODE_NAMES: readonly ColorScaleMode[] = ["minmax", "zscore", "anchor"]
export const SCOPE_NAMES: readonly PopulationScope[] = ["level", "parent"]

export interface Normalized {
  mode: ColorScaleMode
  /** `minmax`: `t` in `[0, 1]`. `zscore`: the signed z. `anchor`: the
   * clamped signed deviation `d` in `[-1, 1]`. */
  raw: number
  /** `zscore`: `zIntensity(z)`. `anchor`: `|d|`. Ignored under `minmax`,
   * where the intensity depends on whether the scheme is diverging and so is
   * derived from `raw` here. */
  intensity: number
}

export interface Scheme {
  name: RampSchemeName
  defaultMode: RampMode
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
   * population modes. Never consulted under `anchor`: a z-ramp is a z-score
   * shape and has no meaning on a linear deviation. */
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

export const SCHEMES: Record<RampSchemeName, Scheme> = {
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

/** Whether a declaration's scheme name is one of the three ramps. An own-
 * property check, not `in`: `"toString" in SCHEMES` is true. */
export function isRampScheme(name: unknown): name is RampSchemeName {
  return typeof name === "string" && Object.prototype.hasOwnProperty.call(SCHEMES, name)
}

/** `rank`'s single highlight: the saturated end of `diverging`'s green at a
 * fixed alpha, plus the bold weight the styler it replaces used. Derived from
 * the scheme rather than typed, so the two cannot drift. */
export const RANK_ALPHA = 0.35
export const RANK_STYLE: Readonly<{ backgroundColor: string; fontWeight: number }> = (() => {
  const [r, g, b] = SCHEMES.diverging.rgb(1, 1)
  return Object.freeze({ backgroundColor: `rgba(${r}, ${g}, ${b}, ${RANK_ALPHA})`, fontWeight: 600 })
})()

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
    // zscore and anchor alike: intensity is precomputed, sign is raw's.
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

- [ ] **Step 5: Run the checks to verify they pass**

```bash
node st_aggrid/frontend/src/colorScales/__checks__/normalize.check.ts
node st_aggrid/frontend/src/colorScales/__checks__/schemes.check.ts
```
Expected: `normalize.check.ts ok` and `schemes.check.ts ok`.

`index.ts` does **not** compile untouched at this point: its `SCHEMES[merged.scheme]` indexes a `Record<RampSchemeName, Scheme>` with a value that may now be `"rank" | "fill"`. Make the one-line interim fix — guard the lookup with `isRampScheme(merged.scheme)` and return `null` otherwise — so that

```bash
cd st_aggrid/frontend && COREPACK_ENABLE_DOWNLOAD_PROMPT=0 corepack yarn tsc --noEmit
```
is silent. Task 6 replaces that whole section of `index.ts`, so keep the fix minimal.

- [ ] **Step 6: Commit**

```bash
git add st_aggrid/frontend/src/colorScales/schemes.ts st_aggrid/frontend/src/colorScales/normalize.ts st_aggrid/frontend/src/colorScales/__checks__/
git commit -m "schemes.ts: rank and fill names, anchor mode, RANK_STYLE; normalize.ts: anchorD"
```

---

### Task 6: Frontend wiring and the first painted grid

Resolution into a `kind`-discriminated config, the parent-scoped population, the cell-style dispatch — and the e2e app's grid 5 as the failing test that drives it.

**Files:**
- Modify: `st_aggrid/frontend/src/colorScales/population.ts` (whole file)
- Modify: `st_aggrid/frontend/src/colorScales/index.ts` (everything above `callerCellStyleSource`; the rest is unchanged)
- Modify: `test/grid_color_scale.py` (append grid 5; the `<style>` for the CSS variable)
- Modify: `test/test_grid_color_scale.py` (`go_to_app` wait, new constants, grid-5 tests)
- Rebuild: `st_aggrid/frontend/build/` (delete + add of the hashed bundle)

**Interfaces:**
- Consumes: Task 5's exports; Task 4's fixture.
- Produces:
  - `population.ts`: `statsFor(api: GridApi, column: Column, node: IRowNode, scope: PopulationScope, skipNonPositive: boolean): Stats | null`, `isTopLevel(node: IRowNode): boolean`, `parentPath(node: IRowNode): string`, `extractValue`, `clearStats` (unchanged).
  - `index.ts`: `ResolvedColorScale` union with `kind: "ramp" | "anchor" | "rank" | "fill"`, `readColorScaleConfig`, `stColorScaleCellStyle(params): CellStyle | null`; `registerColorScales`, `attachColorScaleInvalidation`, `clearStats` re-export unchanged.

- [ ] **Step 1: Add grid 5 to the e2e app**

In `test/grid_color_scale.py`, update the module docstring's list (after the `4` entry):

```
  5  flat, phase 2 — `mode: "anchor"` under three schemes and with the
     scheme defaulted, `reverse` under every mode, `rank` in both directions,
     and `fill` from a literal and from a CSS variable.
  6  row-grouped by region with a grand total, phase 2 — `scope: "parent"`
     against `scope: "level"` side by side, for a ramp and for `rank`, plus a
     `fill` that must reach the grand total. A floating number filter on
     `metric_b` is what the parent-scope stability test drives.
```

and change `Grids 0-2 keep their indices so no existing assertion moves when 3 and 4 are added.` to `Grids keep their indices; a new grid is always appended.`

Append at the end of the file:

```python
# The CSS variable `fill_var` below resolves. Streamlit renders this `<style>`
# into the page itself (CCv2, no iframe), so `:root` is the grid's own root —
# the same way the consumer's `--secondary-background-color` reaches a cell.
st.markdown(
    "<style>:root { --st-aggrid-test-fill: rgb(7, 8, 9); }</style>",
    unsafe_allow_html=True,
)

st.subheader("Phase 2 — anchor, reverse, rank, fill")
ANCHOR = {"mode": "anchor", "anchor": 1.0, "span": 1.0}
AgGrid(
    df,
    grid_options={
        **COMMON_OPTIONS,
        "columnDefs": [
            {"colId": ROW_DIM, "field": ROW_DIM},
            {"colId": LEAF_DIM, "field": LEAF_DIM},
            metric_column("anchor_div", "ratio", "anchor", {"scheme": "diverging", **ANCHOR}),
            # No scheme at either level: resolution defaults it to diverging.
            metric_column("anchor_default", "ratio", "anchor/default", dict(ANCHOR)),
            metric_column(
                "anchor_rev", "ratio", "anchor/reverse",
                {"scheme": "diverging", "reverse": True, **ANCHOR},
            ),
            metric_column("anchor_pos", "ratio", "anchor/positive", {"scheme": "positive", **ANCHOR}),
            metric_column(
                "rev_minmax", "metric_a", "positive/reverse",
                {"scheme": "positive", "reverse": True},
            ),
            metric_column(
                "rev_zscore", "metric_a", "diverging/reverse",
                {"scheme": "diverging", "reverse": True},
            ),
            metric_column("rank_max", "metric_a", "rank", {"scheme": "rank"}),
            metric_column("rank_min", "metric_a", "rank/reverse", {"scheme": "rank", "reverse": True}),
            metric_column("fill_lit", "metric_a", "fill", {"scheme": "fill", "color": "rgb(4, 5, 6)"}),
            metric_column(
                "fill_var", "metric_a", "fill/var",
                {"scheme": "fill", "color": "var(--st-aggrid-test-fill)"},
            ),
        ],
    },
    enable_enterprise_modules=True,
    height=320,
    key="color_scale_phase2_flat",
)
```

- [ ] **Step 2: Write the failing e2e tests for grid 5**

In `test/test_grid_color_scale.py`:

(a) Extend the imports from `color_scale_fixture` with `RANK_RGBA`, `expected_rank`, `region_values`.

(b) Add constants after `DEFAULT_CELLSTYLE_GRID = 4`:

```python
PHASE2_FLAT_GRID = 5
SCOPE_GRID = 6

RATIO = column_values("ratio")
ANCHOR_1 = dict(mode="anchor", anchor=1.0, span=1.0)
```

(c) In `go_to_app`, change the wrapper count in the `wait_for_function` from `>= 5` to `>= 6`. (Task 7 raises it to `>= 7` and adds grid 6's own settle wait.)

(d) Add a helper after `assert_unpainted`:

```python
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
```

(e) Append the grid-5 tests at the end of the file:

```python
# --- Phase 2: grid 5 ----------------------------------------------------------


@pytest.mark.parametrize(
    "col_id,scheme,reverse",
    [
        ("anchor_div", "diverging", False),
        ("anchor_default", "diverging", False),
        ("anchor_rev", "diverging", True),
        ("anchor_pos", "positive", False),
    ],
)
def test_anchor_mode_paints_deviation_from_a_fixed_anchor(page: Page, col_id, scheme, reverse):
    """`ratio` against anchor 1.0, span 1.0: DE and FR below, IT exactly on
    the anchor (unpainted), CA and NY above, TX past the clamp. `anchor_default`
    names no scheme anywhere and must resolve to diverging."""
    painted = cell_backgrounds(page, PHASE2_FLAT_GRID)
    for key, value in zip(FLAT_ROWS, RATIO):
        expected = expected_rgba(scheme, RATIO, value, reverse=reverse, **ANCHOR_1)
        actual = painted[key][col_id]
        if expected is None:
            assert_unpainted(actual, scheme, f"{key}: {col_id}")
        else:
            assert_painted(actual, expected, f"{key}: {col_id}")
    # The exact anchor, pinned explicitly: the gate whose absence would still
    # produce a plausible faint colour.
    assert_unpainted(painted["body:2"][col_id], scheme, f"body:2 (1.0): {col_id}")


def test_anchor_mode_clamps_past_one_span(page: Page):
    painted = cell_backgrounds(page, PHASE2_FLAT_GRID)
    # TX is 2.5 — d = 1.5 before the clamp — and must paint exactly what a
    # value one span above the anchor paints.
    clamped = expected_rgba("diverging", RATIO, 2.5, **ANCHOR_1)
    assert clamped == expected_rgba("diverging", RATIO, 2.0, **ANCHOR_1)
    assert_painted(painted["body:5"]["anchor_div"], clamped, "TX clamped")


def test_reverse_complements_a_minmax_ramp(page: Page):
    painted = cell_backgrounds(page, PHASE2_FLAT_GRID)
    for key, value in zip(FLAT_ROWS, METRIC_A):
        assert_painted(
            painted[key]["rev_minmax"],
            expected_rgba("positive", METRIC_A, value, reverse=True),
            f"{key}: rev_minmax",
        )
    # DE is now the darkest, TX the palest — the opposite of `pos_minmax`.
    assert painted["body:0"]["rev_minmax"][3] > painted["body:5"]["rev_minmax"][3]


def test_reverse_negates_a_zscore_ramp(page: Page):
    painted = cell_backgrounds(page, PHASE2_FLAT_GRID)
    for key, value in zip(FLAT_ROWS, METRIC_A):
        expected = expected_rgba("diverging", METRIC_A, value, reverse=True)
        actual = painted[key]["rev_zscore"]
        if expected is None:
            assert_unpainted(actual, "diverging", f"{key}: rev_zscore")
        else:
            assert_painted(actual, expected, f"{key}: rev_zscore")
    # DE (100, below the mean) now wears the hue TX wears unreversed, and
    # vice versa — the flip, spelled out without a literal.
    assert painted["body:0"]["rev_zscore"][:3] == expected_rgba("diverging", METRIC_A, 600)[:3]
    assert painted["body:5"]["rev_zscore"][:3] == expected_rgba("diverging", METRIC_A, 100)[:3]


def test_rank_paints_only_the_maximum(page: Page):
    painted = cell_backgrounds(page, PHASE2_FLAT_GRID)
    for key, value in zip(FLAT_ROWS, METRIC_A):
        if expected_rank(METRIC_A, value):
            assert_painted(painted[key]["rank_max"], RANK_RGBA, f"{key}: rank_max")
        else:
            assert_unpainted(painted[key]["rank_max"], "rank", f"{key}: rank_max")
    assert font_weight(page, PHASE2_FLAT_GRID, 5, "rank_max") == "600"
    assert font_weight(page, PHASE2_FLAT_GRID, 4, "rank_max") == "400"


def test_rank_reverse_paints_only_the_minimum(page: Page):
    painted = cell_backgrounds(page, PHASE2_FLAT_GRID)
    for key, value in zip(FLAT_ROWS, METRIC_A):
        if expected_rank(METRIC_A, value, reverse=True):
            assert_painted(painted[key]["rank_min"], RANK_RGBA, f"{key}: rank_min")
        else:
            assert_unpainted(painted[key]["rank_min"], "rank", f"{key}: rank_min")
    assert font_weight(page, PHASE2_FLAT_GRID, 0, "rank_min") == "600"


def test_fill_paints_every_row_with_the_literal_colour(page: Page):
    painted = cell_backgrounds(page, PHASE2_FLAT_GRID)
    for key in FLAT_ROWS:
        assert_painted(painted[key]["fill_lit"], (4, 5, 6, 1.0), f"{key}: fill_lit")


def test_fill_resolves_a_css_variable_through_the_host_page(page: Page):
    """`var(--st-aggrid-test-fill)` is set on `:root` by the app; the fill
    passes the string through and the browser resolves it — the same path the
    consumer's `--secondary-background-color` takes under CCv2's no-iframe
    delivery."""
    painted = cell_backgrounds(page, PHASE2_FLAT_GRID)
    for key in FLAT_ROWS:
        assert_painted(painted[key]["fill_var"], (7, 8, 9, 1.0), f"{key}: fill_var")
```

- [ ] **Step 3: Run the new tests to verify they fail**

Run: `uv run pytest test/test_grid_color_scale.py -k "anchor or reverse or rank or fill" -v`
Expected: every new test fails — the committed bundle does not know `rank`, `fill` or `anchor`, so those columns render unpainted (the old `readColorScaleConfig` returns `null` for an unknown scheme and treats `mode: "anchor"` as a z-score). Pre-existing tests still pass, because Python validation already accepts the new keys after Task 2.

- [ ] **Step 4: Rewrite `population.ts`**

Full new content:

```ts
import type { Column, GridApi, IRowNode } from "ag-grid-community"
import { popStats, Stats } from "./normalize"
import type { PopulationScope } from "./schemes"

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

/** Whether a row's parent is the root — a top-level group, or a leaf of a
 * flat grid. Under `scope: "parent"` such rows are neither painted nor
 * counted: they *are* the groups, and comparing them across is what a
 * consumer choosing that scope is declining to do. */
export function isTopLevel(node: IRowNode): boolean {
  return !node.parent || node.parent.level < 0
}

/** The chain of group keys from `group` upward, stopping at the root, as one
 * string. Stable for the life of a model generation, unlike `node.id`, which
 * is not guaranteed to survive every rebuild; unambiguous because the keys
 * are JSON-encoded rather than joined on a separator a key could contain.
 * Group keys are unique among siblings and each level groups on one field,
 * so the chain identifies a parent exactly. */
function groupPath(group: IRowNode | null): string {
  const keys: (string | null)[] = []
  for (let p = group; p && p.level >= 0; p = p.parent) keys.push(p.key)
  return JSON.stringify(keys)
}

/** The cache-key half of a row's parent identity. The root's path is `[]`. */
export function parentPath(node: IRowNode): string {
  return groupPath(node.parent)
}

/** Per-grid statistics for the current model generation, keyed by column,
 * scope and skip rule. A `WeakMap` so a destroyed grid's entry goes with it. */
const statsCache = new WeakMap<GridApi, Map<string, Stats | null>>()

/** Drop everything cached for one grid. Called when the model changes. */
export function clearStats(api: GridApi): void {
  statsCache.delete(api)
}

function cacheFor(api: GridApi): Map<string, Stats | null> {
  let byKey = statsCache.get(api)
  if (!byKey) {
    byKey = new Map()
    statsCache.set(api, byKey)
  }
  return byKey
}

/**
 * The population statistics for one column in one scope, computed once per
 * model generation.
 *
 * `scope: "level"` — the 2.4.0 rule, on the 2.4.0 code: every row at the same
 * `node.level`. Deliberately level-scoped: a group row's aggregate and a
 * leaf's own value are not comparable quantities, and pooling them lets a
 * group total set the maximum and wash every leaf out.
 *
 * `scope: "parent"` — only the row's siblings under the same parent. A miss
 * runs one walk and fills the entry for *every* parent at once (see
 * `fillParentStats`), so a generation costs one pass per painted column in
 * either scope, not one pass per group.
 *
 * Values are read through `api.getCellValue` rather than
 * `row.data[colId]` / `row.aggData[colId]`: that resolves `field`,
 * `valueGetter` and pivot result columns the way the grid itself does, so a
 * column whose `colId` differs from its `field` is not silently blank.
 *
 * `skipNonPositive` *is* part of the cache key, even though it's fixed by
 * the resolved declaration for a given `colId` at any one instant: the
 * declaration is re-read per call (see `index.ts`'s `stColorScaleCellStyle`),
 * so within one grid's life the same `colId` can resolve to either skip rule
 * across a config-only rerun — a Streamlit rerun that flips
 * `skip_non_positive` on an existing column never changes `colId`. Keying on
 * `colId` alone would let the old rule's population survive under the new
 * one until some unrelated model change happened to clear the cache.
 */
export function statsFor(
  api: GridApi,
  column: Column,
  node: IRowNode,
  scope: PopulationScope,
  skipNonPositive: boolean
): Stats | null {
  const byKey = cacheFor(api)
  const colId = column.getColId()

  if (scope === "parent") {
    const key = `${colId}:P${parentPath(node)}:${skipNonPositive}`
    if (byKey.has(key)) return byKey.get(key) ?? null
    fillParentStats(api, column, colId, skipNonPositive, byKey)
    // A parent with no qualifying values got no entry from the walk. Memoise
    // the "no population" answer under the requested key so the next cell of
    // the same parent does not walk again.
    if (!byKey.has(key)) byKey.set(key, null)
    return byKey.get(key) ?? null
  }

  // `has`, not truthiness: `null` — "this column has no population at this
  // level" — is a stable answer for the generation and is memoised too.
  const level = node.level
  const key = `${colId}:${level}:${skipNonPositive}`
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

/** One pass over the model that buckets every qualifying row's value by its
 * parent and writes one `Stats` per parent into the cache. Top-level rows
 * (parent is the root) are skipped, per `isTopLevel`. */
function fillParentStats(
  api: GridApi,
  column: Column,
  colId: string,
  skipNonPositive: boolean,
  byKey: Map<string, Stats | null>
): void {
  const buckets = new Map<IRowNode, number[]>()
  api.forEachNodeAfterFilterAndSort((row: IRowNode) => {
    if (row.footer || row.rowPinned != null) return
    if (isTopLevel(row)) return
    const value = extractValue(api.getCellValue({ rowNode: row, colKey: column }))
    if (value === null) return
    if (skipNonPositive && value <= 0) return
    const parent = row.parent as IRowNode
    let values = buckets.get(parent)
    if (!values) {
      values = []
      buckets.set(parent, values)
    }
    values.push(value)
  })

  for (const [parent, values] of buckets) {
    byKey.set(`${colId}:P${groupPath(parent)}:${skipNonPositive}`, popStats(values))
  }
}
```

- [ ] **Step 5: Rewrite the top of `index.ts`**

Replace everything in `st_aggrid/frontend/src/colorScales/index.ts` from the first line down to (but not including) the `/** Where a caller-supplied `cellStyle` ...` doc comment above `callerCellStyleSource` with:

```ts
import type {
  CellClassParams,
  CellStyle,
  Column,
  ColDef,
  GridApi,
  GridOptions,
} from "ag-grid-community"
import { eachColDef } from "../aggFuncs/foldSums"
import { anchorD, minmaxT, zIntensity, zScore } from "./normalize"
import {
  PopulationScope,
  RANK_STYLE,
  RampMode,
  SCHEMES,
  Scheme,
  colorFor,
  isRampScheme,
} from "./schemes"
import { clearStats, extractValue, isTopLevel, statsFor } from "./population"

// Re-exported so `AgGridComponent.tsx` can invalidate the statistics cache
// ahead of a `redrawRows()` that is not preceded by `modelUpdated` — see
// `attachColorScaleInvalidation` below for the event-driven case, and the
// call sites in `AgGridComponent.tsx` for the config-only-rerun case this
// covers instead.
export { clearStats }

/** The key a declaration lives under inside `context`, at both levels.
 * Matches `st_aggrid/color_scale.py`'s COLOR_SCALE_CONTEXT_KEY. */
export const ST_COLOR_SCALE = "stColorScale"

/** The raw, merged declaration. Every key optional; the shape Python's
 * validator accepts. */
interface Declaration {
  scheme?: unknown
  mode?: unknown
  scope?: unknown
  reverse?: unknown
  skip_non_positive?: unknown
  anchor?: unknown
  span?: unknown
  color?: unknown
}

/**
 * What a declaration resolves to. Discriminated on `kind` so the cell-style
 * function dispatches on one field and the compiler — not a runtime check —
 * guarantees a `fill` never reaches `statsFor` and an `anchor` always carries
 * its two numbers.
 */
export type ResolvedColorScale =
  | {
      kind: "ramp"
      scheme: Scheme
      mode: RampMode
      scope: PopulationScope
      reverse: boolean
      skipNonPositive: boolean
    }
  | {
      kind: "anchor"
      scheme: Scheme
      reverse: boolean
      skipNonPositive: boolean
      anchor: number
      span: number
    }
  | { kind: "rank"; scope: PopulationScope; reverse: boolean; skipNonPositive: boolean }
  | { kind: "fill"; color: string }

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value)
}

/**
 * Merge a column's declaration over the grid-level defaults and resolve it.
 *
 * A column is painted only when its own colDef carries an entry that is not
 * `false`; the grid level supplies defaults and never activates anything. The
 * merge is per key with the column winning. A key the resolved scheme does
 * not read is ignored — a grid default of `mode: "minmax"` must not switch
 * off a `fill` column.
 *
 * `mode: "anchor"` with no scheme at either level resolves to `diverging`:
 * the one asymmetry, because an anchored scale is almost always "above or
 * below a reference". An explicit scheme always wins.
 *
 * Python's `validate_color_scale_columns` implements the same rules and is
 * the copy that produces an actionable error. This one exists because grid
 * options do not always come from `GridOptionsBuilder`, and returning `null`
 * inside a cell renderer is a better failure than throwing there.
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
  const merged = { ...base, ...overrides } as Declaration

  const schemeName =
    merged.scheme ?? (merged.mode === "anchor" ? "diverging" : undefined)

  if (schemeName === "fill") {
    return typeof merged.color === "string" && merged.color.trim() !== ""
      ? { kind: "fill", color: merged.color }
      : null
  }

  const scope: PopulationScope = merged.scope === "parent" ? "parent" : "level"
  const reverse = merged.reverse === true

  if (schemeName === "rank") {
    return {
      kind: "rank",
      scope,
      reverse,
      skipNonPositive: merged.skip_non_positive === true,
    }
  }

  if (!isRampScheme(schemeName)) return null
  const scheme = SCHEMES[schemeName]
  const skipNonPositive =
    typeof merged.skip_non_positive === "boolean"
      ? merged.skip_non_positive
      : scheme.defaultSkipNonPositive
  const mode: unknown = merged.mode ?? scheme.defaultMode

  if (mode === "anchor") {
    const { anchor, span } = merged
    if (!isFiniteNumber(anchor) || !isFiniteNumber(span) || span <= 0) return null
    return { kind: "anchor", scheme, reverse, skipNonPositive, anchor, span }
  }
  // Positive equality narrows `unknown` to the two literals; a negative
  // early return would leave `mode` as `unknown` for the object below.
  if (mode === "minmax" || mode === "zscore") {
    return { kind: "ramp", scheme, mode, scope, reverse, skipNonPositive }
  }
  return null
}

/** The built-in `cellStyle`. Returns `null` — not `{}` — for an unpainted cell,
 * so the theme paints it as it normally would.
 *
 * `fill` is answered before the footer/pinned guard the other kinds share: a
 * fill marks a column as structural, and a stripe that stopped at the grand
 * total would be a visible regression against the styler it replaces. */
export function stColorScaleCellStyle(params: CellClassParams): CellStyle | null {
  const config = readColorScaleConfig(params.colDef, params.context)
  if (!config) return null
  if (config.kind === "fill") return { backgroundColor: config.color }

  const node = params.node
  if (!node || node.footer || node.rowPinned != null) return null

  const value = extractValue(params.value)
  if (value === null) return null
  if (config.skipNonPositive && value <= 0) return null

  if (config.kind === "anchor") {
    let d = anchorD(config.anchor, config.span, value)
    if (config.reverse) d = -d
    // `-0 === 0`, so a reversed exact anchor stays unpainted too.
    if (d === 0) return null
    return {
      backgroundColor: colorFor(config.scheme, { mode: "anchor", raw: d, intensity: Math.abs(d) }),
    }
  }

  // Population-based from here on. Under parent scope a top-level row has no
  // siblings to be compared with — it is one of the groups.
  if (config.scope === "parent" && isTopLevel(node)) return null
  const stats = statsFor(
    params.api,
    params.column as Column,
    node,
    config.scope,
    config.skipNonPositive
  )
  if (!stats) return null

  if (config.kind === "rank") {
    // "Best of one" carries no information — the same rule the ramps apply
    // through their spread gates. Equality is exact: both sides come from the
    // same `getCellValue` walk, so the best *is* one of the values.
    if (stats.count < 2) return null
    const best = config.reverse ? stats.min : stats.max
    return value === best ? { ...RANK_STYLE } : null
  }

  let raw = config.mode === "minmax" ? minmaxT(stats, value) : zScore(stats, value)
  if (raw === null) return null
  // The dead zone and the uniformity gate are symmetric, so flipping after
  // them is equivalent to flipping before.
  if (config.reverse) raw = config.mode === "minmax" ? 1 - raw : -raw

  return {
    backgroundColor: colorFor(config.scheme, {
      mode: config.mode,
      raw,
      intensity: config.mode === "zscore" ? zIntensity(raw) : 0,
    }),
  }
}

```

Everything from `callerCellStyleSource` to the end of the file (`registerColorScales`, `paintedColumnIds`, `attachColorScaleInvalidation`) is unchanged. Two of its doc comments mention "phase 2's runtime toggle" and "`reverse` be one more key"; leave them — both statements remain true.

If `tsc` reports that `CellStyle` is not exported from `ag-grid-community`'s root (it is declared in `entities/colDef.d.ts` and re-exported in 36.0.0, but check rather than assume), replace the import with a local alias — `type CellStyle = Record<string, string | number>` — which is the same shape.

- [ ] **Step 6: Typecheck and rebuild**

```bash
cd st_aggrid/frontend
COREPACK_ENABLE_DOWNLOAD_PROMPT=0 corepack yarn tsc --noEmit
COREPACK_ENABLE_DOWNLOAD_PROMPT=0 corepack yarn build
cd ../..
git status --short st_aggrid/frontend/build
```
Expected: `tsc` silent; the build finishes; `git status` shows one deleted and one added `index-<hash>.js` (and possibly the CSS) — the content-hashed bundle.

Also re-run the two `node` checks from Task 5 — `schemes.ts` is unchanged here but the import list of `index.ts` is the thing most likely to have been mistyped, and `tsc` covers that.

- [ ] **Step 7: Run the colour-scale e2e file to verify the grid-5 tests pass**

Run: `uv run pytest test/test_grid_color_scale.py -v`
Expected: every test PASSES — the thirteen 2.4.0 tests unchanged, the nine new grid-5 tests green.

If `test_fill_resolves_a_css_variable_through_the_host_page` is the only failure and the cell reads as transparent, the `<style>` did not reach the document: check that `st.markdown(..., unsafe_allow_html=True)` is placed **before** the `AgGrid` call of grid 5 in the app (Streamlit inserts elements in script order, and the grid reads the variable at first paint).

- [ ] **Step 8: Commit**

```bash
git add st_aggrid/frontend/src/colorScales/population.ts st_aggrid/frontend/src/colorScales/index.ts st_aggrid/frontend/build test/grid_color_scale.py test/test_grid_color_scale.py
git commit -m "Resolve anchor, rank and fill declarations; add the parent-scoped population"
```

---

### Task 7: The scopes grid and the parent-scope stability test

Grid 6 puts `scope: "parent"` next to `scope: "level"` for a ramp and for `rank`, adds a `fill` that must reach the grand total, and drives a filter to show the one property a static grid cannot: a parent-scoped population does not change when *other* groups are filtered away.

**Files:**
- Modify: `test/grid_color_scale.py` (append grid 6)
- Modify: `test/test_grid_color_scale.py` (grid-6 tests)

**Interfaces:**
- Consumes: Task 6's bundle; `region_values`, `expected_rank`, `RANK_RGBA`, `grand_total_row`-style label lookup already in this file.
- Produces: nothing.

- [ ] **Step 1: Add grid 6 to the e2e app**

Append to `test/grid_color_scale.py`:

```python
st.subheader("Row grouping — parent-scoped population next to level-scoped")
AgGrid(
    df,
    grid_options={
        **COMMON_OPTIONS,
        "groupDefaultExpanded": -1,
        "grandTotalRow": "bottom",
        "columnDefs": [
            {"colId": ROW_DIM, "field": ROW_DIM, "rowGroup": True, "rowGroupIndex": 0},
            {"colId": LEAF_DIM, "field": LEAF_DIM},
            # The grouped `region` column is hidden, so the stability test
            # filters through this visible one: `lessThan 15` keeps DE, FR, IT
            # (-5, 0, 10) and drops every US row.
            {
                "colId": "metric_b",
                "field": "metric_b",
                "filter": "agNumberColumnFilter",
                "floatingFilter": True,
                "filterParams": {"defaultOption": "lessThan"},
                "width": 110,
            },
            metric_column("level_pos", "metric_a", "positive/level", {"scheme": "positive"}, aggFunc="sum"),
            metric_column(
                "parent_pos", "metric_a", "positive/parent",
                {"scheme": "positive", "scope": "parent"}, aggFunc="sum",
            ),
            metric_column(
                "parent_rank", "metric_a", "rank/parent",
                {"scheme": "rank", "scope": "parent"}, aggFunc="sum",
            ),
            metric_column("level_rank", "metric_a", "rank/level", {"scheme": "rank"}, aggFunc="sum"),
            metric_column(
                "fill_grouped", "metric_a", "fill",
                {"scheme": "fill", "color": "rgb(4, 5, 6)"}, aggFunc="sum",
            ),
        ],
    },
    enable_enterprise_modules=True,
    height=360,
    key="color_scale_scope",
)
```

- [ ] **Step 2: Write the failing grid-6 tests**

In `test/test_grid_color_scale.py`, first make grid 6 addressable from `go_to_app`: change the wrapper count from `>= 6` to `>= 7`, and append a settle wait after grid 1's (grid 6 has the same nine rows — two groups, six leaves, the grand total — and is now the last grid on the page to finish):

```python
    page.wait_for_function(
        """() => {
             const grid = document.querySelectorAll('.ag-root-wrapper')[6];
             return !!grid && grid.querySelectorAll('.ag-row').length >= 9;
           }""",
        timeout=60000,
    )
```

Then append:

```python
# --- Phase 2: grid 6 ----------------------------------------------------------
#
# Row layout with `groupDefaultExpanded: -1` and the fixture's data order:
# body:0 EU group, body:1-3 DE FR IT, body:4 US group, body:5-7 CA NY TX, and
# the grand total either as the last body row or in the pinned-bottom section
# (located by label, never by index — see `test_the_grand_total_row_is_not_painted`).

EU_LEAVES = {"body:1": 100.0, "body:2": 200.0, "body:3": 300.0}
US_LEAVES = {"body:5": 400.0, "body:6": 500.0, "body:7": 600.0}
EU_VALUES = region_values("EU", "metric_a")
US_VALUES = region_values("US", "metric_a")


def total_row_key(page: Page, grid_index: int) -> str:
    rows = read_rows(page, grid_index)
    return next(key for key, cells in rows.items() if cells.get("ag-Grid-AutoColumn") == "Total")


def test_parent_scope_compares_a_leaf_with_its_siblings_only(page: Page):
    """Under `scope: "parent"` the EU leaves are scaled over 100..300 and the
    US leaves over 400..600, so DE and CA are both palest and IT and TX both
    darkest. The `level_pos` control column, same field, same rows, keeps the
    2.4.0 picture — one 100..600 ramp — which is what makes the two scopes
    distinguishable on one screen."""
    painted = cell_backgrounds(page, SCOPE_GRID)
    for key, value in EU_LEAVES.items():
        assert_painted(painted[key]["parent_pos"], expected_rgba("positive", EU_VALUES, value), f"{key} parent")
        assert_painted(painted[key]["level_pos"], expected_rgba("positive", METRIC_A, value), f"{key} level")
    for key, value in US_LEAVES.items():
        assert_painted(painted[key]["parent_pos"], expected_rgba("positive", US_VALUES, value), f"{key} parent")
        assert_painted(painted[key]["level_pos"], expected_rgba("positive", METRIC_A, value), f"{key} level")
    # Same alpha for DE and CA under parent scope; different under level.
    assert _alpha_channel(painted["body:1"]["parent_pos"][3]) == _alpha_channel(painted["body:5"]["parent_pos"][3])
    assert _alpha_channel(painted["body:1"]["level_pos"][3]) != _alpha_channel(painted["body:5"]["level_pos"][3])


def test_parent_scope_leaves_top_level_groups_unpainted(page: Page):
    # The group rows' parent is the root: they are the groups, not siblings.
    painted = cell_backgrounds(page, SCOPE_GRID)
    assert_unpainted(painted["body:0"]["parent_pos"], "positive", "EU group / parent")
    assert_unpainted(painted["body:4"]["parent_pos"], "positive", "US group / parent")
    assert_unpainted(painted["body:0"]["parent_rank"], "rank", "EU group / parent rank")
    assert_unpainted(painted["body:4"]["parent_rank"], "rank", "US group / parent rank")
    # ...whereas level scope still scales the two groups against each other.
    totals = list(region_totals().values())
    assert_painted(painted["body:0"]["level_pos"], expected_rgba("positive", totals, 600.0), "EU group / level")


def test_rank_under_parent_scope_picks_one_winner_per_group(page: Page):
    painted = cell_backgrounds(page, SCOPE_GRID)
    for key, value in EU_LEAVES.items():
        if expected_rank(EU_VALUES, value):
            assert_painted(painted[key]["parent_rank"], RANK_RGBA, f"{key} parent rank")
        else:
            assert_unpainted(painted[key]["parent_rank"], "rank", f"{key} parent rank")
    for key, value in US_LEAVES.items():
        if expected_rank(US_VALUES, value):
            assert_painted(painted[key]["parent_rank"], RANK_RGBA, f"{key} parent rank")
        else:
            assert_unpainted(painted[key]["parent_rank"], "rank", f"{key} parent rank")
    # Spelled out: IT and TX, one per region.
    assert is_scheme_color(painted["body:3"]["parent_rank"], "rank")
    assert is_scheme_color(painted["body:7"]["parent_rank"], "rank")


def test_rank_under_level_scope_picks_one_winner_per_level(page: Page):
    painted = cell_backgrounds(page, SCOPE_GRID)
    # Leaves: TX alone (600 over 100..600). IT is not the level maximum.
    assert is_scheme_color(painted["body:7"]["level_rank"], "rank")
    assert_unpainted(painted["body:3"]["level_rank"], "rank", "IT / level rank")
    # Groups: US (1500) over EU (600).
    assert is_scheme_color(painted["body:4"]["level_rank"], "rank")
    assert_unpainted(painted["body:0"]["level_rank"], "rank", "EU group / level rank")


def test_fill_reaches_group_rows_and_the_grand_total(page: Page):
    painted = cell_backgrounds(page, SCOPE_GRID)
    for key in ("body:0", "body:1", "body:2", "body:3", "body:4", "body:5", "body:6", "body:7"):
        assert_painted(painted[key]["fill_grouped"], (4, 5, 6, 1.0), f"{key} fill")
    total = total_row_key(page, SCOPE_GRID)
    assert_painted(painted[total].get("fill_grouped"), (4, 5, 6, 1.0), "grand total fill")


def test_filtering_another_group_away_does_not_rescale_a_parent_scoped_column(page: Page):
    """The one property of parent scoping a static grid cannot show.

    `lessThan 15` on `metric_b` keeps DE, FR, IT and drops every US row. The
    EU leaves' *parent* population is still 100/200/300, so `parent_pos`
    must not change; `level_pos`'s population shrinks from 100..600 to
    100..300 and FR moves from t = 0.2 to t = 0.5. FR keeps row-index 2
    through the filter, so its `level_pos` background changing is the repaint
    signal — the same wait `test_filtering_rescales_the_column` uses.
    """
    before = cell_backgrounds(page, SCOPE_GRID)
    fr_level_before = page.evaluate(
        """(gridIndex) => {
             const grid = document.querySelectorAll('.ag-root-wrapper')[gridIndex];
             const cell = grid.querySelector('.ag-row[row-index="2"] .ag-cell[col-id="level_pos"]');
             return getComputedStyle(cell).backgroundColor;
           }""",
        SCOPE_GRID,
    )

    grid = page.locator(".ag-root-wrapper").nth(SCOPE_GRID)
    # `agNumberColumnFilter`'s floating filter renders a second, disabled
    # read-only input next to the editable one; a bare `input` locator trips
    # Playwright's strict mode.
    grid.locator('.ag-floating-filter[col-id="metric_b"] input:not([disabled])').fill("15")
    # EU group + 3 leaves + the grand total.
    page.wait_for_function(
        """(gridIndex) => {
             const grid = document.querySelectorAll('.ag-root-wrapper')[gridIndex];
             return grid.querySelectorAll('.ag-row').length === 5;
           }""",
        arg=SCOPE_GRID,
        timeout=10000,
    )
    page.wait_for_function(
        """([gridIndex, previousBackground]) => {
             const grid = document.querySelectorAll('.ag-root-wrapper')[gridIndex];
             const cell = grid.querySelector('.ag-row[row-index="2"] .ag-cell[col-id="level_pos"]');
             return !!cell && getComputedStyle(cell).backgroundColor !== previousBackground;
           }""",
        arg=[SCOPE_GRID, fr_level_before],
        timeout=10000,
    )

    after = cell_backgrounds(page, SCOPE_GRID)
    for key, value in EU_LEAVES.items():
        # Unchanged: same expected colour as before the filter, and the same
        # browser output, on the 8-bit grid.
        assert_painted(after[key]["parent_pos"], expected_rgba("positive", EU_VALUES, value), f"{key} parent after")
        assert _alpha_channel(after[key]["parent_pos"][3]) == _alpha_channel(before[key]["parent_pos"][3])
    # Re-scaled: FR is now mid-ramp over three rows, not over six.
    assert_painted(after["body:2"]["level_pos"], expected_rgba("positive", EU_VALUES, 200.0), "FR level after")
    assert _alpha_channel(after["body:2"]["level_pos"][3]) != _alpha_channel(before["body:2"]["level_pos"][3])
```

- [ ] **Step 3: Run the grid-6 tests to verify they fail**

Do this with Step 1's app change **stashed** (`git stash push test/grid_color_scale.py`), so the app still has six grids:

Run: `uv run pytest test/test_grid_color_scale.py -k "parent or level_scope or grand_total or another_group" -v`
Expected: `go_to_app` times out waiting for the seventh wrapper — a failure for the right reason. Then `git stash pop`.

- [ ] **Step 4: Run the whole colour-scale file**

Run: `uv run pytest test/test_grid_color_scale.py -v`
Expected: all PASS — 13 from 2.4.0, 9 from Task 6, 6 from this task.

If `test_fill_reaches_group_rows_and_the_grand_total` cannot find the `Total` row: `read_rows` keys pinned-bottom rows under a different section prefix than `body`; `total_row_key` already searches every section, so the likely cause is `grandTotalRow` not being rendered because no column carries an `aggFunc` — every metric column above does, so re-check the `aggFunc="sum"` kwargs survived the `metric_column(...)` call.

- [ ] **Step 5: Run the entire suite**

Run: `uv run pytest`
Expected: everything passes except the pre-existing drag-and-drop skip. `population.ts` is on the path of every painted grid, so the full e2e run is not optional here.

- [ ] **Step 6: Commit**

```bash
git add test/grid_color_scale.py test/test_grid_color_scale.py
git commit -m "Cover parent scoping, rank per group, fill on the grand total, and filter stability"
```

---

### Task 8: Documentation, version and the release dry run

**Files:**
- Modify: `README.md` (the "Declarative colour scales without JavaScript" section)
- Modify: `CLAUDE.md` (the colour-scheme bullet; `_numbers.py` in the tree)
- Modify: `pyproject.toml`, `st_aggrid/pyproject.toml`, `uv.lock` (version)
- Test: `test/unit/test_component_manifest.py`, `scripts/release.sh --dry-run`

**Interfaces:**
- Consumes: everything above.
- Produces: nothing.

- [ ] **Step 1: Bump the version**

```bash
sed -i '0,/^version = "2.4.0"$/s//version = "2.4.1"/' pyproject.toml
sed -i '0,/^version = "2.4.0"$/s//version = "2.4.1"/' st_aggrid/pyproject.toml
uv lock
grep -n '^version' pyproject.toml st_aggrid/pyproject.toml
grep -n -A1 '^name = "st-aggrid"' uv.lock
```
Expected: both `pyproject.toml` print `version = "2.4.1"`; the `uv.lock` entry reads `version = "2.4.1"`.

Run: `uv run pytest test/unit/test_component_manifest.py -v`
Expected: PASS.

- [ ] **Step 2: Update the README section**

In `README.md`, under `### Declarative colour scales without JavaScript`:

(a) Replace the opening code block with:

```python
gb = GridOptionsBuilder.from_dataframe(df)
gb.configure_color_scale(scheme="positive")          # grid-level defaults
gb.configure_column("revenue", color_scale=True)     # inherit them
gb.configure_column("arppu", color_scale={"scheme": "diverging"})
gb.configure_column("cpi", color_scale={"scheme": "positive", "reverse": True})   # lower is better
gb.configure_column("growth", color_scale={"mode": "anchor", "anchor": 1.0, "span": 1.0})
gb.configure_column("best", color_scale={"scheme": "rank", "scope": "parent"})
gb.configure_column("installs", color_scale={"scheme": "fill", "color": "var(--secondary-background-color)"})
gb.configure_column("notes", color_scale=False)      # explicitly off
AgGrid(df, grid_options=gb.build())
```

(b) Replace the `#### Schemes` table with:

```markdown
| `scheme` | Default `mode` | Default `skip_non_positive` | Reads as |
|---|---|---|---|
| `neutral` | `zscore` | `True` | one blue hue, intensity = distance from the column mean |
| `positive` | `minmax` | `False` | one green hue, palest at the column minimum |
| `diverging` | `zscore` | `True` | red below the mean, green above it |
| `rank` | — | `False` | the best value in the population — the maximum, or the minimum under `reverse` — in bold on green; nothing else is painted. A population of one paints nothing |
| `fill` | — | — | one constant colour on every cell of the column, including group rows, the grand total and pinned rows |
```

(c) Replace the `#### Keys` table and the paragraph after it with:

```markdown
| Key | Values | Read by | Default |
|---|---|---|---|
| `scheme` | `"neutral"`, `"positive"`, `"diverging"`, `"rank"`, `"fill"` | all | required at one of the two levels — except under `mode: "anchor"`, which defaults it to `"diverging"` |
| `mode` | `"minmax"`, `"zscore"`, `"anchor"` | the three ramps | the scheme's own |
| `scope` | `"level"`, `"parent"` | `rank`, and ramps under `minmax` / `zscore` | `"level"` |
| `reverse` | `bool` | ramps and `rank` | `False` |
| `skip_non_positive` | `bool` | ramps and `rank` | the scheme's own |
| `anchor` | number | `mode: "anchor"` | required under that mode |
| `span` | number `> 0` | `mode: "anchor"` | required under that mode |
| `color` | any CSS colour string, e.g. `"var(--secondary-background-color)"` | `fill` | required by that scheme |

A key a scheme does not read is ignored, not rejected — a grid-level
`mode` default does not break a `fill` column. Every key that *is* present
is type-checked at both levels, and a declaration that resolves to no
scheme, a `fill` with no `color`, or an `anchor` mode without both its
numbers raises at build time.

`minmax` ramps linearly between the column's extremes. `zscore` measures
distance from the column's mean in standard deviations, leaves values within
half a deviation of the mean unpainted, and paints nothing at all when the
column is effectively uniform. `anchor` measures the deviation from a fixed
`anchor` in units of `span`, clamped at one span either side, and consults
no population at all: a growth ratio anchored at `1.0` reads red below one,
green above it, and paints nothing at exactly one. Under `diverging` — its
default — the two sides take the two hues; under `neutral` or `positive` the
deviation's magnitude is the intensity.

`reverse` flips the direction: palest at the maximum under `minmax`, red
above the mean under `zscore` and `anchor`, the minimum as the winner under
`rank`. It has no visible effect on `neutral` + `zscore`, whose hue depends
on the magnitude of the z-score alone.
```

(d) Append to `#### What a column is compared against`, after the "Because the population is read after filtering…" paragraph:

```markdown
`scope: "parent"` narrows the population to the row's **siblings under one
parent group**: a long-form grid whose level-0 groups are unlike metrics
compares each metric's rows with each other, never across metrics. Under
this scope a row whose parent is the root — a top-level group, or any row
of an ungrouped grid — is neither painted nor counted: it *is* one of the
groups, and comparing the groups across is what choosing this scope
declines to do. Filtering other groups away therefore does not re-scale a
parent-scoped column. `anchor` and `fill` ignore `scope`.
```

(e) Append to `#### Interaction with `cellStyle``, before the "Working examples" paragraph:

```markdown
This is also why a plain background — a column marked as structural with a
theme colour — should be a `fill` declaration rather than a one-line
`cellStyle`: as a `cellStyle` it occupies the slot, and no colour scale can
ever attach to that column afterwards.
```

(f) Replace the "Working examples" paragraph with:

```markdown
Working examples: `test/grid_color_scale.py` builds seven grids covering
every scheme, every mode, both `skip_non_positive` settings, `reverse`,
both scopes, the `GridOptionsBuilder` path, a `fill` from a CSS variable,
and a grid-wide `defaultColDef.cellStyle` that disables the scale entirely;
`test/test_grid_color_scale.py` asserts what each one paints, against the
reference arithmetic in `test/color_scale_fixture.py`.
```

- [ ] **Step 3: Update CLAUDE.md**

Replace the colour-scheme bullet under **Key Design Decisions** with:

```markdown
- **Five built-in colour schemes, three modes, two scopes**: `neutral`,
  `positive`, `diverging` (ramps), `rank` (the best value in the population)
  and `fill` (a constant colour) — declared in
  `colDef.context["stColorScale"]` with grid-level defaults in
  `gridOptions["context"]`, merged per key. Ramps run `minmax`, `zscore` or
  `anchor` (a fixed reference, no population); `reverse` flips any direction.
  A population is the same column at the same group level after filter and
  sort (`scope: "level"`), or only the row's siblings under one parent
  (`scope: "parent"`, top-level rows then unpainted) — one statistics pass
  either way (`colorScales/population.ts`). A caller-supplied `cellStyle`
  wins over the built-in, as with the aggregators. See the README's
  "Declarative colour scales without JavaScript".
```

In the architecture tree, add below `_coldefs.py`:

```
├── _numbers.py              # strict number predicates shared by both validators
```

- [ ] **Step 4: Run everything one last time**

```bash
uv run pytest -m "not e2e" -q
node st_aggrid/frontend/src/colorScales/__checks__/normalize.check.ts
node st_aggrid/frontend/src/colorScales/__checks__/schemes.check.ts
cd st_aggrid/frontend && COREPACK_ENABLE_DOWNLOAD_PROMPT=0 corepack yarn tsc --noEmit && cd ../..
scripts/release.sh 2.4.1 --dry-run
```
Expected: the unit suite passes; both checks print `ok`; `tsc` is silent; the dry run passes every "what you would ship" gate (versions, lockfile, bundle rebuild diff, typecheck, tests) and only *warns* about the branch, since this is not `main` yet.

- [ ] **Step 5: Commit**

```bash
git add README.md CLAUDE.md pyproject.toml st_aggrid/pyproject.toml uv.lock
git commit -m "Document the phase 2 colour scales and bump to 2.4.1"
```

- [ ] **Step 6: Hand off**

Open a PR from `color-scale-phase-2` to `main`. After merge, tag from `main` with `scripts/release.sh 2.4.1 --push` per the release procedure — never from this branch.

---

## Out of scope

Recorded so nobody adds them mid-plan:

- **9.3 — a runtime scheme picker** in the column menu / context menu. Depends on the `useAutoCollect` refactor (9.1) and a new state channel through `collect`.
- **9.4 — a declarative `getRowStyle`.** A different slot and a second declaration; it will reuse `fill`'s `color` form.
- **The consumer migration itself** (`hitapps_analytics`): the four stylers, the `__max__*` columns, `popover: False` on `ab_tests`, and the golden run of the eight 2.4.0 pages. Listed in the spec's *Consumer migration* section.
- **Any AG-Grid bump.**
- **Changing a consumer page from `neutral` to a directional scheme** — 9.2c hands over `reverse`; using it is a product decision.
