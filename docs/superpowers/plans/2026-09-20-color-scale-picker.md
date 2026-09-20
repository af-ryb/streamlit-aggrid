# Colour-Scale Picker and Settled-Redraw Removal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a reader choose scheme, mode and direction of one column's colour scale from the grid's own menus, with the choice reported to Python and restorable at mount — and, first, delete the obsolete "settled redraw" from the config-update effect.

**Architecture:** The reader's choice is a third resolution layer — a `Map<sourceColId, Override>` owned by the React component and injected into the grid `context` under a reserved key, so it survives `updateGridOptions` and is visible to `cellStyle` before first paint. Menus come from two AG-Grid hooks (`getColumnMenuItems` for the ⋮ menu, the Columns tool panel and the Column Chooser; `getContextMenuItems` for cells) that wrap whatever the caller supplied. State leaves through a fork-owned collect method and a synthetic `update_on` event that calls the collector directly; it returns through a mount-only `color_scale_state` prop.

**Tech Stack:** React 18 + TypeScript (Vite lib build), AG-Grid 36.1.0 Enterprise, Streamlit Custom Components v2, Python 3 + pytest + Playwright, Node 22 (type-stripping) for the pure checks.

**Spec:** `docs/superpowers/specs/2026-09-20-color-scale-picker-design.md`

> **Superseded in part (2026-09-20, after the final review).** This plan's text about
> `@initial` menu hooks and a remount being needed after a live opt-in is wrong: the
> shipped AG-Grid 36.1.0 runtime applies both hooks on `updateGridOptions`. The spec and
> the code are the authority; see the spec's "Toggling `interactive` on a live grid".
> The plan is kept as the historical record of what was executed.

## Global Constraints

- Branch is `feature/color-scale-picker`. **Never commit to `main`.**
- Release version is **2.5.0**, in both `pyproject.toml` and `st_aggrid/pyproject.toml`, which must stay in sync (Task 8 only).
- AG-Grid stays pinned at exactly **36.1.0**. Do not touch `package.json` dependencies.
- **Additive.** A grid without `interactive: true` in `context["stColorScale"]` must run exactly today's code path: no slot filled that is not filled today, no menu hook installed, no context key injected, `stColorScaleCellStyle` still returns `null` when nothing resolves.
- **Part A (Task 1) lands and the whole e2e suite is green before Task 2's first commit.**
- Yarn is **not** on PATH. Every frontend command is `COREPACK_ENABLE_DOWNLOAD_PROMPT=0 corepack yarn …` run from `st_aggrid/frontend`.
- E2E tests run against the **built** bundle. Any task that changes `st_aggrid/frontend/src` must run `corepack yarn build` before its e2e step.
- `st_aggrid/frontend/build/` is committed. A rebuild changes the content hash, so `git status` shows a delete plus an add, never a modify. Stage both (`git add -A st_aggrid/frontend/build`). The build is committed **only in Task 1 and Task 8**; in between, leave `build/` dirty and do not stage it.
- E2E tests address rows by `row-index`, never by DOM order (`test/grid_dom.py` docstring says why).
- Colour-scale e2e tests never hand-type an expected colour: they come from `test/color_scale_fixture.py`.
- `colorScales/overrides.ts` must import **nothing**, so `node <path>.check.ts` can run it.
- Menu labels are these exact English literals: `Colour scale`, `None`, `Neutral`, `Positive`, `Diverging`, `Rank`, `Mode`, `Min–max` (en dash, U+2013), `Z-score`, `Anchor`, `Reverse`, `Reset to default`.
- Python runs through uv: `uv run pytest …`.
- Commit messages are imperative mood, describe what changed, and end with the two attribution lines used by the existing commits on this branch.

## File Structure

| File | Responsibility | Task |
|---|---|---|
| `st_aggrid/frontend/src/AgGridComponent.tsx` | Loses the settled redraw (1); owns the override `Map`, passes the runtime to both `parseGridOptions` call sites (5); wires the collector and the synthetic event (7) | 1, 5, 7 |
| `test/test_grid_cohort_pivot.py` | Docstrings name the real mechanism | 1 |
| `st_aggrid/color_scale.py` | `interactive` key, reserved context key, `validate_color_scale_state` | 2 |
| `test/unit/test_color_scale_validation.py` | Unit tests for the above | 2 |
| `st_aggrid/grid_options_builder.py` | `configure_color_scale(interactive=)` | 3 |
| `st_aggrid/aggrid.py` | `color_scale_state` param + payload; synthetic `update_on` event | 3 |
| `st_aggrid/result.py` | `AgGridResult.color_scale_state` | 3 |
| `st_aggrid/frontend/src/colorScales/overrides.ts` | **New.** Pure layer arithmetic: sanitise, serialise, apply a choice, order the declaration candidates | 4 |
| `st_aggrid/frontend/src/colorScales/__checks__/overrides.check.ts` | **New.** Node check for the above | 4 |
| `st_aggrid/frontend/src/colorScales/index.ts` | Third layer in the resolver, `resolveFor`, interactive slot filling, `UNPAINTED` on interactive grids | 5 |
| `st_aggrid/frontend/src/utils/parsers.ts` | Injects the `Map`, installs the menu | 5, 6 |
| `st_aggrid/frontend/src/types/AgGridTypes.ts` | `color_scale_state` on `AgGridData` | 5 |
| `test/color_scale_dom.py` | **New.** `assert_painted` / `assert_unpainted` / `font_weight`, moved out of `test_grid_color_scale.py` so two suites share them | 5 |
| `test/grid_color_scale_picker.py` | **New.** The e2e app, six grids | 5 |
| `test/test_grid_color_scale_picker.py` | **New.** The e2e suite, grown task by task | 5, 6, 7 |
| `st_aggrid/frontend/src/colorScales/menu.ts` | **New.** Eligibility, the sub menu, the two hook wrappers | 6 |
| `st_aggrid/frontend/src/hooks/useAutoCollect.ts` | `extraCollectors`, `SYNTHETIC_EVENTS` | 7 |
| `README.md`, `CLAUDE.md`, both `pyproject.toml` | Docs and version | 8 |

---

### Task 1: Remove the settled redraw (slice 9.5)

**Files:**
- Modify: `st_aggrid/frontend/src/AgGridComponent.tsx:191-197`, `:640-652`, `:809-810`, `:874-908`
- Modify: `test/test_grid_cohort_pivot.py:31-35`, `:458-461`, `:535-552`

**Interfaces:**
- Consumes: nothing.
- Produces: nothing new. `redrawPendingRef` and `redrawSettleCleanupRef` cease to exist; no later task may reference them.

This is a deletion guarded by existing tests, so there is no new failing test to write first. The guard is `test_adding_a_value_column_while_scrolled_does_not_stack_cells` and `test_a_value_column_added_live_*`, which must stay green.

- [ ] **Step 1: Run the guards on the untouched tree to get a baseline**

Run: `uv run pytest test/test_grid_cohort_pivot.py -v`
Expected: all PASS. If anything fails here, stop — the baseline is broken and this task cannot attribute a regression.

- [ ] **Step 2: Delete the two refs**

In `AgGridComponent.tsx` delete exactly this block (currently `:191-197`):

```tsx
  // Set by the config-update effect to ask for one more row redraw once the
  // column layout has settled; consumed by the debounced
  // `displayedColumnsChanged` listener registered in onGridReady. A ref, not
  // state, so setting it never triggers a React render.
  const redrawPendingRef = useRef(false)
  // Cleanup for that listener, torn down on unmount alongside the others.
  const redrawSettleCleanupRef = useRef<(() => void) | null>(null)
```

- [ ] **Step 3: Delete the arming line and its comment**

In the config-update effect delete from the line `      // ...and arm a second redraw for once the columns have settled. From` through `      redrawPendingRef.current = true` inclusive, plus the blank line that follows. The block directly above it must remain exactly:

```tsx
      clearStats(gridApiRef.current)
      gridApiRef.current.redrawRows()
```

together with its own comment (`// updateGridOptions swaps columnDefs in place …` through `// computed under the old declaration. Clear it explicitly first.`). Do not touch those lines.

- [ ] **Step 4: Delete the listener in `onGridReady`**

Delete from the comment line `      // Repaint rows once a config update's column layout has settled. Armed by` through the closing `      }` of the `redrawSettleCleanupRef.current = () => { … }` assignment, plus the blank line that follows. The next surviving code is the comment `// Re-fit columns to grid width whenever the displayed column set changes`. Keep the `debounce` import: the refit below still uses it.

- [ ] **Step 5: Delete the teardown lines**

In the unmount effect delete:

```tsx
      redrawSettleCleanupRef.current?.()
      redrawSettleCleanupRef.current = null
```

- [ ] **Step 6: Prove nothing references the removed names**

Run: `grep -n "redrawPending\|redrawSettle\|columns have settled\|columns settled" st_aggrid/frontend/src/AgGridComponent.tsx`
Expected: no output.

- [ ] **Step 7: Rewrite the cohort suite's explanation of the mechanism**

In `test/test_grid_cohort_pivot.py`, module docstring, replace

```
  reported overlap. It arrived with the pin (50 stacked pairs on the AG-Grid 36
  build, 0 on 35.2.1) and is fixed in this fork: the config-update effect now
  repaints once the column layout has settled rather than while it is still
  moving.
```

with

```
  reported overlap. It arrived with the pin (50 stacked pairs on the AG-Grid
  36.0 build, 0 on 35.2.1). The cause is AG-Grid's: 36.0.x does not dispatch
  `gridColumnsChanged` when a value column is added to a live pivot grid, so
  the new column's cells never get their `leftChanged`/`widthChanged`
  listeners and stop following the layout. Fixed by pinning AG-Grid 36.1.0.
```

In the comment at `:458-461` replace `the settled-redraw under load from a second angle.` with `the 36.1.0 pin under load from a second angle.`

In `test_adding_a_value_column_while_scrolled_does_not_stack_cells`, replace the docstring's last sentence of the second paragraph and its last paragraph. The second paragraph ends `… but two live columns computing the same left offset, because the redraw ran while the column layout was still in flight.` — change the clause after `same left offset,` to:

```
    columns computing the same left offset, because the added column's cells
    had no `leftChanged` listener: AG-Grid 36.0.x does not dispatch
    `gridColumnsChanged` for a value column added to a live pivot grid.
```

and replace the final paragraph (`Guards the settled-redraw … before the columns settle.`) with:

```
    Guards the AG-Grid 36.1.0 pin (see CLAUDE.md, "Do not go below 36.1.0").
    Until 2026-09-20 this fork also repainted the rows a second time once the
    columns had settled; that treated the symptom — `redrawRows` recreates
    cells at the right offset but adds no listeners — and was removed once the
    pin made it redundant. Not verified: that the original 36.0.0 defect went
    through this exact mechanism, which would need a downgrade to show.
```

- [ ] **Step 8: Build**

Run: `cd st_aggrid/frontend && COREPACK_ENABLE_DOWNLOAD_PROMPT=0 corepack yarn build`
Expected: `tsc` reports no errors (an unused-variable error means a ref survived), Vite writes `build/index-<hash>.js` and `build/index-<hash>.css`.

- [ ] **Step 9: Run the guards**

Run: `uv run pytest test/test_grid_cohort_pivot.py -v`
Expected: all PASS, in particular `test_adding_a_value_column_while_scrolled_does_not_stack_cells` and every `test_a_value_column_added_live_*`.

- [ ] **Step 10: Run the whole suite — this is the evidence the slice was missing**

Run: `uv run pytest`
Expected: all PASS. A failure here is attributable to this task alone; diagnose it before going on. Do not start Task 2 on a red suite.

- [ ] **Step 11: Commit (with the build)**

```bash
git add -A st_aggrid/frontend/build st_aggrid/frontend/src/AgGridComponent.tsx test/test_grid_cohort_pivot.py
git commit -m "Remove the settled redraw from the config-update effect"
```

Body of the message: one paragraph saying the AG-Grid 36.1.0 pin fixed the cause (`gridColumnsChanged` not dispatched on 36.0.x), that the second `redrawRows` only treated the symptom, and that the full e2e suite is green without it.

---

### Task 2: Python validation — `interactive`, the reserved key, the state

**Files:**
- Modify: `st_aggrid/color_scale.py`
- Test: `test/unit/test_color_scale_validation.py`

**Interfaces:**
- Consumes: existing `_validate_declaration`, `validate_color_scale_columns`, `COLOR_SCALE_CONTEXT_KEY`.
- Produces:
  - `COLOR_SCALE_OVERRIDES_CONTEXT_KEY = "stColorScaleOverrides"`
  - `COLOR_SCALE_STATE_KEYS = ("scheme", "mode", "reverse")`
  - `validate_color_scale_state(state: Optional[dict]) -> None` — raises `ValueError` on a malformed state; never on an unknown colId or an unresolvable entry.
  - `_validate_declaration(declaration, where, *, grid_level=False)`

