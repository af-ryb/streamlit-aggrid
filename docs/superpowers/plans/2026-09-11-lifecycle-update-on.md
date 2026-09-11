# Lifecycle `update_on` Triggers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `update_on=["gridReady"]` and `update_on=["firstDataRendered"]` produce exactly one auto-collect per grid creation, with no user interaction and with a post-restore snapshot.

**Architecture:** Both names stop being event subscriptions and become lifecycle callbacks bound when the grid is created. `useAutoCollect` returns its collector so `AgGridComponent` can drive one collect from `onGridReady` and from a new `onFirstDataRendered` prop, and its listener loop skips the two names so nothing fires twice. Python validation changes subject from "reject these names" to "reject a debounce on these names".

**Tech Stack:** React 18 + TypeScript (Vite lib build), AG-Grid 36.0.0 Community/Enterprise, Streamlit Custom Components v2, pytest + Playwright.

**Spec:** `docs/superpowers/specs/2026-09-11-lifecycle-update-on-design.md`

## Global Constraints

- Release version is **2.4.2**, in both `pyproject.toml` and `st_aggrid/pyproject.toml`, which must stay in sync.
- **Additive.** A grid whose `update_on` names neither event must run the same code path it runs today.
- Yarn is **not** on PATH. Every frontend command is `corepack yarn …` run from `st_aggrid/frontend`.
- `st_aggrid/frontend/build/` is committed. A rebuild changes the content hash, so `git status` shows a delete plus an add, never a modify. Stage both.
- E2E tests address rows by `row-index`, never by DOM order (`test/grid_dom.py` docstring says why).
- Tasks 1 and 2-3 must land in the same branch: between Task 1 and Task 3 the package accepts a name the frontend does not yet serve. Do not merge or release mid-plan.
- Commit messages are imperative mood and describe what changed.

## File Structure

| File | Responsibility | Task |
|---|---|---|
| `st_aggrid/aggrid.py` | `LIFECYCLE_UPDATE_ON_EVENTS` + `validate_update_on` change subject; `update_on` docstring follows | 1 |
| `test/unit/test_update_on_validation.py` | Rewritten against the new subject | 1 |
| `st_aggrid/frontend/src/hooks/useAutoCollect.ts` | Exports `LIFECYCLE_EVENTS` and `CollectNow`, returns the collector, skips lifecycle names in the listener loop | 2 |
| `st_aggrid/frontend/src/AgGridComponent.tsx` | Captures the collector, derives which lifecycle triggers were asked for, drives the collect from `onGridReady` and a new `onFirstDataRendered` | 3 |
| `st_aggrid/frontend/build/index-*.js` / `.css` | Rebuilt bundle, committed | 3 |
| `test/grid_lifecycle_collect.py` | New e2e app, one grid per radio case | 4 |
| `test/test_grid_lifecycle_collect.py` | New e2e suite, counts collector invocations from the console | 4 |
| `README.md` | Trigger contract table replaces the rejection paragraph | 5 |
| `test/grid_return.py`, `test/grid_agg_export.py` | Stale comments about why `gridReady` cannot work | 5 |
| `pyproject.toml`, `st_aggrid/pyproject.toml` | 2.4.1 → 2.4.2 | 5 |

---

### Task 1: Python validation changes subject

**Files:**
- Modify: `st_aggrid/aggrid.py:27-73` (the constant and `validate_update_on`)
- Modify: `st_aggrid/aggrid.py:212-213` (the `update_on` docstring)
- Test: `test/unit/test_update_on_validation.py` (full rewrite)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `LIFECYCLE_UPDATE_ON_EVENTS: frozenset` and `validate_update_on(update_on: Optional[List]) -> None` in `st_aggrid.aggrid`. Task 2 mirrors the same two names in TypeScript as `LIFECYCLE_EVENTS`.

- [ ] **Step 1: Write the failing tests**

Replace the entire contents of `test/unit/test_update_on_validation.py`:

