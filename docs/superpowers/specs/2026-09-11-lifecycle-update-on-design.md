# `gridReady` / `firstDataRendered` as `update_on` triggers — Design

**Status:** designed against the code, not yet implemented
**Branch:** `lifecycle-update-on` (off `main` at `10205d1`)
**Date:** 2026-09-11
**Release:** 2.4.2 (additive)
**Consumer task:** stream 9, slice 9.1 (`dash-ai-TASKS.md`)

All `path:line` references are to this repository at `10205d1` unless the path
starts with `web_app/`, which is the consumer (`hitapps_analytics`).

## Problem

`update_on=["gridReady"]` and `update_on=["firstDataRendered"]` do not work, and
since 2026-08-16 they raise `ValueError` instead of failing silently
(`st_aggrid/aggrid.py:35`, `:40`; `README.md:73`). The rejection was a trap
closure, not a fix: a caller who wants one auto-collect as soon as the grid is
ready still has nowhere to put it and has to fake a user interaction. Both e2e
apps that wanted exactly that say so in a comment and click a header instead
(`test/grid_agg_export.py:57`, `test/grid_return.py:179`).

The cause is structural for `gridReady`. Listeners for `collect`/`update_on`
are attached in an effect guarded on the `gridApi` state
(`st_aggrid/frontend/src/hooks/useAutoCollect.ts:125`), and that state is set
from inside the component's own `onGridReady`
(`st_aggrid/frontend/src/AgGridComponent.tsx:803`). The event being subscribed
to is the event that makes subscription possible.

For `firstDataRendered` the 2026-08-16 write-up is wrong in a way that matters.
AG-Grid does not emit it synchronously during the first render cycle: the
dispatch is queued into `requestAnimationFrame` and guarded by a
`dataFirstRenderedFired` flag (`ag-grid-community` 36.0.0,
`dist/package/main.esm.mjs:34501`). A React effect committed in the same tick
therefore attaches **before** the frame callback runs, so a listener registered
through `update_on` would in practice fire. That makes the naive fix actively
dangerous: wiring a lifecycle callback without also removing the name from the
`addEventListener` loop produces two collects, not one.

### Three facts from the AG-Grid 36.0.0 sources that shape the design

1. **`firstDataRendered` fires at most once per grid instance**
   (`dataFirstRenderedFired`, `main.esm.mjs:34501`). The "exactly once"
   requirement is satisfied by the grid itself once the trigger is a lifecycle
   callback; no de-duplication is needed on our side.
2. **`gridOptions` event handlers are queued until `gridReady` has fired**
   (`main.esm.mjs:26759`). `onFirstDataRendered` is therefore guaranteed to run
   after `onGridReady`; the ordering does not have to be defended by hand.
3. **`initialState` restore runs in four phases**, not one: `gridReady`,
   `columnsInitialised`, `rowCountReady` and `firstDataRendered`
   (`StateService`, `main.esm.mjs:51232`). `setFirstDataRenderedState`
   (`:51407`) is where scroll, focused cell, cell selection, pivot column state
   and the **deferred filter state** land. A snapshot taken at the end of our
   `onGridReady` cannot be fully post-restore for a grid that passes
   `initial_state`, no matter how carefully the collect is ordered inside that
   callback.

Fact 3 is the one the slice description under-states. "Collect after the
restore block" is necessary and not sufficient.

A fourth fact constrains the contract rather than the design:
`firstDataRendered` is dispatched from the first non-pinned, non-loading row's
`setComp` (`main.esm.mjs:30632`). **A grid with no rows never fires it.**

## Scope

**In.** Both names become legal `update_on` entries, served as lifecycle
callbacks bound at grid creation rather than as subscriptions. `useAutoCollect`
returns its collector so any caller inside the component can drive one collect
with any event name. Python validation changes subject. README documents what
each trigger sees. New e2e app and suite; the unit suite is rewritten against
the new subject.

**Out.** The misspelled-event-name hole: `update_on` stays otherwise unchecked,
for the reason already recorded at `st_aggrid/aggrid.py:29`. Any consumer-side
change, including adding either name to `DEFAULT_GRID_EVENTS`
(`web_app/src/bi_core/charts/grid_state.py:48`). The colour-scheme picker (9.3)
that this refactor unblocks. Any AG-Grid version bump.

**Design rule: additive.** A grid whose `update_on` names neither event runs
the same code path it runs today and pays nothing. This is literal for the
listener loop, which gains one membership test, and for `onGridReady`, which
gains one guarded call after everything it does now.