- [ ] **Step 1: Write the failing tests**

Append to `test/unit/test_color_scale_validation.py` (and add `COLOR_SCALE_OVERRIDES_CONTEXT_KEY`, `COLOR_SCALE_STATE_KEYS`, `validate_color_scale_state` to the existing `from st_aggrid.color_scale import (...)`):

```python
# ---------------------------------------------------------------------------
# `interactive` — the grid-level opt-in for the reader's picker
# ---------------------------------------------------------------------------


def test_interactive_alone_is_a_complete_grid_level_declaration():
    validate_color_scale_columns(grid_options(None, {"interactive": True}))


def test_interactive_sits_beside_other_grid_level_defaults():
    validate_color_scale_columns(
        grid_options(True, {"scheme": "neutral", "interactive": True})
    )


@pytest.mark.parametrize("value", [1, "yes", None])
def test_interactive_must_be_a_bool(value):
    with pytest.raises(ValueError, match="'interactive'.*must be a bool"):
        validate_color_scale_columns(grid_options(None, {"interactive": value}))


def test_interactive_is_rejected_at_column_level():
    with pytest.raises(ValueError, match="grid-level key"):
        validate_color_scale_columns(
            grid_options({"scheme": "neutral", "interactive": True})
        )


def test_the_overrides_context_key_is_reserved():
    options = grid_options(None, {"interactive": True})
    options["context"][COLOR_SCALE_OVERRIDES_CONTEXT_KEY] = {}
    with pytest.raises(ValueError, match="reserved"):
        validate_color_scale_columns(options)


# ---------------------------------------------------------------------------
# `color_scale_state` — the reader's saved choice, fed back at mount
# ---------------------------------------------------------------------------


def test_state_constants_are_the_literals_the_frontend_uses():
    assert COLOR_SCALE_OVERRIDES_CONTEXT_KEY == "stColorScaleOverrides"
    assert COLOR_SCALE_STATE_KEYS == ("scheme", "mode", "reverse")


@pytest.mark.parametrize(
    "state",
    [
        None,
        {},
        {"cpi": False},
        {"cpi": {}},
        {"cpi": {"scheme": "diverging"}},
        {"cpi": {"scheme": "rank", "reverse": True}},
        {"cpi": {"mode": "zscore"}},
        # Well formed but unresolvable without an anchor/span lower down:
        # the reader's history, not a programming error.
        {"cpi": {"mode": "anchor"}},
        # A column the page no longer has.
        {"gone_column": {"scheme": "neutral"}},
    ],
)
def test_well_formed_state_passes(state):
    validate_color_scale_state(state)


@pytest.mark.parametrize(
    "state, message",
    [
        ([], "must be a dict"),
        ("neutral", "must be a dict"),
        ({1: False}, "keys must be column ids"),
        ({"cpi": True}, "must be False or a dict"),
        ({"cpi": "neutral"}, "must be False or a dict"),
        ({"cpi": {"scope": "parent"}}, "unknown key"),
        ({"cpi": {"anchor": 1.0}}, "unknown key"),
        ({"cpi": {"scheme": "fill"}}, "'fill'"),
        ({"cpi": {"scheme": "rainbow"}}, "must be one of"),
        ({"cpi": {"mode": "linear"}}, "must be one of"),
        ({"cpi": {"reverse": 1}}, "must be a bool"),
    ],
)
def test_malformed_state_raises(state, message):
    with pytest.raises(ValueError, match=message):
        validate_color_scale_state(state)
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest test/unit/test_color_scale_validation.py -q`
Expected: collection error — `ImportError: cannot import name 'COLOR_SCALE_OVERRIDES_CONTEXT_KEY'`.

- [ ] **Step 3: Implement**

In `st_aggrid/color_scale.py`:

After `COLOR_SCALE_CONTEXT_KEY` add:

```python
#: Reserved: the frontend stores the reader's live choices under this key of
#: the grid ``context``. A caller-supplied value would be overwritten, so it is
#: rejected instead. Matches ``colorScales/index.ts``'s
#: ``ST_COLOR_SCALE_OVERRIDES``.
COLOR_SCALE_OVERRIDES_CONTEXT_KEY = "stColorScaleOverrides"

#: The keys the reader's picker can set, and so the only keys an entry of
#: ``color_scale_state`` may carry.
COLOR_SCALE_STATE_KEYS = ("scheme", "mode", "reverse")
```

Add `"interactive",` as the last entry of `_KNOWN_KEYS`.

Change `_validate_declaration`'s signature and the start of its body:

```python
def _validate_declaration(
    declaration: dict, where: str, *, grid_level: bool = False
) -> None:
    """The rules shared by the grid-level and the column-level declaration:
    every present key has the right shape. Relevance is not checked here.

    ``interactive`` is the one key that belongs to a level: it switches the
    reader's picker on for the whole grid, so a column cannot carry it."""
    unknown = sorted(key for key in declaration if key not in _KNOWN_KEYS)
    if unknown:
        raise ValueError(
            f"{where}: unknown key(s) {unknown} in the colour scale "
            f"declaration. Available: {list(_KNOWN_KEYS)}."
        )

    if "interactive" in declaration and not grid_level:
        raise ValueError(
            f"{where}['interactive'] is a grid-level key: it switches the "
            f"reader's picker on for the whole grid. Set it with "
            f"GridOptionsBuilder.configure_color_scale(interactive=True)."
        )
```

Change the flag loop's tuple from `("reverse", "skip_non_positive")` to `("reverse", "skip_non_positive", "interactive")`.

In `validate_color_scale_columns`, right after `grid_context = …`:

```python
    if COLOR_SCALE_OVERRIDES_CONTEXT_KEY in grid_context:
        raise ValueError(
            f"gridOptions context['{COLOR_SCALE_OVERRIDES_CONTEXT_KEY}'] is "
            f"reserved: the component keeps the reader's colour-scale choices "
            f"there. Pass a saved choice as AgGrid(color_scale_state=...)."
        )
```

and pass `grid_level=True` in the grid-level `_validate_declaration(...)` call.

At the end of the module add:

```python
def validate_color_scale_state(state: Optional[dict]) -> None:
    """Raise ``ValueError`` for a malformed ``color_scale_state``.

    Shape only. The state is what a reader chose, possibly long ago and against
    different page code: an entry for a column that no longer exists, or a
    choice that no longer resolves (a saved ``mode: "anchor"`` on a column
    that has since lost its ``anchor``), is history, not a bug — the frontend
    ignores it. A value of the wrong *shape* can only come from the calling
    code, and that is what raises here.
    """
    if state is None:
        return
    if not isinstance(state, dict):
        raise ValueError(
            f"color_scale_state must be a dict of column id -> False or a "
            f"dict, got {type(state).__name__}."
        )

    for col_id, entry in state.items():
        if not isinstance(col_id, str):
            raise ValueError(
                f"color_scale_state keys must be column ids (str), got "
                f"{col_id!r}."
            )
        where = f"color_scale_state['{col_id}']"
        if entry is False:
            continue
        # `True` is a bool, not a dict; it falls through to the same error.
        if not isinstance(entry, dict):
            raise ValueError(
                f"{where} must be False or a dict, got {entry!r}."
            )

        unknown = sorted(key for key in entry if key not in COLOR_SCALE_STATE_KEYS)
        if unknown:
            raise ValueError(
                f"{where}: unknown key(s) {unknown}. The reader's picker sets "
                f"only {list(COLOR_SCALE_STATE_KEYS)}."
            )
        if entry.get("scheme") == "fill":
            raise ValueError(
                f"{where}['scheme'] cannot be 'fill': a fill needs a colour, "
                f"which the picker does not offer."
            )
        _validate_declaration(entry, where)
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest test/unit/test_color_scale_validation.py -q`
Expected: all PASS, including every pre-existing test in the file.

- [ ] **Step 5: Commit**

```bash
git add st_aggrid/color_scale.py test/unit/test_color_scale_validation.py
git commit -m "Validate the interactive opt-in and the reader's colour-scale state"
```

---

### Task 3: Python surface — builder, `AgGrid`, `update_on`, result

**Files:**
- Modify: `st_aggrid/grid_options_builder.py:169-226`
- Modify: `st_aggrid/aggrid.py` (`:28-67` validation, `:162-164` signature, `:238-245` docstring, `:423` validation call, `:490` payload)
- Modify: `st_aggrid/result.py`
- Test: `test/unit/test_grid_options_builder.py`, `test/unit/test_update_on_validation.py`, `test/unit/test_result.py`

**Interfaces:**
- Consumes: `validate_color_scale_state` (Task 2).
- Produces:
  - `GridOptionsBuilder.configure_color_scale(..., interactive: Optional[bool] = None)` (keyword-only)
  - `AgGrid(..., color_scale_state: Optional[Dict] = None)` → payload key `"color_scale_state"`
  - `SYNTHETIC_UPDATE_ON_EVENTS: frozenset = frozenset({"stColorScaleChanged"})` in `st_aggrid/aggrid.py`
  - `AgGridResult.color_scale_state -> Optional[Dict]`, reading `grid_state["colorScaleState"]`

- [ ] **Step 1: Write the failing tests**

Append to `test/unit/test_grid_options_builder.py`:

```python
def test_configure_color_scale_writes_interactive():
    gb = GridOptionsBuilder()
    gb.configure_color_scale(scheme="neutral", interactive=True)
    assert gb.build()["context"][COLOR_SCALE_CONTEXT_KEY] == {
        "scheme": "neutral",
        "interactive": True,
    }


def test_configure_color_scale_interactive_alone():
    gb = GridOptionsBuilder()
    gb.configure_color_scale(interactive=True)
    assert gb.build()["context"][COLOR_SCALE_CONTEXT_KEY] == {"interactive": True}
```

(If the file builds its builder differently — e.g. `GridOptionsBuilder.from_dataframe(df)` — follow the neighbouring `test_configure_color_scale_*` tests at `:85-120` for construction; the assertions stay as written.)

Append to `test/unit/test_update_on_validation.py` (and import `SYNTHETIC_UPDATE_ON_EVENTS`):

```python
def test_the_synthetic_colour_scale_event_passes_as_a_bare_name():
    validate_update_on(["sortChanged", "stColorScaleChanged"])


def test_the_synthetic_colour_scale_event_cannot_be_debounced():
    with pytest.raises(ValueError, match="raised by the component itself"):
        validate_update_on([("stColorScaleChanged", 300)])


def test_synthetic_events_are_the_literals_the_frontend_uses():
    assert SYNTHETIC_UPDATE_ON_EVENTS == frozenset({"stColorScaleChanged"})
```

Append to `test/unit/test_result.py`:

```python
def test_color_scale_state_reads_the_fork_owned_collect_key():
    component = _component_result(
        grid_state={"colorScaleState": {"cpi": {"scheme": "diverging"}, "cpm": False}}
    )
    result = AgGridResult(component_result=component, original_data=None)
    assert result.color_scale_state == {"cpi": {"scheme": "diverging"}, "cpm": False}


def test_color_scale_state_is_none_until_collected():
    result = AgGridResult(component_result=_component_result(), original_data=None)
    assert result.color_scale_state is None
    result = AgGridResult(
        component_result=_component_result(grid_state={"columnState": []}),
        original_data=None,
    )
    assert result.color_scale_state is None
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest test/unit/test_grid_options_builder.py test/unit/test_update_on_validation.py test/unit/test_result.py -q`
Expected: `ImportError` for `SYNTHETIC_UPDATE_ON_EVENTS`; `TypeError: … unexpected keyword argument 'interactive'`; `AttributeError: … 'color_scale_state'`.

- [ ] **Step 3: Implement the builder**

In `configure_color_scale` add `interactive: Optional[bool] = None,` after `color`, add `("interactive", interactive),` as the last tuple of the key loop, and add to the docstring's `Args`:

```
            interactive (bool, optional): let the reader choose scheme, mode
                and direction per column from the grid's menus (⋮, cell
                right-click, Columns panel). Needs the enterprise bundle for
                the menus. Must be set when the grid is created: switching it
                on later needs a remount (a changed `key`).
```

Also change the docstring's opening claim "This activates nothing on its own" to "Apart from `interactive`, this activates nothing on its own".

- [ ] **Step 4: Implement `aggrid.py`**

Below `LIFECYCLE_UPDATE_ON_EVENTS` add:

```python
#: Events the component raises itself rather than AG-Grid. They never reach
#: ``addEventListener``; the frontend calls the collector directly. Mirrors
#: ``SYNTHETIC_EVENTS`` in ``frontend/src/hooks/useAutoCollect.ts``.
SYNTHETIC_UPDATE_ON_EVENTS: frozenset = frozenset({"stColorScaleChanged"})
```

In `validate_update_on`, after the existing lifecycle `raise`, add (the early `if not offenders: return` must become a fall-through — restructure so both checks run):