```python
"""Unit tests for the ``update_on`` guard on lifecycle events.

Pure-Python (no browser, no Streamlit) — fast to run via
``pytest test/unit/test_update_on_validation.py``.

``gridReady`` and ``firstDataRendered`` are served as grid-creation callbacks
rather than as subscriptions, so they work as zero-interaction triggers but
cannot be debounced: see :func:`st_aggrid.aggrid.validate_update_on` for why,
and the README's Auto-Collect section for the user-facing version.
"""

import pytest

from st_aggrid.aggrid import LIFECYCLE_UPDATE_ON_EVENTS, validate_update_on


def test_ordinary_events_pass():
    validate_update_on(["selectionChanged", "filterChanged", "sortChanged"])


def test_debounced_tuple_form_passes_for_ordinary_events():
    validate_update_on([("columnResized", 400), "columnPinned"])


def test_none_passes():
    """`AgGrid` validates before applying its default, and the default is
    itself a valid list — so `None` must simply be allowed through."""
    validate_update_on(None)


def test_empty_passes():
    validate_update_on([])


@pytest.mark.parametrize("event", sorted(LIFECYCLE_UPDATE_ON_EVENTS))
def test_lifecycle_event_passes_as_a_bare_name(event):
    """The feature itself: both names are zero-interaction triggers now, not
    rejected entries."""
    validate_update_on(["sortChanged", event])


@pytest.mark.parametrize("event", sorted(LIFECYCLE_UPDATE_ON_EVENTS))
def test_lifecycle_event_is_rejected_in_tuple_form(event):
    """A debounce coalesces a burst of firings; an event emitted at most once
    per grid creation has no burst, so the request cannot be honoured."""
    with pytest.raises(ValueError) as excinfo:
        validate_update_on([(event, 400)])
    assert event in str(excinfo.value)


def test_list_form_of_the_debounced_entry_is_rejected_too():
    """A JSON round-trip turns the tuple into a list; the guard must not care
    which of the two it is looking at."""
    with pytest.raises(ValueError):
        validate_update_on([["gridReady", 400]])


def test_message_names_every_offender_and_points_somewhere():
    """One raise listing all offenders, not one per name — a caller who
    debounced both should not have to fix them one round-trip at a time."""
    debounced = [(event, 400) for event in sorted(LIFECYCLE_UPDATE_ON_EVENTS)]
    with pytest.raises(ValueError) as excinfo:
        validate_update_on(debounced)
    message = str(excinfo.value)
    for event in LIFECYCLE_UPDATE_ON_EVENTS:
        assert event in message
    # The point of failing loudly is telling the caller what to do instead.
    assert "bare event name" in message


def test_unknown_names_are_not_rejected():
    """Deliberately narrow. AG-Grid's event set changes with every release and
    this package has no truthful copy of it, so a name that is merely
    misspelled still fails silently — a known, separate gap."""
    validate_update_on(["thisIsNotAnAgGridEvent", ("alsoNotAnEvent", 200)])
```

- [ ] **Step 2: Run the tests and verify they fail**

Run: `uv run pytest test/unit/test_update_on_validation.py -q`
Expected: collection error, `ImportError: cannot import name 'LIFECYCLE_UPDATE_ON_EVENTS'`.

- [ ] **Step 3: Rewrite the constant and the validator**

In `st_aggrid/aggrid.py`, replace the comment block, the constant and the whole
of `validate_update_on` (lines 27 through 73 at `10205d1`) with:

```python
#: AG-Grid events this component serves as lifecycle callbacks bound at grid
#: creation rather than as subscriptions. Each is emitted at most once per grid
#: instance, and ``gridReady`` is itself the event that makes subscription
#: possible, so ``AgGridComponent`` calls the collector directly for both. They
#: work as zero-interaction ``update_on`` triggers; what they cannot take is a
#: debounce, which is all this module now rejects.
#:
#: Mirrors ``LIFECYCLE_EVENTS`` in
#: ``st_aggrid/frontend/src/hooks/useAutoCollect.ts``. The two must agree: the
#: hook skips exactly these names when attaching listeners, so a name here that
#: is missing there would be collected twice.
LIFECYCLE_UPDATE_ON_EVENTS: frozenset = frozenset(
    {"gridReady", "firstDataRendered"}
)


def validate_update_on(update_on: Optional[List]) -> None:
    """Reject a debounce on an event that fires at most once.

    A debounce coalesces a burst of firings. ``gridReady`` and
    ``firstDataRendered`` are emitted once per grid creation, so
    ``(name, debounce_ms)`` on either is a request the component cannot honour
    — and dropping it silently is the failure class this guard exists to
    prevent. Every offender is reported in one raise, so a caller who debounced
    both fixes them in one pass.

    Args:
        update_on: The list as the caller passed it; ``None`` (meaning "use the
            default") is valid.

    Raises:
        ValueError: if any entry debounces an event in
            :data:`LIFECYCLE_UPDATE_ON_EVENTS`.
    """
    if not update_on:
        return

    offenders = [
        entry[0]
        for entry in update_on
        if isinstance(entry, (tuple, list))
        and entry
        and entry[0] in LIFECYCLE_UPDATE_ON_EVENTS
    ]
    if not offenders:
        return

    raise ValueError(
        f"update_on={offenders!r} cannot be debounced: these AG-Grid events are "
        "emitted at most once per grid creation, so there is no burst of "
        "firings for a debounce to coalesce. Pass the bare event name instead "
        f"(e.g. {offenders[0]!r}), which collects exactly once as soon as the "
        "grid is ready."
    )
```

- [ ] **Step 4: Update the `update_on` docstring**

In the `AgGrid` docstring, replace these two lines (`st_aggrid/aggrid.py:212-213`):

```
        Raises ValueError for grid-creation events that can never reach the
        auto-collect listeners — see UNSUPPORTED_UPDATE_ON_EVENTS.
```

with:

```
        "gridReady" and "firstDataRendered" are zero-interaction triggers that
        collect exactly once per grid creation; they cannot be debounced, and
        the tuple form raises ValueError for them. See
        LIFECYCLE_UPDATE_ON_EVENTS and the README's Auto-Collect section.
```