## Public contract

### `update_on`

Both names are accepted as bare strings. Each produces exactly one auto-collect
per grid creation, with `result.event_name` set to the name and
`result.event_data` to the serialized AG-Grid event.

| Trigger | Fires | Sees |
|---|---|---|
| `gridReady` | Always, once per grid creation | Column layout as restored by `initialState`'s `gridReady` and `columnsInitialised` phases, plus everything this component restores in its own `onGridReady`: row groups, the `merge` overlay, pre-selection. **Not** scroll, focused cell, cell selection, pivot column state, or a filter whose restore AG-Grid deferred. |
| `firstDataRendered` | Once per grid creation, **only if at least one row renders** | Everything above, plus the `firstDataRendered` restore phase. This is the complete post-restore snapshot. |

The asymmetry is the contract, not an implementation detail. A caller
restoring a full `initial_state` and wanting the snapshot to match it must use
`firstDataRendered`. A caller who wants a guaranteed single fire even on an
empty grid must use `gridReady`.

Both triggers are read **at grid creation**. Adding either name to `update_on`
on a later rerun has no effect until the grid remounts (a key change, e.g. a
saved-view switch).

### Debounce form

`(eventName, debounce_ms)` on either name raises `ValueError`. A debounce
coalesces a burst of firings; a once-per-creation event has no burst, so the
tuple is a request the component cannot honour. Rejecting keeps the property
that the 2026-08-16 validation was introduced to protect: nothing in
`update_on` is silently dropped, except a name nobody can verify.

### Collector channel

`useAutoCollect` returns `collectNow(eventName, eventData, api?)`. The event
name is not validated against AG-Grid's event set, so a caller inside the
component may drive a collect under a synthetic name. This release uses it for
the two lifecycle names only; 9.3's menu handler is the reason the channel is
general now rather than later. `result.event_name` is therefore documented as
"the name of the event or action that triggered the update", not "the AG-Grid
event name".

## Frontend

### `st_aggrid/frontend/src/hooks/useAutoCollect.ts`

Three changes.

**A lifecycle set, exported.**

```ts
export const LIFECYCLE_EVENTS: ReadonlySet<string> = new Set([
  "gridReady",
  "firstDataRendered",
])
```

**The collector takes an explicit api and is returned.** `collectAndSend`
becomes `collectNow` with signature
`(eventName: string, eventData: unknown, api?: GridApi) => void`. A ref inside the
hook, `apiRef`, is assigned from the `gridApi` prop during render — the same pattern
already used for `notesEditableRef` (`AgGridComponent.tsx:175`) — and the guard
at `:64` becomes:

```ts
const target = api ?? apiRef.current
if (!target) return
```

Every later use of `gridApi` inside the collector reads `target`. The
`useCallback` dependency list drops `gridApi`, leaving
`[collectConfig, setStateValue, debug]`, so the returned function is stable
across the `null → api` transition. That stability is what lets `onGridReady`
call it while the `gridApi` state is still `null`, which is exactly where the
naive fix fails.

The programmatic-source filter at `:80-93` is unchanged and is load-bearing
here: neither `GridReadyEvent` nor `FirstDataRenderedEvent` carries a `source`,
so both pass the filter. Nothing about them looks programmatic to it.

**The listener loop skips lifecycle names.** Inside `for (const entry of updateOn)`
(`:131`), before the branch:

```ts
const name = Array.isArray(entry) ? entry[0] : entry
if (LIFECYCLE_EVENTS.has(name)) continue
```

Without this, `firstDataRendered` collects twice (see *Problem*, fact about
`requestAnimationFrame`). The `debug` log at `:157` moves into the two branches
so it never claims a listener that was skipped.

### `st_aggrid/frontend/src/AgGridComponent.tsx`

`LIFECYCLE_EVENTS` is imported from the hook so the two files cannot drift
apart on which names are lifecycle names.

**Capture the collector** at the existing call site (`:457`):

```ts
const collectNow = useAutoCollect({ ... })
```

**Derive which lifecycle triggers were asked for**, next to the `updateOn` memo
(`:450`):

```ts
const lifecycleWanted = useMemo(() => {
  const names = new Set<string>()
  for (const entry of updateOn) {
    const name = Array.isArray(entry) ? entry[0] : entry
    if (LIFECYCLE_EVENTS.has(name)) names.add(name)
  }
  return names
}, [updateOn])
```

**`gridReady`: the last statement of `onGridReady`**, after the user's own
handler is chained (`:973-977`):