```python
    synthetic = [
        entry[0]
        for entry in update_on
        if isinstance(entry, (tuple, list))
        and entry
        and entry[0] in SYNTHETIC_UPDATE_ON_EVENTS
    ]
    if synthetic:
        raise ValueError(
            f"update_on={synthetic!r} cannot be debounced: these events are "
            "raised by the component itself, once per reader action, not by "
            "AG-Grid, so there is no burst of firings for a debounce to "
            f"coalesce. Pass the bare event name instead (e.g. {synthetic[0]!r})."
        )
```

Concretely the function's tail becomes: compute `offenders`; `if offenders: raise …` (existing message, unchanged); compute `synthetic`; `if synthetic: raise …`. Extend the docstring's first paragraph with one sentence: "The same goes for the component's own synthetic events (:data:`SYNTHETIC_UPDATE_ON_EVENTS`)."

Signature: after `initial_state: Optional[Dict] = None,` add `color_scale_state: Optional[Dict] = None,`.

Docstring, after the `initial_state` entry:

```
    color_scale_state : dict, optional
        The reader's saved per-column colour-scale choices, as returned by
        ``AgGridResult.color_scale_state``: ``{col_id: False | {"scheme",
        "mode", "reverse"}}``. Read **once, at mount** — change ``key`` to
        apply a different one. Ignored unless the grid is interactive
        (``configure_color_scale(interactive=True)``). Entries for columns the
        grid does not have are kept, not rejected.
```

After `validate_color_scale_columns(grid_options)` add `validate_color_scale_state(color_scale_state)` and extend the import at `:10` to `from st_aggrid.color_scale import validate_color_scale_columns, validate_color_scale_state`.

In the payload dict, after `"initial_state": initial_state,` add `"color_scale_state": color_scale_state,`.

In the `update_on` docstring entry, add: "``"stColorScaleChanged"`` is raised by the component when the reader picks a colour scale from a menu; it cannot be debounced."

- [ ] **Step 5: Implement the result property**

In `st_aggrid/result.py`, after the `grid_state` property:

```python
    @property
    def color_scale_state(self) -> Optional[Dict]:
        """The reader's per-column colour-scale choices, or ``None`` until a
        collect that included ``"stGetColorScaleState"`` has run. Feed it back
        as ``AgGrid(color_scale_state=...)``."""
        if self._grid_state:
            return self._grid_state.get("colorScaleState")
        return None
```

- [ ] **Step 6: Run the tests**

Run: `uv run pytest -m "not e2e" -q`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add st_aggrid/grid_options_builder.py st_aggrid/aggrid.py st_aggrid/result.py test/unit
git commit -m "Add the colour-scale picker's Python surface"
```

---

### Task 4: `overrides.ts` — the pure layer arithmetic

**Files:**
- Create: `st_aggrid/frontend/src/colorScales/overrides.ts`
- Test: `st_aggrid/frontend/src/colorScales/__checks__/overrides.check.ts`

**Interfaces:**
- Consumes: nothing. **This file imports nothing.**
- Produces:
  - `type Override = false | { scheme?: string; mode?: string; reverse?: boolean }`
  - `type Choice = { kind: "none" } | { kind: "reset" } | { kind: "scheme"; scheme: string } | { kind: "mode"; mode: string } | { kind: "reverse"; reverse: boolean }`
  - `PICKABLE_SCHEMES: readonly string[]` = `["neutral", "positive", "diverging", "rank"]`
  - `sanitizeState(raw: unknown): Map<string, Override>`
  - `serializeState(map: Map<string, Override>): Record<string, Override>`
  - `applyChoice(map: Map<string, Override>, colId: string, choice: Choice, hasOwnDeclaration: boolean): void`
  - `declarationCandidates(gridDefaults: unknown, own: unknown, override: Override | undefined): Record<string, unknown>[]` — merged declarations to try, in order; the first that resolves wins; `[]` means unpainted.

- [ ] **Step 1: Write the failing check**

Create `__checks__/overrides.check.ts`:

```ts
/** Runnable check for `overrides.ts`. Run it with:
 *
 *     node st_aggrid/frontend/src/colorScales/__checks__/overrides.check.ts
 *
 * Same arrangement as `normalize.check.ts`: Node 22 strips the types, so the
 * layer arithmetic is tested without a JS test runner. What needs a live grid
 * is in `test/test_grid_color_scale_picker.py`.
 */
import assert from "node:assert/strict"
import {
  applyChoice,
  declarationCandidates,
  sanitizeState,
  serializeState,
} from "../overrides.ts"
import type { Override } from "../overrides.ts"

// --- sanitizeState: junk in, clean map out, never throws -------------------
for (const junk of [undefined, null, 7, "x", [], [["a", false]]]) {
  assert.equal(sanitizeState(junk).size, 0)
}
const clean = sanitizeState({
  a: false,
  b: { scheme: "diverging", mode: "zscore", reverse: true },
  c: { scheme: "fill" }, // not pickable: key dropped, entry kept as {}
  d: { scheme: "rainbow", mode: 3, reverse: "yes", scope: "parent" },
  e: true, // not an override
  f: "neutral",
  g: null,
})
assert.deepEqual([...clean.keys()], ["a", "b", "c", "d"])
assert.equal(clean.get("a"), false)
assert.deepEqual(clean.get("b"), { scheme: "diverging", mode: "zscore", reverse: true })
assert.deepEqual(clean.get("c"), {})
assert.deepEqual(clean.get("d"), {})

// The map owns its entries: mutating the input afterwards changes nothing.
const input = { a: { scheme: "neutral" } }
const owned = sanitizeState(input)
input.a.scheme = "rank"
assert.deepEqual(owned.get("a"), { scheme: "neutral" })

// --- serializeState: a plain, detached object ------------------------------
const plain = serializeState(clean)
assert.deepEqual(plain, {
  a: false,
  b: { scheme: "diverging", mode: "zscore", reverse: true },
  c: {},
  d: {},
})
;(plain.b as { scheme?: string }).scheme = "rank"
assert.deepEqual(clean.get("b"), { scheme: "diverging", mode: "zscore", reverse: true })
assert.deepEqual(serializeState(new Map()), {})

// --- applyChoice ------------------------------------------------------------
const map = new Map<string, Override>()
applyChoice(map, "m", { kind: "scheme", scheme: "neutral" }, false)
assert.deepEqual(map.get("m"), { scheme: "neutral" })
// Keys accumulate; nothing is normalised away.
applyChoice(map, "m", { kind: "mode", mode: "minmax" }, false)
applyChoice(map, "m", { kind: "reverse", reverse: true }, false)
assert.deepEqual(map.get("m"), { scheme: "neutral", mode: "minmax", reverse: true })
applyChoice(map, "m", { kind: "scheme", scheme: "diverging" }, false)
assert.deepEqual(map.get("m"), { scheme: "diverging", mode: "minmax", reverse: true })

// "none" on an undeclared column has nothing to switch off: the entry goes.
applyChoice(map, "m", { kind: "none" }, false)
assert.equal(map.has("m"), false)
// "none" on a declared column must outvote the declaration.
applyChoice(map, "d", { kind: "none" }, true)
assert.equal(map.get("d"), false)
// A choice after "none" starts from scratch, not from `false`.
applyChoice(map, "d", { kind: "reverse", reverse: true }, true)
assert.deepEqual(map.get("d"), { reverse: true })
applyChoice(map, "d", { kind: "reset" }, true)
assert.equal(map.has("d"), false)
// Reset on a column with no entry is a no-op, not an error.
applyChoice(map, "d", { kind: "reset" }, true)
assert.equal(map.size, 0)

// --- declarationCandidates --------------------------------------------------
const GRID = { scheme: "neutral", interactive: true }

// No override: exactly the two-layer behaviour that exists today.
assert.deepEqual(declarationCandidates(GRID, undefined, undefined), [])
assert.deepEqual(declarationCandidates(GRID, null, undefined), [])
assert.deepEqual(declarationCandidates(GRID, false, undefined), [])
assert.deepEqual(declarationCandidates(GRID, true, undefined), [GRID])
assert.deepEqual(declarationCandidates(undefined, { scheme: "rank" }, undefined), [
  { scheme: "rank" },
])
assert.deepEqual(declarationCandidates(GRID, { mode: "minmax" }, undefined), [
  { scheme: "neutral", interactive: true, mode: "minmax" },
])
// A non-object, non-true declaration contributes no keys (as today).
assert.deepEqual(declarationCandidates(GRID, 5, undefined), [GRID])

// `false` from the reader switches a declared column off.
assert.deepEqual(declarationCandidates(GRID, true, false), [])
// The page author's `false` outvotes the reader.
assert.deepEqual(declarationCandidates(GRID, false, { scheme: "rank" }), [])

// An override activates an undeclared column — one candidate, no fallback.
assert.deepEqual(declarationCandidates(GRID, undefined, { scheme: "rank" }), [
  { scheme: "rank", interactive: true },
])
// On a declared column the override wins per key, and the declaration alone
// is the fallback if the merge does not resolve.
assert.deepEqual(
  declarationCandidates(GRID, { mode: "minmax" }, { scheme: "diverging", mode: "anchor" }),
  [
    { scheme: "diverging", interactive: true, mode: "anchor" },
    { scheme: "neutral", interactive: true, mode: "minmax" },
  ]
)

console.log("overrides.check.ts: ok")
```

- [ ] **Step 2: Run it to see it fail**

Run: `node st_aggrid/frontend/src/colorScales/__checks__/overrides.check.ts`
Expected: `ERR_MODULE_NOT_FOUND` for `../overrides.ts`.

- [ ] **Step 3: Implement**

Create `colorScales/overrides.ts`:

```ts
/**
 * The reader's layer of a colour-scale declaration.
 *
 * Resolution has three layers: grid-level defaults, the column's own
 * declaration, and what the reader picked from a menu. This module owns the
 * third one's arithmetic and the order in which merged declarations are tried.
 * It imports nothing, so `__checks__/overrides.check.ts` runs it under plain
 * `node`; turning a merged declaration into a `ResolvedColorScale` stays in
 * `index.ts`.
 *
 * An override stores only what the reader touched, never a full declaration,
 * so a page that later changes its defaults still reaches every column the
 * reader left alone.
 */

/** `false` — unpainted whatever the column declares. An object — merged per
 * key over the two lower layers; activates a column with no declaration. */
export type Override = false | { scheme?: string; mode?: string; reverse?: boolean }

/** One menu action. */
export type Choice =
  | { kind: "none" }
  | { kind: "reset" }
  | { kind: "scheme"; scheme: string }
  | { kind: "mode"; mode: string }
  | { kind: "reverse"; reverse: boolean }

/** `fill` is absent on purpose: it needs a colour, which no menu offers. */
export const PICKABLE_SCHEMES: readonly string[] = [
  "neutral",
  "positive",
  "diverging",
  "rank",
]
const PICKABLE_MODES: readonly string[] = ["minmax", "zscore", "anchor"]

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}

/**
 * The guard copy of Python's `validate_color_scale_state`. Python raises on a
 * malformed state because that is where a developer can act on it; here a bad
 * entry is dropped, because throwing while a grid mounts helps nobody. Returns
 * a map that owns its entries.
 */
export function sanitizeState(raw: unknown): Map<string, Override> {
  const state = new Map<string, Override>()
  if (!isPlainObject(raw)) return state

  for (const [colId, entry] of Object.entries(raw)) {
    if (entry === false) {
      state.set(colId, false)
      continue
    }
    if (!isPlainObject(entry)) continue

    const override: Exclude<Override, false> = {}
    if (typeof entry.scheme === "string" && PICKABLE_SCHEMES.includes(entry.scheme)) {
      override.scheme = entry.scheme
    }
    if (typeof entry.mode === "string" && PICKABLE_MODES.includes(entry.mode)) {
      override.mode = entry.mode
    }
    if (typeof entry.reverse === "boolean") override.reverse = entry.reverse
    state.set(colId, override)
  }
  return state
}

/** A plain, detached object — what the collector posts to Python. */
export function serializeState(map: Map<string, Override>): Record<string, Override> {
  const out: Record<string, Override> = {}
  for (const [colId, entry] of map) out[colId] = entry === false ? false : { ...entry }
  return out
}

/**
 * The menu's one write path.
 *
 * "none" writes `false` only where there is a declaration to outvote; on an
 * undeclared column there is nothing to switch off, and deleting the entry
 * keeps the saved state free of noise. Keys accumulate as written and are
 * never normalised away — "reset" is the only thing that removes them.
 */