- [ ] **Step 5: Run the tests and verify they pass**

Run: `uv run pytest test/unit -q`
Expected: PASS, whole unit suite green (not just the rewritten file — `test_public_exports.py` also imports from this module).

- [ ] **Step 6: Commit**

```bash
git add st_aggrid/aggrid.py test/unit/test_update_on_validation.py
git commit -m "update_on validation: reject a debounce on lifecycle events, not the names"
```

---

### Task 2: `useAutoCollect` returns its collector and skips lifecycle names

**Files:**
- Modify: `st_aggrid/frontend/src/hooks/useAutoCollect.ts`

**Interfaces:**
- Consumes: the two names agreed in Task 1 (`gridReady`, `firstDataRendered`).
- Produces, for Task 3:
  - `export const LIFECYCLE_EVENTS: ReadonlySet<string>`
  - `export type CollectNow = (eventName: string, eventData: any, api?: GridApi) => void`
  - `useAutoCollect(options: UseAutoCollectOptions): CollectNow` — same options object as today, now with a return value.

There is no JavaScript test runner in this package, so this task's gate is the
TypeScript compiler; the behavioural gate arrives in Task 3, which is when the
two files together make the feature observable.

- [ ] **Step 1: Add the exported lifecycle set and collector type**

Insert directly after the imports at the top of
`st_aggrid/frontend/src/hooks/useAutoCollect.ts`:

```ts
/**
 * Events served as lifecycle callbacks bound at grid creation, not as
 * subscriptions. AG-Grid emits each at most once per grid instance, and
 * `gridReady` is the event that makes subscription possible in the first
 * place, so a listener attached from the effect below is either dead
 * (`gridReady`) or a duplicate on top of the callback (`firstDataRendered`,
 * whose dispatch is queued into requestAnimationFrame and so loses to a React
 * effect committed in the same tick — this was measured, not assumed).
 *
 * `AgGridComponent` imports this set, and `LIFECYCLE_UPDATE_ON_EVENTS` in
 * `st_aggrid/aggrid.py` mirrors it. All three must agree.
 */
export const LIFECYCLE_EVENTS: ReadonlySet<string> = new Set([
  "gridReady",
  "firstDataRendered",
])

/**
 * Run one auto-collect under `eventName` and post the result to the host.
 *
 * `api` overrides the hook's own grid API. That is what lets a grid-creation
 * callback collect while the `gridApi` state it is about to set is still null,
 * which is exactly where the naive fix for lifecycle triggers fails.
 */
export type CollectNow = (
  eventName: string,
  eventData: any,
  api?: GridApi
) => void
```

- [ ] **Step 2: Make the collector take an explicit api, and return it**

Replace the hook's signature line and the `collectAndSend` declaration. The
function becomes:

```ts
export function useAutoCollect({
  gridApi,
  collectConfig,
  updateOn,
  setStateValue,
  debug,
}: UseAutoCollectOptions): CollectNow {
  const cleanupRef = useRef<(() => void)[]>([])
  // Live grid API, read at call time so `collectNow` stays referentially
  // stable across the null -> api transition and the effect below does not
  // re-attach every listener when the grid becomes ready. Assigned during
  // render, the same way `AgGridComponent` maintains `notesEditableRef`.
  const apiRef = useRef<GridApi | null>(null)
  apiRef.current = gridApi

  const collectNow = useCallback<CollectNow>(
    (eventName, eventData, api) => {
      const target = api ?? apiRef.current
      if (!target) return
```

The rest of the callback body is unchanged except that the `collectConfig` loop
reads `target` instead of `gridApi`, and the dependency array drops `gridApi`.
In full, from the guard to the end of the callback:

```ts
      // Skip programmatic (api-sourced) column events. Applying saved column
      // state on mount/restore (initialState + onGridReady setRowGroupColumns
      // + the columns_state re-apply effect) fires AG-Grid events with
      // source="api"/"apiNoSortChange". Echoing those back via setStateValue
      // triggers a Streamlit fragment rerun (and a restore->capture->re-apply
      // loop / column flicker). Only user actions should sync state — this
      // mirrors dash_app's is_programmatic_grid_event, moved upstream so the
      // rerun is never triggered, not merely the capture suppressed.
      //
      // Also skip sizing-driven sources: the fitGridWidth refit listener calls
      // sizeColumnsToFit() on displayedColumnsChanged, which emits a
      // columnResized with source="sizeColumnsToFit" (likewise "flex" /
      // "autosizeColumns"). Capturing those would persist the auto-fit widths
      // as if the user set them and fire a needless rerun.
      //
      // Neither GridReadyEvent nor FirstDataRenderedEvent carries a `source`,
      // so both pass this filter. That is deliberate: nothing about a
      // lifecycle trigger is programmatic in the sense meant here.
      const source = eventData?.source
      const isProgrammatic =
        typeof source === "string" &&
        (source.startsWith("api") ||
          source === "sizeColumnsToFit" ||
          source === "flex" ||
          source === "autosizeColumns")
      if (isProgrammatic) {
        if (debug) {
          console.log(`[useAutoCollect] Skipping programmatic "${eventName}" (source=${source})`)
        }
        return
      }

      const result: GridStateResult = {
        eventName,
        eventData: serializeEventData(eventData),
      }

      for (const method of collectConfig) {
        try {
          const fn = (target as any)[method]
          if (typeof fn === "function") {
            const value = fn.call(target)
            result[toKey(method)] = value
          } else if (debug) {
            console.warn(`AG-Grid API method "${method}" not found`)
          }
        } catch (err) {
          if (debug) {
            console.error(`Error calling gridApi.${method}():`, err)
          }
        }
      }

      if (debug) {
        console.log(`[useAutoCollect] Event "${eventName}":`, result)
      }

      setStateValue("grid_state", result)
    },
    [collectConfig, setStateValue, debug]
  )
```