```ts
if (lifecycleWanted.has("gridReady")) {
  collectNow("gridReady", event, event.api)
}
```

`lifecycleWanted` and `collectNow` join the dependency list at `:979`.

Placement is the main implementation trap and the ordering rule is: **the
caller's handler runs first, the collect runs last.** The restore block
(`:941-959`) and pre-selection (`:961-971`) must precede it or `getColumnState`
returns the pre-restore layout and the feature lies rather than fails. The
user's `onGridReady` is treated as part of restore for the same reason.

**`firstDataRendered`: a new prop with the same chain.**

```ts
const onFirstDataRendered = useCallback(
  (event: FirstDataRenderedEvent) => {
    const { onFirstDataRendered: userHandler } = gridOptions
    if (userHandler) userHandler(event)
    if (lifecycleWanted.has("firstDataRendered")) {
      collectNow("firstDataRendered", event, event.api)
    }
  },
  [gridOptions, lifecycleWanted, collectNow]
)
```

passed at `:1022-1025` alongside `onGridReady`. The manual chain is required,
not defensive: `_combineAttributesAndGridOptions`
(`ag-grid-community/dist/package/main.esm.mjs:1005`) overwrites a `gridOptions`
key with the prop of the same name, so a user's `onFirstDataRendered` supplied
through `grid_options` would otherwise be dropped. This is verified, and it is
the same mechanism the existing `onGridReady` chain relies on.

Chaining in a prop rather than injecting the handler into the memoized
`gridOptions` (`:398`) is a deliberate departure from the slice description.
The prop keeps both lifecycle handlers in one shape, keeps the `gridOptions`
memo purely a translation of Python-sent config, and avoids a second place
where a user handler can be silently shadowed.

## Python

`st_aggrid/aggrid.py` — the constant changes name and meaning:

```python
LIFECYCLE_UPDATE_ON_EVENTS: frozenset = frozenset({"gridReady", "firstDataRendered"})
```

It is module-local and absent from `st_aggrid/__init__.py`, so the rename is
internal. `validate_update_on` (`:40`) keeps its name and call site (`:374`)
and changes subject: it now rejects only the **tuple form** on these names,
reporting every offender in one raise, and says why a debounce cannot apply. The
docstring reference at `:213` is updated to match.

No other Python changes. `AgGrid`'s signature, `AgGridResult` and
`call_grid_api` are untouched.

## Tests

### Unit — `test/unit/test_update_on_validation.py`

Rewritten against the new subject, keeping the file and the parametrisation
over the constant:

- both bare names now pass;
- `(name, ms)` raises for each name;
- both offenders in one call produce one raise naming both;
- an ordinary tuple (`("columnResized", 400)`) still passes;
- an unknown name is still not rejected (the deliberate hole, unchanged).

### E2E — `test/grid_lifecycle_collect.py` + `test/test_grid_lifecycle_collect.py`

A radio-selected app in the style of `test/grid_return.py`. Fire counting goes
through an `on_grid_state_change` callback that appends `result.event_name` to a
list in `session_state`, rendered into a `data-testid` element. Counting the
list rather than reading the last `grid_state` is the point: a second fire
would otherwise be invisible, since the later collect overwrites the earlier
one under the same state key.

| Case | Asserts |
|---|---|
| `update_on=["gridReady"]` | Without any interaction: the list is exactly `["gridReady"]`, and the collected `columnState` is non-empty. |
| `update_on=["firstDataRendered"]` | Without any interaction: exactly `["firstDataRendered"]`. |
| Both names | Exactly `["gridReady", "firstDataRendered"]`, in that order. Guards fact 2 and guards against a double fire. |
| Post-restore | A grid whose `columns_state` hides one column and sets a row group. The `gridReady` snapshot shows the restored layout, not the `columnDefs` default. This is the regression test for the ordering trap. |
| Empty `rowData` + `firstDataRendered` | The grid renders and the list stays empty. Pins the README's "only if at least one row renders". |
| User `onFirstDataRendered` via `JsCode` | The user handler runs exactly once and the collect also happens. CCv2 runs without an iframe, so the handler can increment a `data-testid` counter in the host document directly. |

Reading rows follows the house rule: by row index, never DOM order.

### Comments in existing apps

`test/grid_return.py:179-181` and the docstring paragraph at
`test/grid_agg_export.py:57-70` both explain at length why `gridReady` cannot
be used. Both are rewritten to state what is true after this release: the
trigger works, and these two suites keep clicking a header because they are
testing a user-driven collect, not a lifecycle one.