export function applyChoice(
  map: Map<string, Override>,
  colId: string,
  choice: Choice,
  hasOwnDeclaration: boolean
): void {
  if (choice.kind === "reset") {
    map.delete(colId)
    return
  }
  if (choice.kind === "none") {
    if (hasOwnDeclaration) map.set(colId, false)
    else map.delete(colId)
    return
  }

  const current = map.get(colId)
  const next: Exclude<Override, false> = current ? { ...current } : {}
  if (choice.kind === "scheme") next.scheme = choice.scheme
  else if (choice.kind === "mode") next.mode = choice.mode
  else next.reverse = choice.reverse
  map.set(colId, next)
}

/**
 * The merged declarations to try, in order; the first that resolves wins and
 * an empty list means "unpainted".
 *
 * With `override === undefined` this is exactly the two-layer rule that
 * predates the picker: a column is painted only when its own declaration is
 * present and not `false`. An override object adds a first candidate — and is
 * the only candidate on an undeclared column. The declaration-only fallback is
 * what keeps a stale saved choice (say `mode: "anchor"` on a column that has
 * since lost its `anchor`) from blanking a column the page still declares.
 *
 * The page author's `false` outvotes the reader: it is an explicit "not this
 * column", and the menu does not offer such a column either.
 */
export function declarationCandidates(
  gridDefaults: unknown,
  own: unknown,
  override: Override | undefined
): Record<string, unknown>[] {
  if (own === false || override === false) return []

  const hasOwn = own !== undefined && own !== null
  if (!hasOwn && override === undefined) return []

  const base = isPlainObject(gridDefaults) ? gridDefaults : {}
  const declared = isPlainObject(own) ? own : {}

  const candidates: Record<string, unknown>[] = []
  if (override !== undefined) candidates.push({ ...base, ...declared, ...override })
  if (hasOwn) candidates.push({ ...base, ...declared })
  return candidates
}
```

- [ ] **Step 4: Run the check**

Run: `node st_aggrid/frontend/src/colorScales/__checks__/overrides.check.ts`
Expected: prints `overrides.check.ts: ok`, exit code 0. Also run the two existing checks to confirm nothing about the runner changed:
`node st_aggrid/frontend/src/colorScales/__checks__/normalize.check.ts && node st_aggrid/frontend/src/colorScales/__checks__/schemes.check.ts`

- [ ] **Step 5: Commit**

```bash
git add st_aggrid/frontend/src/colorScales/overrides.ts st_aggrid/frontend/src/colorScales/__checks__/overrides.check.ts
git commit -m "Add the reader's override layer for colour scales"
```

---

### Task 5: The third layer in the grid — resolver, slots, injection, restore

**Files:**
- Modify: `st_aggrid/frontend/src/colorScales/index.ts`
- Modify: `st_aggrid/frontend/src/utils/parsers.ts`
- Modify: `st_aggrid/frontend/src/types/AgGridTypes.ts`
- Modify: `st_aggrid/frontend/src/AgGridComponent.tsx` (new ref before the `gridOptions` memo at `:399`; both `parseGridOptions` call sites)
- Create: `test/color_scale_dom.py`
- Modify: `test/test_grid_color_scale.py:51-111` (helpers move out)
- Create: `test/grid_color_scale_picker.py`
- Create: `test/test_grid_color_scale_picker.py`

**Interfaces:**
- Consumes: `Override`, `sanitizeState`, `declarationCandidates` (Task 4); the `color_scale_state` payload key (Task 3).
- Produces (all exported from `colorScales/index.ts` unless noted):
  - `ST_COLOR_SCALE_OVERRIDES = "stColorScaleOverrides"`
  - `isInteractive(gridContext: unknown): boolean`
  - `lowerLayers(colDef: ColDef | null | undefined, gridContext: unknown): Record<string, unknown>` — grid defaults merged with the column's own declaration, no override
  - `readColorScaleConfig(colDef, gridContext, override?: Override): ResolvedColorScale | null`
  - `sourceColumnOf(colDef: ColDef | null | undefined, column: Column | null | undefined): Column | null`
  - `resolveFor(colDef, column, gridContext): ResolvedColorScale | null`
  - `interface ColorScaleRuntime { overrides: Map<string, Override>; onChange: (colId: string) => void }`
  - `parseGridOptions(data, streamlitTheme?, runtime?: ColorScaleRuntime)` (in `utils/parsers.ts`)
  - In `AgGridComponent.tsx`: `colorScaleRuntimeRef` (stable per mount) and `colorScaleChangeRef: MutableRefObject<(colId: string) => void>`, a no-op until Task 7 assigns it.
  - E2E app grid indices (fixed for Tasks 6-7): `0` flat interactive, `1` pivot interactive with Columns side bar, `2` flat not interactive, `3` interactive with a caller `getMainMenuItems`, `4` interactive state round trip, `5` pivot mounted with a saved state.
  - `test/color_scale_dom.py`: `assert_painted`, `assert_unpainted`, `font_weight`.

- [ ] **Step 1: Move the shared DOM assertions into their own module**

Create `test/color_scale_dom.py` with this header, then move `_alpha_channel`, `assert_painted`, `assert_unpainted` and `font_weight` from `test/test_grid_color_scale.py` (`:51-111`) into it **verbatim**, docstrings included:

```python
"""Colour assertions shared by the colour-scale e2e suites.

Lived in `test_grid_color_scale.py` until the picker suite needed the same
alpha-quantisation rule; two copies of that rule would drift.
"""

from playwright.sync_api import Page

from color_scale_fixture import half_up, is_scheme_color
```

In `test_grid_color_scale.py` delete the four definitions and add `from color_scale_dom import assert_painted, assert_unpainted, font_weight`. Remove `half_up` and `is_scheme_color` from its `color_scale_fixture` import only if nothing else in the file uses them (`grep -n "half_up\|is_scheme_color" test/test_grid_color_scale.py`).

Run: `uv run pytest test/test_grid_color_scale.py -q`
Expected: all PASS — a pure move.

- [ ] **Step 2: Write the e2e app**

Create `test/grid_color_scale_picker.py`:

```python
"""Streamlit app: the reader's per-column colour-scale picker.

Grids over `color_scale_fixture.py`, which also owns the expected colours:

  0  flat, interactive — a declared column (`metric_a`), an undeclared numeric
     one (`metric_b`), a text column, a `fill` column, a column with its own
     `cellStyle`, and a column the page switched off with `False`. Its
     `update_on` does not name `stColorScaleChanged`, so a menu action must
     repaint without a rerun; `runs=` is the counter that proves it.
  1  pivot, interactive, Columns side bar open — one choice must reach every
     result column of a metric, from a header and from the panel.
  2  flat, NOT interactive — the same columns as the picker would touch. Must
     behave exactly as it did before the picker existed.
  3  interactive, with a caller-supplied `getMainMenuItems` — the built-in
     item is appended, the caller's is kept.
  4  interactive, state round trip — mounted with a saved choice, collects
     `stGetColorScaleState` on `stColorScaleChanged`, feeds the result back,
     can be remounted (`remount`) and config-updated (`flip option`).
  5  pivot, interactive, mounted with a saved choice — the override layer in
     pivot mode with no menu involved.

Grids keep their indices; a new grid is always appended.

Run standalone with:  streamlit run test/grid_color_scale_picker.py
"""

import json

import streamlit as st

from st_aggrid import AgGrid, JsCode

from color_scale_fixture import color_scale_dataframe

df = color_scale_dataframe()

COMMON_OPTIONS = {
    "suppressColumnVirtualisation": True,
    "suppressRowVirtualisation": True,
    "animateRows": False,
}
INTERACTIVE = {"stColorScale": {"interactive": True}}

#: Flat grey, nothing a scheme would ever produce.
OWN_STYLE = JsCode("function(params) { return {backgroundColor: 'rgb(1, 2, 3)'}; }")
FILL_COLOR = "rgb(9, 8, 7)"

CALLER_MENU = JsCode(
    """function(params) {
         return params.defaultItems.concat([{name: 'Caller item'}]);
       }"""
)

st.session_state.runs = st.session_state.get("runs", 0) + 1
st.text(f"runs={st.session_state.runs}")


def metric(field, color_scale=None, col_id=None, **extra):
    col = {"colId": col_id or field, "field": field, "width": 130, **extra}
    if color_scale is not None:
        col["context"] = {"stColorScale": color_scale}
    return col


def flat_columns():
    return [
        {"colId": "region", "field": "region"},
        {"colId": "country", "field": "country"},
        metric("metric_a", {"scheme": "neutral"}),
        metric("metric_b"),
    ]


def pivot_columns():
    return [
        {"colId": "country", "field": "country", "rowGroup": True},
        {"colId": "region", "field": "region", "pivot": True},
        metric("metric_a", {"scheme": "neutral"}, aggFunc="sum"),
        metric("metric_b", aggFunc="sum"),
    ]


st.subheader("0 flat, interactive")
AgGrid(
    df,
    grid_options={
        **COMMON_OPTIONS,
        "context": INTERACTIVE,
        "columnDefs": [
            *flat_columns(),
            metric("metric_c", {"scheme": "fill", "color": FILL_COLOR}),
            metric("ratio", col_id="ratio_own", cellStyle=OWN_STYLE),
            metric("ratio", False, col_id="ratio_off"),
        ],
    },
    height=300,
    allow_unsafe_jscode=True,
    enable_enterprise_modules=True,
    key="picker_flat",
)

st.subheader("1 pivot, interactive, Columns panel")
AgGrid(
    df,
    grid_options={
        **COMMON_OPTIONS,
        "context": INTERACTIVE,
        "pivotMode": True,
        "sideBar": {"toolPanels": ["columns"], "defaultToolPanel": "columns"},
        "columnDefs": pivot_columns(),
    },
    height=420,
    enable_enterprise_modules=True,
    key="picker_pivot",
)

st.subheader("2 flat, not interactive")
AgGrid(
    df,
    grid_options={**COMMON_OPTIONS, "columnDefs": flat_columns()},
    height=300,
    enable_enterprise_modules=True,
    key="picker_off",
)

st.subheader("3 interactive, caller getMainMenuItems")
AgGrid(
    df,
    grid_options={
        **COMMON_OPTIONS,
        "context": INTERACTIVE,
        "getMainMenuItems": CALLER_MENU,
        "columnDefs": flat_columns(),
    },
    height=300,
    allow_unsafe_jscode=True,
    enable_enterprise_modules=True,
    key="picker_caller",
)

st.subheader("4 interactive, state round trip")
if "picker_saved" not in st.session_state:
    st.session_state.picker_saved = {"metric_b": {"scheme": "diverging"}}
    st.session_state.picker_mount = 0


def _remount():
    st.session_state.picker_mount += 1


st.button("remount", on_click=_remount)
flip = st.checkbox("flip option")
state_result = AgGrid(
    df,
    grid_options={
        **COMMON_OPTIONS,
        "context": INTERACTIVE,
        # Unrelated to colour: only here to send a rerun down the
        # `updateGridOptions` path.
        "suppressMovableColumns": bool(flip),
        "columnDefs": flat_columns(),
    },
    height=300,
    color_scale_state=st.session_state.picker_saved,
    collect=["stGetColorScaleState"],
    update_on=["stColorScaleChanged"],
    enable_enterprise_modules=True,
    key=f"picker_state_{st.session_state.picker_mount}",
)
if state_result.color_scale_state is not None:
    st.session_state.picker_saved = state_result.color_scale_state
st.text("state=" + json.dumps(state_result.color_scale_state, sort_keys=True))

st.subheader("5 pivot, mounted with a saved choice")
AgGrid(
    df,
    grid_options={
        **COMMON_OPTIONS,
        "context": INTERACTIVE,
        "pivotMode": True,
        "columnDefs": pivot_columns(),
    },
    height=300,
    color_scale_state={"metric_a": {"scheme": "diverging"}, "metric_b": {"scheme": "positive"}},
    enable_enterprise_modules=True,
    key="picker_pivot_saved",
)
```

- [ ] **Step 3: Write the failing e2e tests (restore only — no menu yet)**

Create `test/test_grid_color_scale_picker.py`:

```python
"""The reader's colour-scale picker, driven through a real grid.

Every expected colour comes from `color_scale_fixture.expected_rgba`, never
from a number typed here. Rows are addressed by `row-index`, never by document
order (`grid_dom.py` says why).
"""

import re
import time
from pathlib import Path

import pytest
from playwright.sync_api import Page

from color_scale_dom import assert_painted, assert_unpainted
from color_scale_fixture import column_values, expected_rgba, region_values
from e2e_utils import StreamlitRunner
from grid_dom import cell_backgrounds

ROOT_DIRECTORY = Path(__file__).parent.parent.absolute()
APP_FILE = ROOT_DIRECTORY / "test" / "grid_color_scale_picker.py"

FLAT_GRID = 0
PIVOT_GRID = 1
OFF_GRID = 2
CALLER_GRID = 3
STATE_GRID = 4
PIVOT_SAVED_GRID = 5
GRID_COUNT = 6