Then add the return at the very end of the hook, after the `useEffect`:

```ts
  return collectNow
}
```

The two handler factories inside the effect call `collectNow` instead of
`collectAndSend`; Step 5 greps to prove no reference to the old name survives.

- [ ] **Step 3: Skip lifecycle names in the listener loop**

Inside `useEffect`, at the top of `for (const entry of updateOn) {`, before the
`if (Array.isArray(entry))` branch:

```ts
      const name = Array.isArray(entry) ? entry[0] : entry

      // Served by AgGridComponent as a grid-creation callback. A listener here
      // would never fire (gridReady) or would fire on top of the callback
      // (firstDataRendered) — one collect turning into two.
      if (LIFECYCLE_EVENTS.has(name)) {
        if (debug) {
          console.log(
            `[useAutoCollect] Lifecycle trigger, no listener: ${name}`
          )
        }
        continue
      }
```

and change the trailing debug log in the same loop from `${entry}` to `${name}`,
so a debounced entry logs `columnResized` rather than `columnResized,400`.

- [ ] **Step 4: Typecheck**

Run: `cd st_aggrid/frontend && COREPACK_ENABLE_DOWNLOAD_PROMPT=0 corepack yarn tsc --noEmit`
Expected: no output, exit 0. If `tsc` is not resolvable standalone, run
`COREPACK_ENABLE_DOWNLOAD_PROMPT=0 corepack yarn build` instead and expect it to
complete; discard the build output for now, Task 3 produces the bundle that gets
committed.

- [ ] **Step 5: Confirm nothing still calls the old name**

Run: `grep -rn "collectAndSend" st_aggrid/frontend/src`
Expected: no matches.

- [ ] **Step 6: Commit**

```bash
git add st_aggrid/frontend/src/hooks/useAutoCollect.ts
git commit -m "useAutoCollect: return the collector, take an explicit api, skip lifecycle names"
```

---

### Task 3: Drive the collect from the two grid-creation callbacks

**Files:**
- Modify: `st_aggrid/frontend/src/AgGridComponent.tsx` (imports at `:4-10` and `:20`; the `useAutoCollect` call at `:457`; `onGridReady` at `:800-979`; the render block at `:1021-1026`)
- Modify: `st_aggrid/frontend/build/index-*.js` and `index-*.css` (rebuilt; delete + add)

**Interfaces:**
- Consumes from Task 2: `LIFECYCLE_EVENTS`, `CollectNow`, and `useAutoCollect`'s return value.
- Produces: the observable feature. Task 4's e2e suite asserts against it.

The ordering rule for this whole task: **the caller's handler runs first, the
collect runs last.** A collect placed before the restore block returns the
pre-restore layout, and the feature then lies rather than fails — which is worse.

- [ ] **Step 1: Extend the imports**

Add `FirstDataRenderedEvent` to the `ag-grid-community` type import (`:4-10`):

```ts
import {
  AllCommunityModule,
  FirstDataRenderedEvent,
  GetRowIdParams,
  GridApi,
  GridReadyEvent,
  ModuleRegistry,
} from "ag-grid-community"
```

and pull the lifecycle set in alongside the hook (`:20`):

```ts
import { LIFECYCLE_EVENTS, useAutoCollect } from "./hooks/useAutoCollect"
```

- [ ] **Step 2: Capture the collector and derive the requested triggers**

At the `useAutoCollect` call site (`:457`), keep the options object identical and
capture the return value:

```ts
  // Auto-collect hook — needs a stable `gridApi` value that changes exactly
  // once the grid becomes ready, so `useState` (not the ref) is the source.
  // The returned collector is what the two grid-creation callbacks below use:
  // they run before that state exists, so they hand it `event.api` directly.
  const collectNow = useAutoCollect({
    gridApi,
    collectConfig,
    updateOn,
    setStateValue,
    debug,
  })

  // Which lifecycle triggers this grid asked for. Derived once from `updateOn`
  // so a grid that asked for neither pays nothing at creation.
  const lifecycleWanted = useMemo(() => {
    const names = new Set<string>()
    for (const entry of updateOn) {
      const name = Array.isArray(entry) ? entry[0] : entry
      if (LIFECYCLE_EVENTS.has(name)) names.add(name)
    }
    return names
  }, [updateOn])
```