## Risks

**Radius.** `useAutoCollect` is the collect path for every grid, and the change
touches its guard, its callback identity and its listener loop. The failure
mode is not "the new trigger did not fire", it is "state collection moved
everywhere". A full e2e run of the fork is mandatory, not the new suite alone.

**An extra rerun per mount.** A grid that asks for either trigger writes
`grid_state` during mount, which is one Streamlit rerun the grid did not
previously cause. It cannot loop: the CCv2 root is keyed and a rerun re-renders
rather than remounts (`st_aggrid/frontend/src/index.tsx:8`), so `onGridReady`
does not fire again. A key change (saved-view switch) remounts and collects
once more, which is correct.

**Consumer capture.** `is_programmatic_grid_event`
(`web_app/src/bi_core/charts/grid_state.py:181`) treats an event as programmatic
when `source` starts with `api`. `gridReady` has no `source`, so it returns
`False` and capture runs. Adding the name to `DEFAULT_GRID_EVENTS` would write
a column snapshot to `session_state` on every grid mount. With the ordering
above the snapshot should equal what was just restored, so no loop, but that is
a prediction and the consumer must measure it before adopting either name. No
consumer change is part of this release; `gridReady` and `firstDataRendered`
appear in no consumer call today.

**Event payload size.** `serializeEventData` walks two levels
(`useAutoCollect.ts:21`), so `event.api` serializes to an object of nulls and
`event.context` serializes its own top level, which for this fork carries the
grid-level colour-scale defaults. This is the shape every existing event
already produces; it is called out only so nobody reads the new `event_data` as
a regression.

## Cost

Frontend: roughly 60 lines across two files. Tests: a new app and suite of
about 150 lines, plus a rewrite of the 67-line unit file. Documentation:
`README.md:73` replaced by the trigger table, two e2e comment blocks corrected.

A frontend rebuild is required (`corepack yarn build`), which shows as a delete
plus an add of the content-hashed `st_aggrid/frontend/build/index-*.js`, and the
full e2e run costs about six minutes.

Version 2.4.2 in both `pyproject.toml` and `st_aggrid/pyproject.toml`, which
must stay in sync.

## Done when

- `update_on=["gridReady"]` produces one auto-collect after grid readiness with
  no interaction, and the snapshot is post-restore for everything the
  `gridReady` row of the contract table claims.
- `update_on=["firstDataRendered"]` produces one auto-collect, exactly once,
  with synchronous `rowData`, and none when there are no rows.
- Neither name fires twice when both are requested.
- The tuple form on either name raises, and every other `update_on` shape
  behaves as it does today.
- `README.md:73` describes the new behaviour, including the empty-grid case and
  the split between what each trigger sees.
- The fork's e2e suites are green in full, not only the new one.
- Slice 9.1 is recorded in the consumer's `dash-ai-CHANGELOG.md` and removed
  from `dash-ai-TASKS.md`, per that tracker's closing rule.

## Correction (2026-09-11, during implementation)

Two claims in this spec did not survive contact with measurement, and the
shipped documentation (`README.md`, Auto-Collect section) says less than the
contract table above.

1. **The contract table's split of what `gridReady` cannot see does not hold
   up.** Three probes were tried. `focusedCell` and `scroll`, both read through
   `getState()`, were invalid: `getState()` returns cached state seeded from
   the supplied `initialState`, so it echoes the request back whether or not
   anything has actually been applied yet. A third probe read `scroll` through
   `getVerticalPixelRange()` instead, and measured `{top: 2000}` at both
   `gridReady` and `firstDataRendered` — the restored scroll was already in
   effect at the `gridReady` collect, the opposite of what the table above
   claims. The README therefore documents only what these three rounds could
   demonstrate (the restored column layout and row groups, the `merge`
   overlay, and pre-selection, all confirmed at `gridReady`) and drops the
   enumeration of what `gridReady` supposedly misses. Whether `gridReady` and
   `firstDataRendered` actually differ in what they see is an open question,
   not a documented behaviour.

2. **Naming both triggers on one grid delivers one host-side update, not
   two.** The frontend does collect twice — the e2e suite asserts this from
   the browser console — but `grid_state` is a single component state value
   rather than an event stream, and AG-Grid dispatches `firstDataRendered`
   from a `requestAnimationFrame` callback right behind the synchronous
   `gridReady` collect. The two writes land inside one flush window and
   collapse to the later one, so only the `firstDataRendered` collect reaches
   Python. This is now documented in the README rather than left as a
   consumer-side surprise.