#: Body rows in fixture order: DE, FR, IT (EU) then CA, NY, TX (US). The pivot
#: grids group by country, so they have the same six rows in the same order.
ROWS = tuple(f"body:{index}" for index in range(6))


def flat_values(field: str) -> dict[str, float]:
    return dict(zip(ROWS, column_values(field)))


def pivot_values(region: str, field: str) -> dict[str, float | None]:
    """One pivot result column: a region's countries carry a value, every
    other row is an empty cell."""
    values = region_values(region, field)
    offset = 0 if region == "EU" else 3
    return {
        row: (values[index - offset] if offset <= index < offset + 3 else None)
        for index, row in enumerate(ROWS)
    }


def eventually(check, timeout: float = 5.0) -> None:
    """Re-run `check` until it stops raising. A menu action repaints on the
    next frame and a rerun lands later still; polling beats a fixed sleep."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            return check()
        except (AssertionError, KeyError):
            if time.monotonic() > deadline:
                raise
            time.sleep(0.1)


def assert_column(
    page: Page,
    grid: int,
    col_id: str,
    scheme: str,
    values_by_row: dict,
    population=None,
    **expected_kwargs,
) -> None:
    """Every cell of one column is painted exactly as `scheme` dictates over
    `population` (default: the column's own non-empty values)."""
    if population is None:
        population = [v for v in values_by_row.values() if v is not None]

    def check():
        backgrounds = cell_backgrounds(page, grid)
        for row, value in values_by_row.items():
            where = f"grid {grid} {col_id} {row}"
            actual = backgrounds[row][col_id]
            expected = expected_rgba(scheme, population, value, **expected_kwargs)
            if expected is None:
                assert_unpainted(actual, scheme, where)
            else:
                assert_painted(actual, expected, where)

    eventually(check)


def assert_column_unpainted(page: Page, grid: int, col_id: str, *schemes: str) -> None:
    def check():
        backgrounds = cell_backgrounds(page, grid)
        for row in ROWS:
            for scheme in schemes:
                assert_unpainted(backgrounds[row][col_id], scheme, f"grid {grid} {col_id} {row}")

    eventually(check)


def marker(page: Page, prefix: str) -> str:
    """The value of one `st.text("<prefix>=<value>")` line of the app."""
    text = page.get_by_text(re.compile(rf"^{prefix}=")).first.inner_text()
    return text.split("=", 1)[1]


@pytest.fixture(autouse=True, scope="module")
def streamlit_app():
    with StreamlitRunner(APP_FILE) as runner:
        yield runner


@pytest.fixture(autouse=True, scope="function")
def go_to_app(page: Page, streamlit_app: StreamlitRunner):
    page.set_viewport_size({"width": 1400, "height": 1000})
    page.goto(streamlit_app.server_url)
    page.wait_for_function(
        f"() => document.querySelectorAll('.ag-root-wrapper').length >= {GRID_COUNT}",
        timeout=60000,
    )
    # The last grid is a pivot: wait until it has rendered its six group rows.
    page.wait_for_function(
        f"""() => {{
             const grid = document.querySelectorAll('.ag-root-wrapper')[{PIVOT_SAVED_GRID}];
             return !!grid && grid.querySelectorAll('.ag-cell[col-id^="pivot_"]').length >= 6;
           }}""",
        timeout=60000,
    )


# ---------------------------------------------------------------------------
# Restore: the saved choice is a resolution layer, present before first paint
# ---------------------------------------------------------------------------


def test_a_saved_choice_activates_an_undeclared_column(page: Page):
    assert_column(page, STATE_GRID, "metric_b", "diverging", flat_values("metric_b"))
    # The declared neighbour is untouched by someone else's entry.
    assert_column(page, STATE_GRID, "metric_a", "neutral", flat_values("metric_a"))


def test_a_saved_choice_reaches_every_pivot_result_column(page: Page):
    for region in ("EU", "US"):
        assert_column(
            page,
            PIVOT_SAVED_GRID,
            f"pivot_region_{region}_metric_a",
            "diverging",
            pivot_values(region, "metric_a"),
        )
        assert_column(
            page,
            PIVOT_SAVED_GRID,
            f"pivot_region_{region}_metric_b",
            "positive",
            pivot_values(region, "metric_b"),
        )


def test_an_interactive_grid_paints_its_declarations_as_before(page: Page):
    assert_column(page, FLAT_GRID, "metric_a", "neutral", flat_values("metric_a"))
    assert_column_unpainted(page, FLAT_GRID, "metric_b", "neutral", "positive", "diverging")


def test_a_grid_without_the_opt_in_is_unchanged(page: Page):
    assert_column(page, OFF_GRID, "metric_a", "neutral", flat_values("metric_a"))
    assert_column_unpainted(page, OFF_GRID, "metric_b", "neutral", "positive", "diverging")
```

Note on the pivot population: a pivot result column's level-scoped population is the three countries that carry a value in it, which is what `assert_column`'s default (`non-empty values of the column`) reproduces. `test_grid_color_scale.py`'s pivot test makes the same assumption; if the two disagree, read that test before changing this one.

- [ ] **Step 4: Run them to see the restore tests fail**

Run: `uv run pytest test/test_grid_color_scale_picker.py -v`
Expected: `test_a_saved_choice_activates_an_undeclared_column` and `test_a_saved_choice_reaches_every_pivot_result_column` FAIL (cells unpainted / still neutral). The other two PASS already — they pin today's behaviour and must stay green through every later task.

- [ ] **Step 5: Implement the resolver layer in `colorScales/index.ts`**

Add imports:

```ts
import { Override, declarationCandidates } from "./overrides"
```

Below `ST_COLOR_SCALE` add:

```ts
/** Reserved key of the grid `context` that holds the reader's live choices —
 * a `Map<sourceColId, Override>` owned by `AgGridComponent` and injected by
 * `parseGridOptions`. It lives in `context` rather than on a colDef because
 * `updateGridOptions` installs fresh colDefs on every config rerun, and
 * because a pivot result column's `colDef.context` is a copy, not the source
 * column's object (measured 2026-09-20). `params.context`, by contrast, is the
 * grid's own object by identity. Matches `color_scale.py`'s
 * COLOR_SCALE_OVERRIDES_CONTEXT_KEY. */
export const ST_COLOR_SCALE_OVERRIDES = "stColorScaleOverrides"

/** What `AgGridComponent` hands to `parseGridOptions`: the live choices and
 * the callback a menu action reports to. */
export interface ColorScaleRuntime {
  overrides: Map<string, Override>
  onChange: (colId: string) => void
}

function gridDeclaration(gridContext: unknown): unknown {
  return (gridContext as Record<string, unknown> | undefined)?.[ST_COLOR_SCALE]
}

function ownDeclaration(colDef: ColDef | null | undefined): unknown {
  return (colDef?.context as Record<string, unknown> | undefined)?.[ST_COLOR_SCALE]
}

/** The grid-level opt-in for the reader's picker. */
export function isInteractive(gridContext: unknown): boolean {
  const declaration = gridDeclaration(gridContext)
  return (
    !!declaration &&
    typeof declaration === "object" &&
    (declaration as Record<string, unknown>).interactive === true
  )
}

/** Grid defaults merged with the column's own declaration — the two layers
 * below the reader's. The menu reads it to know whether an `anchor` exists. */
export function lowerLayers(
  colDef: ColDef | null | undefined,
  gridContext: unknown
): Record<string, unknown> {
  const own = ownDeclaration(colDef)
  const [merged] = declarationCandidates(
    gridDeclaration(gridContext),
    own === undefined || own === null || own === false ? true : own,
    undefined
  )
  return merged ?? {}
}
```

Split `readColorScaleConfig` in two. Everything from `const schemeName =` to the final `return null` becomes the body of a new private function, unchanged:

```ts
/** Turn one merged declaration into what it paints, or `null`. */
function resolveMerged(merged: Declaration): ResolvedColorScale | null {
  const schemeName =
    merged.scheme ?? (merged.mode === "anchor" ? "diverging" : undefined)
  // … the existing body, verbatim, through the final `return null`
}
```

and `readColorScaleConfig` becomes:

```ts
export function readColorScaleConfig(
  colDef: ColDef | null | undefined,
  gridContext: unknown,
  override?: Override
): ResolvedColorScale | null {
  const candidates = declarationCandidates(
    gridDeclaration(gridContext),
    ownDeclaration(colDef),
    override
  )
  for (const candidate of candidates) {
    const resolved = resolveMerged(candidate as Declaration)
    if (resolved) return resolved
  }
  return null
}
```

Extend its docstring with a paragraph: the optional third argument is the reader's layer; with it absent the function is the two-layer rule unchanged; the candidate order and the fallback are documented on `declarationCandidates`.

Add:

```ts
/** The column a choice is keyed by: a pivot result column stands for its
 * value column, so one choice on a metric reaches every pivot key. */
export function sourceColumnOf(
  colDef: ColDef | null | undefined,
  column: Column | null | undefined
): Column | null {
  return colDef?.pivotValueColumn ?? column ?? null
}

/** Resolve a displayed column including the reader's layer. The one place
 * that looks a choice up, shared by the cell style and the invalidation. */
export function resolveFor(
  colDef: ColDef | null | undefined,
  column: Column | null | undefined,
  gridContext: unknown
): ResolvedColorScale | null {
  const overrides = (gridContext as Record<string, unknown> | undefined)?.[
    ST_COLOR_SCALE_OVERRIDES
  ]
  const colId = sourceColumnOf(colDef, column)?.getColId()
  const override =
    overrides instanceof Map && colId !== undefined
      ? (overrides.get(colId) as Override | undefined)
      : undefined
  return readColorScaleConfig(colDef, gridContext, override)
}
```

In `stColorScaleCellStyle` replace the first two lines of the body with:

```ts
  const config = resolveFor(params.colDef, params.column, params.context)
  // `null` keeps ag-grid-react's previous inline style. Harmless while a
  // declaration can only ever be absent from the start; on an interactive grid
  // the reader can remove one ("None"), and the old colour would stay.
  if (!config) return isInteractive(params.context) ? { ...UNPAINTED } : null
```

and update the function's docstring first sentence to: "Returns `null` only when no declaration resolves **on a grid without the picker**."

In `paintedColumnIds` replace the filter with:

```ts
    .filter((column) => resolveFor(column.getColDef(), column, context) !== null)
```

Rewrite `registerColorScales`'s body:

```ts
  const interactive = isInteractive(gridOptions.context)
  let warnedDefaultColDef = false

  eachColDef(gridOptions.columnDefs, (def) => {
    const declared = readColorScaleConfig(def, gridOptions.context) !== null
    // Without the picker: same predicate `paintedColumnIds` and
    // `stColorScaleCellStyle` use — a declaration that resolves to nothing
    // must not occupy the slot. With it, the slot has to exist *before* the
    // reader asks: a choice is a context mutation plus `refreshCells`, and
    // there is nothing to refresh on a column that carries no function.
    if (!declared && !interactive) return

    const source = callerCellStyleSource(def, gridOptions)
    if (source) {
      const colId = def.colId ?? def.field
      if (source === "defaultColDef.cellStyle") {
        if (interactive) {
          if (!warnedDefaultColDef) {
            warnedDefaultColDef = true
            console.warn(
              `[st_aggrid] This grid is interactive for colour scales, but ` +
                `defaultColDef.cellStyle wins for every column, so the built-in ` +
                `was not attached anywhere: nothing will be painted and the ` +
                `picker is unavailable.`
            )
          }
        } else {
          console.warn(
            `[st_aggrid] "${colId}" declares a colour scale, but defaultColDef.cellStyle ` +
              `wins for every column in this grid, so the built-in was not attached and ` +
              `"${colId}" will not be painted.`
          )
        }
      } else if (debug && declared) {
        console.log(
          `[st_aggrid] cellStyle on "${colId}" was supplied ` +
            `by ${source} and overrides the built-in colour scale.`
        )
      }
      return
    }
    def.cellStyle = stColorScaleCellStyle
  })

  return gridOptions
```

Update its docstring: replace the paragraph beginning "The attached function does not close over the declaration" so that it ends "…The reader's picker relies on exactly that: a choice changes the override map and refreshes, with nothing re-attached. On an interactive grid every column without a caller-supplied `cellStyle` gets the built-in, declared or not." and add that the `defaultColDef` warning is raised once per grid in that mode.

- [ ] **Step 6: Inject the map in `utils/parsers.ts`**

Change the import to `import { ColorScaleRuntime, ST_COLOR_SCALE_OVERRIDES, isInteractive, registerColorScales } from "../colorScales"`, the signature to

```ts
export function parseGridOptions(
  data: AgGridData,
  streamlitTheme?: StreamlitThemeInfo | null,
  colorScaleRuntime?: ColorScaleRuntime
): GridOptions {
```

and after `registerColorScales(gridOptions, data.debug === true)` add:

```ts
  // The reader's choices. Injected after the `cloneDeep` above, so every parse
  // — the mount and each live config update — hands AG-Grid a fresh `context`
  // object carrying the *same* map. That is what lets a choice survive
  // `updateGridOptions`, and being in `context` before the first cell is
  // styled is what lets a restored choice paint with no unpainted flash.
  // `context` is known to be an object here: `isInteractive` read it.
  if (colorScaleRuntime && isInteractive(gridOptions.context)) {
    gridOptions.context[ST_COLOR_SCALE_OVERRIDES] = colorScaleRuntime.overrides
  }
```

- [ ] **Step 7: Types**

In `types/AgGridTypes.ts`, after `initial_state?: any` add `color_scale_state?: unknown`.

- [ ] **Step 8: Own the map in `AgGridComponent.tsx`**

Imports: extend the colour-scale import to `import { ColorScaleRuntime, attachColorScaleInvalidation, clearStats } from "./colorScales"` and add `import { sanitizeState } from "./colorScales/overrides"`.

Directly below `rowGroupOrderCleanupRef` (the ref block that Task 1 shortened) add:

```tsx
  // The reader's per-column colour-scale choices, and the hook a menu action
  // reports to. One object per mount, created on first render: `parseGridOptions`
  // injects this same map into every `context` it builds, so a choice outlives
  // `updateGridOptions`. Seeded from `color_scale_state`, which is therefore
  // read at mount only — a live prop would inherit the capture<->prop lag that
  // `columns_state` has (two quick clicks, and the rerun from the first writes
  // the prop back over the second). A view switch remounts by `key` anyway.
  const colorScaleChangeRef = useRef<(colId: string) => void>(() => {})
  const colorScaleRuntimeRef = useRef<ColorScaleRuntime | null>(null)
  if (colorScaleRuntimeRef.current === null) {
    colorScaleRuntimeRef.current = {
      overrides: sanitizeState(data.color_scale_state),
      onChange: (colId) => colorScaleChangeRef.current(colId),
    }
  }
```

In the `gridOptions` memo change the first line to
`const go = parseGridOptions(data, streamlitTheme, colorScaleRuntimeRef.current ?? undefined)`,
and in the config-update effect change `const go = parseGridOptions(data)` to
`const go = parseGridOptions(data, undefined, colorScaleRuntimeRef.current ?? undefined)`.

- [ ] **Step 9: Build and run**

Run: `cd st_aggrid/frontend && COREPACK_ENABLE_DOWNLOAD_PROMPT=0 corepack yarn build && cd ../.. && node st_aggrid/frontend/src/colorScales/__checks__/overrides.check.ts && uv run pytest test/test_grid_color_scale_picker.py test/test_grid_color_scale.py -v`
Expected: all PASS. `test_a_saved_choice_reaches_every_pivot_result_column` is the milestone the spike could not reach — if it fails while the flat restore passes, the fault is in `sourceColumnOf`/`resolveFor`, not in the map injection.

- [ ] **Step 10: Commit (without the build)**

```bash
git add st_aggrid/frontend/src test/color_scale_dom.py test/test_grid_color_scale.py test/grid_color_scale_picker.py test/test_grid_color_scale_picker.py
git commit -m "Resolve colour scales through the reader's override layer"
```

---

### Task 6: The menu — three surfaces, two hooks

**Files:**
- Create: `st_aggrid/frontend/src/colorScales/menu.ts`
- Modify: `st_aggrid/frontend/src/utils/parsers.ts`
- Test: `test/test_grid_color_scale_picker.py`

**Interfaces:**
- Consumes: `ColorScaleRuntime`, `ST_COLOR_SCALE`, `clearStats`, `isInteractive`, `lowerLayers`, `readColorScaleConfig`, `sourceColumnOf`, `stColorScaleCellStyle` (Task 5); `Choice`, `applyChoice` (Task 4).
- Produces: `registerColorScaleMenu(gridOptions: GridOptions, runtime: ColorScaleRuntime): GridOptions` and `isEligible(source: Column, gridContext: unknown): boolean`, both from `colorScales/menu.ts`. `runtime.onChange(colId)` is called once after every menu action, after the repaint.

- [ ] **Step 1: Add the menu helpers and the failing tests**

Append to `test/test_grid_color_scale_picker.py`, above the first test:

```python
from color_scale_fixture import RANK_RGBA  # merge into the import at the top

MENU_ITEM = "Colour scale"


def grid_locator(page: Page, grid: int):
    return page.locator(".ag-root-wrapper").nth(grid)


def open_header_menu(page: Page, grid: int, col_id: str) -> None:
    header = grid_locator(page, grid).locator(f'.ag-header-cell[col-id="{col_id}"]')
    header.scroll_into_view_if_needed()
    header.hover()
    header.locator(".ag-header-cell-menu-button").first.click()
    page.locator(".ag-menu-option").first.wait_for(state="visible")


def open_cell_menu(page: Page, grid: int, col_id: str, row_index: int = 1) -> None:
    cell = grid_locator(page, grid).locator(
        f'.ag-row[row-index="{row_index}"] .ag-cell[col-id="{col_id}"]'
    )
    cell.scroll_into_view_if_needed()
    cell.click(button="right")
    page.locator(".ag-menu-option").first.wait_for(state="visible")


def open_panel_menu(page: Page, grid: int, label: str) -> None:
    """Right-click a column's row in the Columns tool panel."""
    row = grid_locator(page, grid).locator(".ag-column-select-column", has_text=label).first
    row.scroll_into_view_if_needed()
    row.click(button="right")
    page.locator(".ag-menu-option").first.wait_for(state="visible")


def option(page: Page, name: str):
    return page.locator(
        ".ag-menu-option", has=page.locator(f'.ag-menu-option-text:text-is("{name}")')
    ).last


def has_option(page: Page, name: str) -> bool:
    return page.locator(f'.ag-menu-option-text:text-is("{name}")').count() > 0


def pick(page: Page, *path: str) -> None:
    """Walk an open menu by visible names; hovering opens a sub menu, the
    last name is clicked."""
    for index, name in enumerate(path):
        target = option(page, name)
        target.wait_for(state="visible")
        if index < len(path) - 1:
            target.hover()
        else:
            target.click()


def ticked(page: Page) -> list[str]:
    return page.evaluate(
        """() => [...document.querySelectorAll('.ag-menu-option')]
             .filter(o => o.querySelector('.ag-menu-option-icon .ag-icon-tick'))
             .map(o => o.querySelector('.ag-menu-option-text').textContent.trim())"""
    )


def close_menu(page: Page) -> None:
    page.keyboard.press("Escape")
    page.locator(".ag-menu").first.wait_for(state="hidden")
```

Append the tests:

```python
# ---------------------------------------------------------------------------
# The menu
# ---------------------------------------------------------------------------


def test_header_menu_paints_an_undeclared_column_without_a_rerun(page: Page):
    runs = marker(page, "runs")
    open_header_menu(page, FLAT_GRID, "metric_b")
    pick(page, MENU_ITEM, "Diverging")
    assert_column(page, FLAT_GRID, "metric_b", "diverging", flat_values("metric_b"))
    # `stColorScaleChanged` is not in this grid's `update_on`.
    assert marker(page, "runs") == runs


def test_cell_menu_ticks_the_current_value_and_changes_mode_and_direction(page: Page):
    values = flat_values("metric_a")

    open_cell_menu(page, FLAT_GRID, "metric_a")
    option(page, MENU_ITEM).hover()
    option(page, "Mode").hover()
    assert set(ticked(page)) == {"Neutral", "Z-score"}
    pick(page, "Min–max")
    assert_column(page, FLAT_GRID, "metric_a", "neutral", values, mode="minmax")

    open_cell_menu(page, FLAT_GRID, "metric_a")
    pick(page, MENU_ITEM, "Reverse")
    assert_column(page, FLAT_GRID, "metric_a", "neutral", values, mode="minmax", reverse=True)

    open_cell_menu(page, FLAT_GRID, "metric_a")
    option(page, MENU_ITEM).hover()
    option(page, "Mode").hover()
    assert set(ticked(page)) == {"Neutral", "Min–max", "Reverse"}
    close_menu(page)


def test_rank_is_offered_and_disables_mode(page: Page):
    open_header_menu(page, FLAT_GRID, "metric_a")
    pick(page, MENU_ITEM, "Rank")

    def best_is_marked():
        backgrounds = cell_backgrounds(page, FLAT_GRID)
        assert_painted(backgrounds["body:5"]["metric_a"], RANK_RGBA, "rank winner")
        assert_unpainted(backgrounds["body:0"]["metric_a"], "neutral", "rank loser")

    eventually(best_is_marked)

    open_header_menu(page, FLAT_GRID, "metric_a")
    option(page, MENU_ITEM).hover()
    assert "ag-menu-option-disabled" in (option(page, "Mode").get_attribute("class") or "")
    close_menu(page)


def test_none_clears_the_colour_and_reset_restores_the_declaration(page: Page):
    open_header_menu(page, FLAT_GRID, "metric_a")
    pick(page, MENU_ITEM, "None")
    # The regression this guards: `cellStyle` returning `null` would leave the
    # old colour on the cell.
    assert_column_unpainted(page, FLAT_GRID, "metric_a", "neutral")

    open_header_menu(page, FLAT_GRID, "metric_a")
    option(page, MENU_ITEM).hover()
    assert ticked(page) == ["None"]
    pick(page, "Reset to default")
    assert_column(page, FLAT_GRID, "metric_a", "neutral", flat_values("metric_a"))

    open_header_menu(page, FLAT_GRID, "metric_a")
    option(page, MENU_ITEM).hover()
    assert not has_option(page, "Reset to default")
    close_menu(page)


@pytest.mark.parametrize("col_id", ["region", "metric_c", "ratio_own", "ratio_off"])
def test_ineligible_columns_offer_no_item(page: Page, col_id: str):
    """Text, `fill`, a caller's `cellStyle`, and the page author's `False`."""
    open_header_menu(page, FLAT_GRID, col_id)
    assert not has_option(page, MENU_ITEM)
    close_menu(page)
    open_cell_menu(page, FLAT_GRID, col_id)
    assert not has_option(page, MENU_ITEM)
    close_menu(page)


def test_a_grid_without_the_opt_in_offers_no_item(page: Page):
    open_header_menu(page, OFF_GRID, "metric_a")
    assert has_option(page, "Sort Ascending")  # it is the real menu
    assert not has_option(page, MENU_ITEM)
    close_menu(page)
    open_cell_menu(page, OFF_GRID, "metric_a")
    assert not has_option(page, MENU_ITEM)
    close_menu(page)


def test_a_header_choice_repaints_every_pivot_result_column(page: Page):
    open_header_menu(page, PIVOT_GRID, "pivot_region_EU_metric_a")
    pick(page, MENU_ITEM, "Diverging")
    for region in ("EU", "US"):
        assert_column(
            page,
            PIVOT_GRID,
            f"pivot_region_{region}_metric_a",
            "diverging",
            pivot_values(region, "metric_a"),
        )


def test_the_columns_panel_offers_the_same_menu(page: Page):
    open_panel_menu(page, PIVOT_GRID, "Metric_b")
    pick(page, MENU_ITEM, "Positive")
    for region in ("EU", "US"):
        assert_column(
            page,
            PIVOT_GRID,
            f"pivot_region_{region}_metric_b",
            "positive",
            pivot_values(region, "metric_b"),
        )
    # Reopened from the panel, the tick reflects the choice just made.
    open_panel_menu(page, PIVOT_GRID, "Metric_b")
    option(page, MENU_ITEM).hover()
    assert ticked(page) == ["Positive"]
    close_menu(page)


def test_a_caller_supplied_main_menu_is_kept(page: Page):
    open_header_menu(page, CALLER_GRID, "metric_a")
    assert has_option(page, "Caller item")
    assert has_option(page, MENU_ITEM)
    close_menu(page)
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest test/test_grid_color_scale_picker.py -v`
Expected: every new test that calls `pick(page, MENU_ITEM, …)` or asserts `has_option(page, MENU_ITEM)` FAILS (timeout waiting for the "Colour scale" option). `test_ineligible_columns_offer_no_item` and `test_a_grid_without_the_opt_in_offers_no_item` PASS already — they must still pass after Step 3, which is what makes them meaningful.

- [ ] **Step 3: Implement `colorScales/menu.ts`**

```ts
import type {
  Column,
  GetColumnMenuItemsParams,
  GetContextMenuItemsParams,
  GridApi,
  GridOptions,
  MenuItemDef,
} from "ag-grid-community"
import {
  ColorScaleRuntime,
  ST_COLOR_SCALE,
  clearStats,
  isInteractive,
  lowerLayers,
  readColorScaleConfig,
  sourceColumnOf,
  stColorScaleCellStyle,
} from "./index"
import { Choice, applyChoice } from "./overrides"

type Items = (string | MenuItemDef)[]

const SCHEME_ITEMS: readonly [string, string][] = [
  ["neutral", "Neutral"],
  ["positive", "Positive"],
  ["diverging", "Diverging"],
  ["rank", "Rank"],
]
const MODE_ITEMS: readonly [string, string][] = [
  ["minmax", "Min–max"],
  ["zscore", "Z-score"],
]

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value)
}