- [ ] **Step 3: Collect at the end of `onGridReady`**

Append to `onGridReady`, immediately after the existing user-handler chain at
`:973-977` and before the closing `},`:

```ts
      // Zero-interaction trigger. Last on purpose: the restore block above
      // (row groups, the merge overlay), pre-selection and the caller's own
      // onGridReady all count as part of restore, and a snapshot taken before
      // them would report the pre-restore layout as if it were live.
      //
      // `event.api` is passed explicitly because the `gridApi` state this
      // callback set at its top has not committed yet.
      if (lifecycleWanted.has("gridReady")) {
        collectNow("gridReady", event, event.api)
      }
```

and extend the dependency array at `:979`:

```ts
    [
      data.columns_state,
      data.columns_state_mode,
      data.gridOptions,
      gridOptions,
      debug,
      lifecycleWanted,
      collectNow,
    ]
```

- [ ] **Step 4: Add the `onFirstDataRendered` callback**

Immediately after the `onGridReady` `useCallback` ends (after `:979`):

```ts
  // AG-Grid emits `firstDataRendered` at most once per grid instance, and its
  // gridOptions handlers are queued until `gridReady` has fired, so this always
  // runs after onGridReady above. It never runs at all on a grid with no rows:
  // the event is dispatched from the first rendered body row.
  //
  // The user's handler is chained by hand because a prop of the same name
  // REPLACES the gridOptions key rather than adding to it
  // (`_combineAttributesAndGridOptions` in ag-grid-community) — the same reason
  // onGridReady chains its own.
  const onFirstDataRendered = useCallback(
    (event: FirstDataRenderedEvent) => {
      const { onFirstDataRendered: userOnFirstDataRendered } = gridOptions
      if (userOnFirstDataRendered) {
        userOnFirstDataRendered(event)
      }

      if (lifecycleWanted.has("firstDataRendered")) {
        collectNow("firstDataRendered", event, event.api)
      }
    },
    [gridOptions, lifecycleWanted, collectNow]
  )
```

- [ ] **Step 5: Pass it to the grid**

In the render block (`:1021-1026`):

```tsx
      <AgGridReact
        onGridReady={onGridReady}
        onFirstDataRendered={onFirstDataRendered}
        rowData={rowData}
        gridOptions={gridOptions}
        initialState={initialState}
      />
```

- [ ] **Step 6: Build**

Run: `cd st_aggrid/frontend && COREPACK_ENABLE_DOWNLOAD_PROMPT=0 corepack yarn build`
Expected: completes; `st_aggrid/frontend/build/` holds exactly one `index-*.js`
and one `index-*.css`.

Run: `ls st_aggrid/frontend/build/`
Expected: exactly two files matching those globs. More than one of either breaks
`component.py`'s registration, which requires each glob to resolve to one file.

- [ ] **Step 7: Run the existing e2e suites in full**

This is the radius gate for the whole plan. `useAutoCollect` is the collect path
for every grid and `onGridReady` now has one more statement, so the failure to
look for is not "the new trigger did not fire" but "state collection moved
somewhere else".

Run: `uv run pytest -m "e2e and not slow" -q`
Expected: same pass/fail set as before the branch. If anything fails, compare
against `git stash`-ing the frontend source and rebuilding before assuming the
test is flaky.

- [ ] **Step 8: Commit source and rebuilt bundle together**

```bash
git add -A st_aggrid/frontend/src st_aggrid/frontend/build
git status --short   # expect: modified src, one D and one A per bundle extension
git commit -m "Collect on gridReady and firstDataRendered as grid-creation callbacks"
```

---

### Task 4: End-to-end coverage

**Files:**
- Create: `test/grid_lifecycle_collect.py`
- Create: `test/test_grid_lifecycle_collect.py`

**Interfaces:**
- Consumes: the behaviour built in Tasks 1-3.
- Produces: nothing later tasks depend on.

Both files are auto-marked `e2e` by `test/conftest.py` because they live outside
`test/unit/`.

- [ ] **Step 1: Write the Streamlit app**

Create `test/grid_lifecycle_collect.py`:

```python
"""Streamlit app: gridReady / firstDataRendered as zero-interaction triggers.

One grid at a time, chosen by a radio, so every `[useAutoCollect]` console line
on the page belongs to exactly one grid and the test can count collector
invocations directly. Case "none" renders no grid and is where every test lands
before clicking its own case — otherwise a default case's fires would already
be in the console log.

Fires are also accumulated on the Python side through `on_grid_state_change`,
which is what proves the value reached the host with the right event name and
post-restore content. The count itself is read from the console: Streamlit
invokes the callback only when the component's state value changes, so a
second, byte-identical collect would leave no trace here.

Run standalone with:  streamlit run test/grid_lifecycle_collect.py
"""

import json

import pandas as pd
import streamlit as st

from st_aggrid import AgGrid, JsCode

DF = pd.DataFrame(
    {
        "region": ["DE", "FR", "IT", "CA"],
        "channel": ["web", "web", "app", "app"],
        "metric": [10, 20, 30, 40],
    }
)
#: Same columns, no rows. AG-Grid dispatches `firstDataRendered` from the first
#: rendered body row, so this grid must never fire it.
EMPTY = DF.iloc[0:0]

COMMON = {
    "columnDefs": [
        {"colId": "region", "field": "region"},
        {"colId": "channel", "field": "channel"},
        {"colId": "metric", "field": "metric", "type": "numericColumn"},
    ],
    "animateRows": False,
}

#: Neither the row group nor the hidden column is declared in `columnDefs`, so a
#: pre-restore snapshot would look nothing like this.
RESTORE_STATE = [
    {"colId": "region", "rowGroup": True, "rowGroupIndex": 0},
    {"colId": "channel", "hide": True},
    {"colId": "metric"},
]

#: Writes to `window` rather than to the DOM: the collect triggers a Streamlit
#: rerun, and a counter rendered by the app would be reset by it.
USER_HANDLER = JsCode(
    "function(event) {"
    " window.__userFirstDataRendered = (window.__userFirstDataRendered || 0) + 1;"
    " }"
)


def recorder(key):
    """A callback that appends each collected event name to a per-grid list."""
    fires = st.session_state.setdefault("fires", {})

    def _record(result):
        fires.setdefault(key, []).append(result.event_name)

    return _record


def show_fires(key):
    fires = st.session_state.get("fires", {}).get(key, [])
    st.html(f"<pre data-testid='fires-{key}'>{','.join(fires)}</pre>")


CASE = st.radio(
    "Case",
    options=[
        "none",
        "gridReady",
        "firstDataRendered",
        "both",
        "restore",
        "empty",
        "chain",
    ],
)

if CASE == "gridReady":
    AgGrid(
        DF,
        grid_options=COMMON,
        collect=["getColumnState"],
        update_on=["gridReady"],
        debug=True,
        on_grid_state_change=recorder("lc_ready"),
        key="lc_ready",
    )
    show_fires("lc_ready")

elif CASE == "firstDataRendered":
    AgGrid(
        DF,
        grid_options=COMMON,
        collect=["getColumnState"],
        update_on=["firstDataRendered"],
        debug=True,
        on_grid_state_change=recorder("lc_first"),
        key="lc_first",
    )
    show_fires("lc_first")

elif CASE == "both":
    AgGrid(
        DF,
        grid_options=COMMON,
        collect=["getColumnState"],
        update_on=["gridReady", "firstDataRendered"],
        debug=True,
        on_grid_state_change=recorder("lc_both"),
        key="lc_both",
    )
    show_fires("lc_both")

elif CASE == "restore":
    result = AgGrid(
        DF,
        grid_options=COMMON,
        collect=["getColumnState"],
        update_on=["gridReady"],
        columns_state=RESTORE_STATE,
        enable_enterprise_modules=True,
        debug=True,
        on_grid_state_change=recorder("lc_restore"),
        key="lc_restore",
    )
    show_fires("lc_restore")
    st.html(
        "<pre data-testid='state-lc_restore'>"
        f"{json.dumps(result.column_state or [])}</pre>"
    )

elif CASE == "empty":
    AgGrid(
        EMPTY,
        grid_options=COMMON,
        collect=["getColumnState"],
        update_on=["firstDataRendered"],
        debug=True,
        on_grid_state_change=recorder("lc_empty"),
        key="lc_empty",
    )
    show_fires("lc_empty")

elif CASE == "chain":
    AgGrid(
        DF,
        grid_options={**COMMON, "onFirstDataRendered": USER_HANDLER},
        collect=["getColumnState"],
        update_on=["firstDataRendered"],
        allow_unsafe_jscode=True,
        debug=True,
        on_grid_state_change=recorder("lc_chain"),
        key="lc_chain",
    )
    show_fires("lc_chain")
```

- [ ] **Step 2: Run the app by hand and confirm each case renders**

Run: `uv run streamlit run test/grid_lifecycle_collect.py`

Click through all seven cases in a browser. Confirm, before writing any
assertion against them:

- `gridReady`, `firstDataRendered`, `both`, `chain` show four data rows;
- `restore` shows grouped rows with `channel` gone;
- `empty` shows a grid with headers and no rows.

If `empty` fails to render at all, an empty DataFrame is not surviving the Arrow
round-trip. Fall back to `DF.head(0)` and, failing that, report it rather than
dropping the case: "never fires on an empty grid" is a documented contract line
and needs a test.

Stop the server before continuing.

- [ ] **Step 3: Write the failing test suite**

Create `test/test_grid_lifecycle_collect.py`:

```python
"""gridReady and firstDataRendered as zero-interaction auto-collect triggers.

Collector invocations are counted from the browser console, not from what
arrived in Python. `on_grid_state_change` runs only when the component's state
value changes, so a second, byte-identical collect would be invisible on the
Python side — and a second collect is exactly the regression this suite guards:
AG-Grid queues the `firstDataRendered` dispatch into requestAnimationFrame, so
a listener attached from a React effect in the same tick does win the race.

The `debug=True` console line the count comes from is emitted by
`useAutoCollect` immediately before it posts the result to the host, so it
tracks collector calls one for one.
"""

import json
import re
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

from e2e_utils import StreamlitRunner

ROOT_DIRECTORY = Path(__file__).parent.parent.absolute()
APP_FILE = ROOT_DIRECTORY / "test" / "grid_lifecycle_collect.py"

COLLECT_LINE = re.compile(r'\[useAutoCollect\] Event "([^"]+)"')

#: How long to wait before asserting that nothing else fired. Every positive
#: assertion runs first and has already waited for a full browser -> Streamlit
#: -> browser round trip, so this only has to cover a late duplicate.
SETTLE_MS = 1500


@pytest.fixture(autouse=True, scope="module")
def streamlit_app():
    with StreamlitRunner(APP_FILE) as runner:
        yield runner


@pytest.fixture
def collected(page: Page, streamlit_app: StreamlitRunner):
    """Event names the frontend collector was invoked with, in order.

    Navigates as part of the fixture: the console listener has to be attached
    before the first load or the page's own lines are missed.
    """
    names: list[str] = []

    def _on_console(message):
        found = COLLECT_LINE.search(message.text)
        if found:
            names.append(found.group(1))

    page.on("console", _on_console)
    page.goto(streamlit_app.server_url)
    page.get_by_role("img", name="Running...").is_hidden()
    return names


def select_case(page: Page, case: str) -> None:
    page.get_by_test_id("stRadio").get_by_text(case, exact=True).click()


def test_grid_ready_collects_once_without_interaction(page: Page, collected):
    select_case(page, "gridReady")

    expect(page.get_by_test_id("fires-lc_ready")).to_have_text("gridReady")

    page.wait_for_timeout(SETTLE_MS)
    assert collected == ["gridReady"]


def test_first_data_rendered_collects_once_without_interaction(page: Page, collected):
    select_case(page, "firstDataRendered")

    expect(page.get_by_test_id("fires-lc_first")).to_have_text("firstDataRendered")

    page.wait_for_timeout(SETTLE_MS)
    assert collected == ["firstDataRendered"]


def test_both_triggers_fire_once_each_and_in_order(page: Page, collected):
    """gridOptions handlers are queued until gridReady has fired, so the order
    is a property of AG-Grid, not of luck."""
    select_case(page, "both")

    expect(page.get_by_test_id("fires-lc_both")).to_have_text(
        "gridReady,firstDataRendered"
    )

    page.wait_for_timeout(SETTLE_MS)
    assert collected == ["gridReady", "firstDataRendered"]


def test_grid_ready_snapshot_is_post_restore(page: Page, collected):
    """The ordering trap: a collect placed before the restore block in
    onGridReady returns the columnDefs layout, and the feature then lies."""
    select_case(page, "restore")

    state_element = page.get_by_test_id("state-lc_restore")
    expect(state_element).to_contain_text("rowGroupIndex")

    state = json.loads(state_element.inner_text())
    by_id = {entry["colId"]: entry for entry in state}
    assert by_id["region"]["rowGroupIndex"] == 0
    assert by_id["channel"]["hide"] is True


def test_empty_grid_never_fires_first_data_rendered(page: Page, collected):
    select_case(page, "empty")

    grid = page.locator(".st-key-lc_empty")
    expect(grid.locator(".ag-root")).to_be_visible()
    expect(grid.locator(".ag-row")).to_have_count(0)

    page.wait_for_timeout(SETTLE_MS)
    assert collected == []
    expect(page.get_by_test_id("fires-lc_empty")).to_have_text("")


def test_user_handler_is_chained_and_runs_once(page: Page, collected):
    """A prop of the same name replaces the gridOptions key rather than adding
    to it, so the chain is hand-written — and a hand-written chain is where a
    handler gets called twice."""
    select_case(page, "chain")

    expect(page.get_by_test_id("fires-lc_chain")).to_have_text("firstDataRendered")

    page.wait_for_timeout(SETTLE_MS)
    assert collected == ["firstDataRendered"]
    assert page.evaluate("window.__userFirstDataRendered") == 1
```

- [ ] **Step 4: Run the new suite**

Run: `uv run pytest test/test_grid_lifecycle_collect.py -q`
Expected: 6 passed.

If `select_case` cannot find an option, print the radio's rendered text with
`page.get_by_test_id("stRadio").inner_text()` and match the real label rather
than guessing.

- [ ] **Step 5: Commit**

```bash
git add test/grid_lifecycle_collect.py test/test_grid_lifecycle_collect.py
git commit -m "Cover both lifecycle triggers: one fire each, post-restore, empty grid, user chain"
```

---

### Task 5: Documentation, stale comments, version bump

**Files:**
- Modify: `README.md:73-77`
- Modify: `test/grid_return.py:179-181`
- Modify: `test/grid_agg_export.py:57-70`
- Modify: `pyproject.toml:3`
- Modify: `st_aggrid/pyproject.toml:13`