/**
 * Whether the picker is offered on `source` — a real column, never a pivot
 * result column (callers pass `sourceColumnOf`'s result).
 *
 * The first check is the load-bearing one: the slot is ours only where
 * `registerColorScales` attached the built-in, so this single identity test
 * covers a caller's `cellStyle` from any of its three sources, the auto-group
 * column (never walked by `eachColDef`), and a column `registerColorScales`
 * skipped. The live `isInteractive` check is what takes the item away when a
 * config update switches the opt-in off on a grid whose hooks — `@initial` in
 * AG-Grid — can no longer be removed.
 */
export function isEligible(source: Column, gridContext: unknown): boolean {
  if (!isInteractive(gridContext)) return false
  const def = source.getColDef()
  if (def.cellStyle !== stColorScaleCellStyle) return false

  const own = (def.context as Record<string, unknown> | undefined)?.[ST_COLOR_SCALE]
  // The page author's explicit "not this column".
  if (own === false) return false
  // A fill marks a structural column, not a measurement.
  if (readColorScaleConfig(def, gridContext)?.kind === "fill") return false

  // A measure: declared, aggregated, or numeric. `cellDataType` is the
  // inferred one — AG-Grid writes it into the colDef (measured 2026-09-20).
  if (own !== undefined && own !== null) return true
  if (def.aggFunc != null || source.getAggFunc() != null) return true
  if (def.cellDataType === "number") return true
  const types = def.type == null ? [] : Array.isArray(def.type) ? def.type : [def.type]
  return types.includes("numericColumn")
}

/** The `Colour scale ▸` item for one column, or `null` when not offered. */
function colorScaleItem(
  api: GridApi,
  column: Column,
  runtime: ColorScaleRuntime
): MenuItemDef | null {
  const context = api.getGridOption("context")
  const source = sourceColumnOf(column.getColDef(), column)
  if (!source || !isEligible(source, context)) return null

  const colId = source.getColId()
  const def = source.getColDef()
  const own = (def.context as Record<string, unknown> | undefined)?.[ST_COLOR_SCALE]
  const hasOwn = own !== undefined && own !== null

  // Read fresh on every open — AG-Grid calls the hook each time — so a tick
  // can never be stale.
  const override = runtime.overrides.get(colId)
  const resolved = readColorScaleConfig(def, context, override)
  const lower = lowerLayers(def, context)
  const anchorAvailable =
    isFiniteNumber(lower.anchor) && isFiniteNumber(lower.span) && lower.span > 0

  const scheme =
    resolved === null || resolved.kind === "fill"
      ? null
      : resolved.kind === "rank"
        ? "rank"
        : resolved.scheme.name
  const mode =
    resolved?.kind === "ramp" ? resolved.mode : resolved?.kind === "anchor" ? "anchor" : null
  const reverse = resolved !== null && resolved.kind !== "fill" && resolved.reverse
  const isRamp = resolved?.kind === "ramp" || resolved?.kind === "anchor"

  const apply = (choice: Choice) => {
    applyChoice(runtime.overrides, colId, choice, hasOwn)
    // A different scheme can change the skip rule, hence the population.
    clearStats(api)
    const displayed = [...(api.getColumns() ?? []), ...(api.getPivotResultColumns() ?? [])]
    const columns = displayed
      .filter((c) => sourceColumnOf(c.getColDef(), c) === source)
      .map((c) => c.getColId())
    api.refreshCells({ force: true, columns })
    runtime.onChange(colId)
  }

  const modeItems: MenuItemDef[] = MODE_ITEMS.map(([value, name]) => ({
    name,
    checked: mode === value,
    action: () => apply({ kind: "mode", mode: value }),
  }))
  if (anchorAvailable) {
    modeItems.push({
      name: "Anchor",
      checked: mode === "anchor",
      action: () => apply({ kind: "mode", mode: "anchor" }),
    })
  }

  const subMenu: Items = [
    { name: "None", checked: resolved === null, action: () => apply({ kind: "none" }) },
    ...SCHEME_ITEMS.map(
      ([value, name]): MenuItemDef => ({
        name,
        checked: scheme === value,
        action: () => apply({ kind: "scheme", scheme: value }),
      })
    ),
    "separator",
    { name: "Mode", disabled: !isRamp, subMenu: modeItems },
    {
      name: "Reverse",
      disabled: resolved === null,
      checked: reverse,
      action: () => apply({ kind: "reverse", reverse: !reverse }),
    },
  ]
  if (override !== undefined) {
    subMenu.push("separator", {
      name: "Reset to default",
      action: () => apply({ kind: "reset" }),
    })
  }

  return { name: "Colour scale", subMenu }
}

function withColorScale(
  items: Items | null | undefined,
  api: GridApi,
  column: Column | null | undefined,
  runtime: ColorScaleRuntime
): Items {
  const base = items ?? []
  if (!column) return base
  const item = colorScaleItem(api, column, runtime)
  return item ? [...base, "separator", item] : base
}

/**
 * Install the picker on the grid's menus. Call only for a grid that is
 * interactive **at creation**: both hooks are `@initial` grid options, so they
 * cannot be added or removed later, and a grid that never opts in must not get
 * a wrapper around its menus at all.
 *
 * `getColumnMenuItems` (AG-Grid 36.1) serves the column menu, the Columns tool
 * panel and the Column Chooser. It takes precedence over `getMainMenuItems`
 * for the column menu, so a caller's `getMainMenuItems` is delegated to here
 * or it would be shadowed. Whatever the caller supplied is kept and the item
 * appended — a built-in is a default, not a reservation. A colDef-level
 * `mainMenuItems`/`contextMenuItems` overrides these grid-level hooks for its
 * column and is left alone.
 */
export function registerColorScaleMenu(
  gridOptions: GridOptions,
  runtime: ColorScaleRuntime
): GridOptions {
  const callerColumn = gridOptions.getColumnMenuItems
  const callerMain = gridOptions.getMainMenuItems
  const callerContext = gridOptions.getContextMenuItems

  gridOptions.getColumnMenuItems = (params: GetColumnMenuItemsParams) => {
    let items: Items
    if (typeof callerColumn === "function") {
      items = callerColumn(params) as Items
    } else if (params.source === "columnMenu" && typeof callerMain === "function") {
      items = callerMain(params as any) as Items
    } else {
      items = params.defaultItems as Items
    }
    return withColorScale(items, params.api, params.column, runtime) as any
  }

  gridOptions.getContextMenuItems = (params: GetContextMenuItemsParams) => {
    const result: unknown =
      typeof callerContext === "function" ? callerContext(params) : params.defaultItems
    // A caller's hook may be async (`gridOptions.d.ts:2728`).
    if (result && typeof (result as Promise<Items>).then === "function") {
      return (result as Promise<Items>).then(
        (items) => withColorScale(items, params.api, params.column, runtime) as any
      )
    }
    return withColorScale(result as Items, params.api, params.column, runtime) as any
  }

  return gridOptions
}
```

If `tsc` rejects a cast, widen that one expression to `as any` with a comment naming the AG-Grid type that did not line up — do not change runtime behaviour to satisfy the compiler.

- [ ] **Step 4: Install it from `utils/parsers.ts`**

Add `import { registerColorScaleMenu } from "../colorScales/menu"` and extend the block added in Task 5:

```ts
  if (colorScaleRuntime && isInteractive(gridOptions.context)) {
    gridOptions.context[ST_COLOR_SCALE_OVERRIDES] = colorScaleRuntime.overrides
    // The menus are enterprise modules. Without them the opt-in still fills
    // the slots and still honours a saved state; it just offers no picker.
    if (data.enable_enterprise_modules) {
      registerColorScaleMenu(gridOptions, colorScaleRuntime)
    } else if (data.debug === true) {
      console.log(
        "[st_aggrid] colour-scale picker: no menu on a community grid " +
          "(needs enable_enterprise_modules)."
      )
    }
  }
```

- [ ] **Step 5: Build and run**

Run: `cd st_aggrid/frontend && COREPACK_ENABLE_DOWNLOAD_PROMPT=0 corepack yarn build && cd ../.. && uv run pytest test/test_grid_color_scale_picker.py -v`
Expected: all PASS.

If `test_the_columns_panel_offers_the_same_menu` cannot find the row, print `grid_locator(page, PIVOT_GRID).locator(".ag-column-select-column").all_inner_texts()` — the label is AG-Grid's auto-generated header name for the field (`Metric_b`), confirmed by the 2026-09-20 spike. If a sub menu is clipped by a grid's bottom edge so that an option cannot be clicked, **do not** set `popupParent` — raise the affected grid's `height` in the app instead and record the clipping under "Risks" in the spec; `popupParent` is a separate, grid-wide decision.

- [ ] **Step 6: Run the neighbouring suites that share the touched code**

Run: `uv run pytest test/test_grid_color_scale.py test/test_grid_cohort_pivot.py test/test_grid_state_visibility_pivot.py -q`
Expected: all PASS.

- [ ] **Step 7: Commit (without the build)**

```bash
git add st_aggrid/frontend/src test/test_grid_color_scale_picker.py
git commit -m "Offer the colour-scale picker from the column, cell and Columns-panel menus"
```

---

### Task 7: State out — the fork-owned collector and the synthetic event

**Files:**
- Modify: `st_aggrid/frontend/src/hooks/useAutoCollect.ts`
- Modify: `st_aggrid/frontend/src/AgGridComponent.tsx` (next to `lifecycleWanted`, `:470`)
- Test: `test/test_grid_color_scale_picker.py`

**Interfaces:**
- Consumes: `colorScaleRuntimeRef`, `colorScaleChangeRef` (Task 5); `serializeState` (Task 4); `runtime.onChange` being called after every menu action (Task 6); `AgGridResult.color_scale_state` (Task 3).
- Produces:
  - `export const SYNTHETIC_EVENTS: ReadonlySet<string>` = `new Set(["stColorScaleChanged"])`
  - `export type ExtraCollectors = Record<string, { key: string; read: () => unknown }>`
  - `useAutoCollect({ …, extraCollectors?: ExtraCollectors })`
  - Collect method `stGetColorScaleState` → result key `colorScaleState`.

- [ ] **Step 1: Write the failing tests**

Append to `test/test_grid_color_scale_picker.py`:

```python
import json  # merge into the imports at the top

# ---------------------------------------------------------------------------
# State out, and back in
# ---------------------------------------------------------------------------


def saved_state(page: Page) -> dict | None:
    return json.loads(marker(page, "state"))


def test_a_choice_is_reported_and_survives_a_remount(page: Page):
    open_header_menu(page, STATE_GRID, "metric_a")
    pick(page, MENU_ITEM, "Positive")

    def reported():
        assert saved_state(page) == {
            "metric_a": {"scheme": "positive"},
            "metric_b": {"scheme": "diverging"},
        }

    eventually(reported)
    # The rerun that reported it must not have disturbed the picture.
    assert_column(page, STATE_GRID, "metric_a", "positive", flat_values("metric_a"))

    page.get_by_role("button", name="remount").click()
    # A fresh grid instance, fed only from what Python saved.
    assert_column(page, STATE_GRID, "metric_a", "positive", flat_values("metric_a"))
    assert_column(page, STATE_GRID, "metric_b", "diverging", flat_values("metric_b"))


def test_none_on_a_declared_column_is_reported_as_false(page: Page):
    open_header_menu(page, STATE_GRID, "metric_a")
    pick(page, MENU_ITEM, "None")

    def reported():
        assert saved_state(page) == {"metric_a": False, "metric_b": {"scheme": "diverging"}}

    eventually(reported)


def test_a_choice_survives_a_config_update(page: Page):
    open_header_menu(page, STATE_GRID, "metric_a")
    pick(page, MENU_ITEM, "Positive")
    assert_column(page, STATE_GRID, "metric_a", "positive", flat_values("metric_a"))

    runs = int(marker(page, "runs"))
    page.get_by_text("flip option").click()
    eventually(lambda: _assert_greater(int(marker(page, "runs")), runs))
    # `updateGridOptions` installed fresh colDefs and a fresh `context`; the
    # same map rode along.
    assert_column(page, STATE_GRID, "metric_a", "positive", flat_values("metric_a"))
    assert_column(page, STATE_GRID, "metric_b", "diverging", flat_values("metric_b"))