**Interfaces:**
- Consumes: the finished behaviour.
- Produces: the release.

- [ ] **Step 1: Replace the README's rejection paragraph**

In `README.md`, replace the paragraph beginning "**`gridReady` and
`firstDataRendered` are rejected in `update_on`**" and the "Only these two names
are rejected" paragraph that follows it with:

```markdown
**`gridReady` and `firstDataRendered` are zero-interaction triggers.** Either
name in `update_on` produces exactly one auto-collect per grid creation, with no
click. They are served as callbacks bound when the grid is created, not as event
subscriptions, and what each one sees differs:

| Trigger | Fires | Sees |
|---|---|---|
| `gridReady` | Always, once per grid creation | The restored column layout, row groups, the `merge` overlay and pre-selection. **Not** scroll position, focused cell, cell selection, pivot column state, or a filter whose restore AG-Grid deferred: AG-Grid applies those later. |
| `firstDataRendered` | Once per grid creation, **only if at least one row renders** | Everything above, plus the deferred restore. This is the complete post-restore snapshot. |

Restoring a full `initial_state` and need the snapshot to match it? Use
`firstDataRendered`. Need a guaranteed single fire even on a grid with no rows?
Use `gridReady`. Both are read at grid creation, so adding either name on a later
rerun takes effect the next time the grid mounts.

Neither can be debounced: `("gridReady", 300)` raises `ValueError`, because a
debounce coalesces a burst of firings and these fire once.

That is the only check. `update_on` is otherwise unchecked — AG-Grid's event set
moves with every release and this package keeps no copy of it, so a misspelled
event name is still a silent no-op.
```

- [ ] **Step 2: Correct the two stale e2e comments**

In `test/grid_return.py`, replace the three comment lines above `update_on`:

```python
        # These are user-driven events on purpose: this grid tests collection
        # from interaction. "gridReady" now works as a zero-interaction
        # trigger (see the README's Auto-Collect section) and would add a fire
        # on every mount that the assertions here do not expect.
```

In `test/grid_agg_export.py`, replace the paragraph that starts
"`update_on=["sortChanged"]`, not `["gridReady"]`" and runs to "See
`test_grid_agg_export.py` for the click." with:

```
`update_on=["sortChanged"]`, not `["gridReady"]`: the lifecycle triggers work
now (README, Auto-Collect), but this suite is about exporting what a settled,
user-sorted grid holds. So the test clicks the (hidden) row-group column's
header once, ascending, to fire a genuine `sortChanged` after the grid has
settled — ascending because it reproduces the fixture's natural campaign order
(A before B) so the CSV is identical to what an unsorted grid would export,
keeping the pinned strings meaningful. See `test_grid_agg_export.py` for the
click.
```

- [ ] **Step 3: Widen what `event_name` is documented to hold**

The collector no longer validates the event name against AG-Grid's event set,
because 9.3's menu handler will drive a collect under a name AG-Grid never
emits. Three places promise otherwise today; make each say "event or action".

`README.md:63`:

```python
result.event_name      # name of the event or action that triggered the update
```

`README.md:639`, in the result-attribute table, change the `.event_name`
description to `Triggering event or action name`.

`st_aggrid/result.py:92`:

```python
        """Name of the event or action that triggered this update."""
```

- [ ] **Step 4: Check nothing stale survives**

Run: `grep -rn "never fire\|can never reach\|UNSUPPORTED_UPDATE_ON" README.md st_aggrid test --include=*.py --include=*.ts --include=*.tsx --include=*.md | grep -v __pycache__`
Expected: no matches.

- [ ] **Step 5: Bump both versions**

`pyproject.toml:3` and `st_aggrid/pyproject.toml:13`: `2.4.1` → `2.4.2`.

Run: `grep -n 'version = "2.4.2"' pyproject.toml st_aggrid/pyproject.toml`
Expected: one match in each file.

Run: `uv run pytest test/unit/test_component_manifest.py -q`
Expected: PASS. This is the test that fails if the two versions drift.

- [ ] **Step 6: Run everything**

Run: `uv run pytest -m "not slow" -q`
Expected: all green, including the new suite and every pre-existing e2e suite.

- [ ] **Step 7: Commit**

```bash
git add README.md st_aggrid/result.py test/grid_return.py test/grid_agg_export.py pyproject.toml st_aggrid/pyproject.toml
git commit -m "Document the lifecycle triggers and bump to 2.4.2"
```

---

## After the plan

Not part of any task, and not this repository's to do:

- Record slice 9.1 in the consumer's `dash-ai-CHANGELOG.md` and delete the slice
  from `dash-ai-TASKS.md`, per that tracker's closing rule.
- Do **not** add either name to the consumer's `DEFAULT_GRID_EVENTS`.
  `is_programmatic_grid_event` lets `gridReady` through because it has no
  `source`, so every grid mount would write a column snapshot to
  `session_state`. The spec predicts that the snapshot equals what was just
  restored and so cannot loop, but that is a prediction and the consumer has to
  measure it.