def _assert_greater(actual: int, floor: int) -> None:
    assert actual > floor
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest test/test_grid_color_scale_picker.py -v -k "reported or remount or config_update"`
Expected: the first two FAIL — `state=null` never changes, because nothing collects. `test_a_choice_survives_a_config_update` may already PASS (the map injection from Task 5 is what it guards); keep it regardless.

- [ ] **Step 3: Implement `useAutoCollect.ts`**

Below `LIFECYCLE_EVENTS` add:

```ts
/**
 * Events the component raises itself. AG-Grid never emits them, so a listener
 * attached below would simply never fire; the owner of each event calls the
 * collector directly instead (`collectNow`). Mirrors
 * `SYNTHETIC_UPDATE_ON_EVENTS` in `st_aggrid/aggrid.py`.
 */
export const SYNTHETIC_EVENTS: ReadonlySet<string> = new Set(["stColorScaleChanged"])

/**
 * Collect methods the fork owns, looked up by name before the `GridApi`. They
 * keep `collect=[...]` one flat list of names without patching AG-Grid's api
 * object, whose extensibility is not a documented guarantee. `key` is explicit
 * because `toKey` only strips a leading `get`.
 */
export type ExtraCollectors = Record<string, { key: string; read: () => unknown }>
```

Add `extraCollectors?: ExtraCollectors` to `UseAutoCollectOptions` and to the destructured parameters. In the collect loop, make the body of the `try`:

```ts
          const extra = extraCollectors?.[method]
          if (extra) {
            result[extra.key] = extra.read()
            continue
          }
          const fn = (target as any)[method]
          // … existing branches unchanged
```

Add `extraCollectors` to `collectNow`'s dependency array.

In the listener loop, directly after the `LIFECYCLE_EVENTS` branch:

```ts
      if (SYNTHETIC_EVENTS.has(name)) {
        if (debug) {
          console.log(`[useAutoCollect] Synthetic trigger, no listener: ${name}`)
        }
        continue
      }
```

- [ ] **Step 4: Wire it in `AgGridComponent.tsx`**

Imports: `import { serializeState, sanitizeState } from "./colorScales/overrides"` (extend Task 5's import) and `import { LIFECYCLE_EVENTS, ExtraCollectors, useAutoCollect } from "./hooks/useAutoCollect"`.

Above the `useAutoCollect` call:

```tsx
  // `stGetColorScaleState` in `collect` reads the live map. Stable for the
  // mount: the runtime object never changes identity.
  const extraCollectors = useMemo<ExtraCollectors>(
    () => ({
      stGetColorScaleState: {
        key: "colorScaleState",
        read: () => serializeState(colorScaleRuntimeRef.current!.overrides),
      },
    }),
    []
  )
```

Pass `extraCollectors` in the `useAutoCollect({ … })` options.

Below `lifecycleWanted`:

```tsx
  // A menu action reports here. `stColorScaleChanged` is the component's own
  // event, so nothing subscribes to it: when `update_on` names it, the
  // collector is called directly — the same route `gridReady` takes. The
  // `source` must not start with "api", which the collector drops as
  // programmatic. Assigned during render, like `notesEditableRef`, so the
  // menu closure built at grid creation always reaches the current collector.
  const colorScaleEventWanted = useMemo(
    () =>
      updateOn.some(
        (entry) => (Array.isArray(entry) ? entry[0] : entry) === "stColorScaleChanged"
      ),
    [updateOn]
  )
  colorScaleChangeRef.current = (colId: string) => {
    if (!colorScaleEventWanted) return
    collectNow("stColorScaleChanged", { colId, source: "uiColorScaleMenu" })
  }
```

- [ ] **Step 5: Build and run the picker suite**

Run: `cd st_aggrid/frontend && COREPACK_ENABLE_DOWNLOAD_PROMPT=0 corepack yarn build && cd ../.. && uv run pytest test/test_grid_color_scale_picker.py -v`
Expected: all PASS, including `test_header_menu_paints_an_undeclared_column_without_a_rerun` — grid 0 does not name the event, so its `runs=` still must not move.

- [ ] **Step 6: Run the collector's own suites**

Run: `uv run pytest test/test_grid_lifecycle_collect.py test/test_grid_return.py test/test_grid_saved_view.py -q`
Expected: all PASS.

- [ ] **Step 7: Commit (without the build)**

```bash
git add st_aggrid/frontend/src test/test_grid_color_scale_picker.py
git commit -m "Report the reader's colour-scale choice through auto-collect"
```

---

### Task 8: Documentation, version, build, full run

**Files:**
- Modify: `README.md` (Auto-Collect `:46`, colour scales `:454`, `AgGrid()` and `AgGridResult` reference `:651`, `:673`)
- Modify: `CLAUDE.md`
- Modify: `pyproject.toml:3`, `st_aggrid/pyproject.toml:13`
- Modify: `st_aggrid/frontend/build/*` (rebuilt)

**Interfaces:**
- Consumes: everything above.
- Produces: release-ready branch at 2.5.0.

- [ ] **Step 1: README — the picker**

At the end of "Declarative colour scales without JavaScript" (before "Export and clipboard") add a subsection:

````markdown
#### Letting the reader choose a colour scale

```python
gb.configure_color_scale(scheme="neutral", interactive=True)

result = AgGrid(
    df,
    grid_options=gb.build(),
    enable_enterprise_modules=True,
    collect=["getColumnState", "stGetColorScaleState"],
    update_on=["columnMoved", "stColorScaleChanged"],
    color_scale_state=st.session_state.get("colors"),
    key="grid",
)
if result.color_scale_state is not None:
    st.session_state["colors"] = result.color_scale_state
```

`interactive=True` adds **Colour scale ▸** to the column menu (⋮), the cell
right-click menu and the Columns tool panel's right-click menu: None, Neutral,
Positive, Diverging, Rank, a Mode sub menu (Min–max, Z-score, and Anchor where
the column already declares `anchor` and `span`), Reverse, and Reset to
default. The grid repaints at once, without a rerun.

* **Which columns.** Numeric or aggregated columns, and any column with a
  declaration, provided the built-in owns the `cellStyle` slot. Not offered on a
  column with its own `cellStyle`, on a `fill` column, or on a column the page
  switched off with `color_scale=False` — that is the opt-out. In pivot mode a
  choice made on any result column applies to every result column of that
  metric.
* **The choice is a layer**, over the column's declaration, which is over the
  grid-level defaults. Only what the reader touched is stored, so changing a
  default in code still reaches every column they left alone.
* **Getting it out.** Add `"stGetColorScaleState"` to `collect` and read
  `result.color_scale_state` (`{col_id: False | {"scheme", "mode",
  "reverse"}}`). Add `"stColorScaleChanged"` to `update_on` to rerun when the
  reader picks something; it cannot be debounced.
* **Putting it back.** `color_scale_state=` is read **once, when the grid
  mounts** — change `key` to apply a different one. A malformed value raises;
  a stale one (a column that is gone, a choice that no longer resolves) is
  ignored and never blanks a declared column.
* **Set `interactive` when the grid is created.** AG-Grid reads the column-menu
  hook at creation only. Switching `interactive` off later removes the item
  everywhere at once; switching it on for a grid created without it adds the
  item to the cell menu at once, but the column menu and the Columns panel need
  a remount (a changed `key`).
* The menus are enterprise modules. On a community grid the saved state is
  still honoured; there is just no picker.
* A caller-supplied `getColumnMenuItems`, `getMainMenuItems` or
  `getContextMenuItems` is kept and the item appended. A colDef-level
  `mainMenuItems`/`contextMenuItems` replaces the menu for its column, picker
  included.
````

In "Auto-Collect", after the paragraph on lifecycle triggers, add:

```markdown
Two names in these lists belong to the component rather than to AG-Grid:
`"stGetColorScaleState"` in `collect` (returned as `result.color_scale_state`)
and `"stColorScaleChanged"` in `update_on`. See "Letting the reader choose a
colour scale".
```

Add `color_scale_state` to the `AgGrid()` parameter table and `color_scale_state` to the `AgGridResult` table, in the wording of their docstrings. Update the version references the README carries for the package (search `2.4.3`).

- [ ] **Step 1b: Correct the `@initial` claim in `colorScales/menu.ts`**

`registerColorScaleMenu`'s doc comment says both hooks are `@initial`. Only `getColumnMenuItems` is (`gridOptions.d.ts:1932-1939`); `getContextMenuItems` (`:1921-1925`) is re-applied by `updateGridOptions`. Replace the comment's first paragraph with:

```ts
 * Install the picker on the grid's menus. Called only for parsed options that
 * are interactive, so a grid that never opts in gets no wrapper around its
 * menus at all. `getColumnMenuItems` is an `@initial` grid option — AG-Grid
 * reads it at creation only — while `getContextMenuItems` is re-applied by
 * `updateGridOptions`. Hence the asymmetry when `interactive` is switched on
 * for a live grid: the cell menu gains the item at once, the column menu and
 * the Columns panel only after a remount. Switching it off needs neither:
 * every open re-checks the live flag (`isEligible`).
```

Apply the same correction to `isEligible`'s doc comment where it calls the hooks `@initial`: say "whose column-menu hook — `@initial` in AG-Grid — can no longer be removed". No runtime change.

- [ ] **Step 2: CLAUDE.md**

In the architecture tree add, in order, under `colorScales/`:

```
    │   ├── colorScales/overrides.ts   # the reader's layer: sanitise, apply a choice, candidate order (pure)
    │   ├── colorScales/menu.ts        # eligibility, the Colour scale ▸ item, the two menu-hook wrappers
```

and change the `colorScales/index.ts` line to `# declaration resolution (three layers), cellStyle, registration`.

Append to the "Five built-in colour schemes" bullet under Key Design Decisions:

```
  With `interactive: true` at grid level the reader picks scheme, mode and
  direction per column from the column menu, the cell menu and the Columns
  panel. The choice is a third layer — a `Map` keyed by the *source* colId,
  held by `AgGridComponent` and injected into the grid `context` on every
  parse — never a `colDef.context` mutation: `updateGridOptions` replaces
  colDefs, and a pivot result column's `context` is a copy. It leaves through
  the fork-owned collect method `stGetColorScaleState` and the synthetic
  `update_on` event `stColorScaleChanged` (no listener — the menu calls
  `collectNow`), and returns through the mount-only `color_scale_state` prop.
  `getColumnMenuItems` is `@initial` (`getContextMenuItems` is not), so a grid
  switched to interactive after creation gets the cell-menu item at once and
  the column-menu/Columns-panel item only after a remount.
```

In "Conventions", extend the pure-module sentence: "The three pure colour-scale modules (`normalize.ts`, `schemes.ts`, `overrides.ts`) import nothing …".

- [ ] **Step 3: Version**

Set `version = "2.5.0"` in `pyproject.toml` and `st_aggrid/pyproject.toml`.

Run: `uv run pytest test/unit/test_component_manifest.py -q`
Expected: PASS (it checks the two agree).

- [ ] **Step 4: Final build**

Run: `cd st_aggrid/frontend && COREPACK_ENABLE_DOWNLOAD_PROMPT=0 corepack yarn build && ls build && cd ../..`
Expected: exactly one `index-*.js` and one `index-*.css`.

- [ ] **Step 5: Every check, every suite**

Run:
```bash
for f in normalize schemes overrides; do node st_aggrid/frontend/src/colorScales/__checks__/$f.check.ts || exit 1; done
uv run pytest
uv run pytest -m slow
```
Expected: all PASS. Read the summary line and quote it in the commit body; do not claim green without it.

- [ ] **Step 6: Commit docs, version and the build**

```bash
git add -A st_aggrid/frontend/build README.md CLAUDE.md pyproject.toml st_aggrid/pyproject.toml
git commit -m "Document the colour-scale picker and bump to 2.5.0"
```

- [ ] **Step 7: Stop**

Do not tag, push or open a PR. Report the branch state and the test summary to the owner; release tagging has its own gated procedure (`scripts/release.sh`) and happens on `main` after merge.

---

## Spec coverage

| Spec section | Task |
|---|---|
| Part A — Change, Done when | 1 |
| Opt-in (`interactive`, grid-level only, community behaviour) | 2, 3, 5, 6 |
| Toggling `interactive` on a live grid | 6 (`isEligible` live check, install-at-creation), 8 (README) |
| The override layer (keying, activation, author's `false`, fallback) | 4, 5 |
| State out (`stGetColorScaleState`, `stColorScaleChanged`, no debounce) | 3, 7 |
| State in (mount-only, unknown colIds kept, shape-only validation) | 2, 3, 5 |
| `UNPAINTED` on interactive grids | 5, 6 (`test_none_clears…`) |
| Slot filling, once-per-grid warning | 5 |
| Menu: hooks, wrapping, eligibility, shape, action | 6 |
| Reserved context key | 2 |
| Tests: node checks / unit / e2e list | 4 / 2-3 / 5-7 |
| Version, README, CLAUDE.md | 8 |
| Consumer contract | out of scope here — own spec in `hitapps_analytics` |
