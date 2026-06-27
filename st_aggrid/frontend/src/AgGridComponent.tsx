import React, { useRef, useState, useCallback, useEffect, useMemo } from "react"
import { AgGridReact } from "ag-grid-react"

import {
  AllCommunityModule,
  GetRowIdParams,
  GridApi,
  GridReadyEvent,
  ModuleRegistry,
} from "ag-grid-community"

import { AgChartsEnterpriseModule } from "ag-charts-enterprise"
import { AllEnterpriseModule, LicenseManager } from "ag-grid-enterprise"

import isEqual from "lodash/isEqual"
import omit from "lodash/omit"
import debounce from "lodash/debounce"
import cloneDeep from "lodash/cloneDeep"

import { useAutoCollect } from "./hooks/useAutoCollect"
import { useExplicitApiCall } from "./hooks/useExplicitApiCall"
import { useStreamlitTheme } from "./hooks/useStreamlitTheme"
import { ThemeParser } from "./ThemeParser"

import GridToolBar from "./components/GridToolBar"

import {
  addCustomCSS,
  columnStateToInitialState,
  extractColumnStateFromDefs,
  extractRowGroupColumns,
  extractRowGroupColumnsFromState,
  injectProAssets,
} from "./utils/gridUtils"

import { parseGridOptions, parseData } from "./utils/parsers"
import type { AgGridData } from "./types/AgGridTypes"

import "@fontsource/source-sans-pro"
import "./AgGrid.css"

interface AgGridComponentProps {
  data: AgGridData
  setStateValue: (key: string, value: any) => void
  setTriggerValue: (key: string, value: any) => void
  parentElement: HTMLElement
}

// Track whether modules have been registered to avoid double registration
let modulesRegistered = false

function registerModules(data: AgGridData) {
  if (modulesRegistered) return
  modulesRegistered = true

  const enableEnterprise = data.enable_enterprise_modules
  if (enableEnterprise === "enterprise+AgCharts") {
    ModuleRegistry.registerModules([
      AllEnterpriseModule.with(AgChartsEnterpriseModule),
    ])
    if (data.license_key) {
      LicenseManager.setLicenseKey(data.license_key)
    }
  } else if (enableEnterprise === true || enableEnterprise === "enterpriseOnly") {
    ModuleRegistry.registerModules([AllEnterpriseModule])
    if (data.license_key) {
      LicenseManager.setLicenseKey(data.license_key)
    }
  } else {
    ModuleRegistry.registerModules([AllCommunityModule])
  }
}

// Build a {field: key} map of a group row's dimension ancestry (this node and
// its parents). Used by the group-dimension notes probe (debug_group_notes) and,
// later, the notes_groups matcher. See REQUIREMENT-group-dimension-notes.md.
function groupDimensionAncestry(node: any): Record<string, any> {
  const map: Record<string, any> = {}
  let n: any = node
  while (n) {
    if (n.field != null && n.key != null && !(n.field in map)) {
      map[n.field] = n.key
    }
    n = n.parent
  }
  return map
}

// Track whether custom CSS has been injected
let cssInjected = false
let proAssetsInjected = false

const AgGridComponent: React.FC<AgGridComponentProps> = ({
  data,
  setStateValue,
  setTriggerValue,
  parentElement,
}) => {
  // Grid API is held both as a ref (for imperative calls from callbacks and
  // effects that don't need to re-run on mount) and as state (so hooks like
  // `useAutoCollect` that attach event listeners re-run once the grid signals
  // readiness, not just on the next Streamlit-driven re-render).
  const gridApiRef = useRef<GridApi | null>(null)
  const [gridApi, setGridApi] = useState<GridApi | null>(null)
  const gridContainerRef = useRef<HTMLDivElement>(null)
  const prevDataRef = useRef<AgGridData | undefined>(undefined)

  // Live Find (AG-Grid 35.3) match counter for the toolbar's Find widget. Driven
  // by the `findChanged` event (see onGridReady) — reading findGetTotalMatches()
  // synchronously after setting findSearchValue returns a stale count.
  const [findState, setFindState] = useState<{ matches: number; active: number }>(
    { matches: 0, active: 0 }
  )
  const findCleanupRef = useRef<(() => void) | null>(null)

  // Cell Notes (AG-Grid 35.3 Enterprise) store. Held in a ref (not state) so the
  // getNote/setNote closures read the live map at call time and never go stale,
  // and so mutating it on edit doesn't trigger a React re-render. Seeded from
  // data.notes by the effect below.
  const notesStoreRef = useRef<Record<string, Record<string, any>>>({})
  // Editability read through a ref so the (stable) notesDataSource always sees the
  // current value without being rebuilt when notes_editable toggles.
  const notesEditableRef = useRef<boolean>(data.notes_editable ?? false)
  notesEditableRef.current = data.notes_editable ?? false
  // Monotonic token so the host can tell a fresh write-back from a stale one.
  const notesTokenRef = useRef<number>(0)
  // Last seeded data.notes (by content) — guards re-seeding on every rerun (the
  // host re-sends a structurally-equal but referentially-new object each pass),
  // which would otherwise clobber unacknowledged local edits.
  const lastNotesRef = useRef<unknown>(undefined)
  // Cleanup for the displayedColumnsChanged refit listener registered in
  // onGridReady (see the gated `sizeColumnsToFit` re-fit below). Held in a ref
  // so the unmount effect can tear it down without re-running onGridReady.
  const refitCleanupRef = useRef<(() => void) | null>(null)

  const debug = data.debug || false

  // Live Streamlit theme (reads --st-* CSS custom properties from the
  // component's wrapper element and subscribes to their changes). Used
  // instead of any Python-side detection, which can't see UI-level theme
  // toggles — those only update CSS variables, no server rerun.
  const streamlitTheme = useStreamlitTheme(parentElement)

  // Register modules once
  registerModules(data)

  // Inject custom CSS once
  if (!cssInjected && data.custom_css) {
    addCustomCSS(data.custom_css)
    cssInjected = true
  }

  // Inject pro assets once
  if (!proAssetsInjected && data.pro_assets && Array.isArray(data.pro_assets)) {
    data.pro_assets.forEach((asset) => {
      injectProAssets(asset?.js, asset?.css)
    })
    proAssetsInjected = true
  }

  // Parsed row data — recomputed when the incoming rowData reference changes.
  // Passed as a separate prop to <AgGridReact> so AG-Grid applies it reactively
  // with immutable-data semantics (preserves selection/scroll when getRowId is stable).
  // Depends on both data.rowData (Arrow path) and data.gridOptions.rowData
  // (JSON-fallback path, used when the DataFrame contains dict cells and
  // the Python side serializes via to_json instead of Arrow) — otherwise
  // the fallback path never re-parses and cells for dynamically added
  // columns stay empty.
  const rowData = useMemo(
    () => parseData(data),
    [data.rowData, data.gridOptions?.rowData]
  )

  // Stable getRowId based on the auto_unique_id marker, if present.
  // Memoized by rowData so identity stays stable across re-renders while schema is unchanged.
  const autoGetRowId = useMemo(() => {
    if (
      rowData.length > 0 &&
      Object.prototype.hasOwnProperty.call(rowData[0], "::auto_unique_id::")
    ) {
      return (params: GetRowIdParams) =>
        params.data["::auto_unique_id::"] as string
    }
    return undefined
  }, [rowData])

  // Cell Notes datasource (35.3). Built only when host notes are present; stable
  // across renders (rebuilds only when notes presence flips) so AG-Grid doesn't
  // re-init notes on every theme/config change. The closures read the live
  // notesStoreRef / notesEditableRef, so edits and editability changes are seen
  // without rebuilding. Skipped if the user supplied their own notesDataSource via
  // grid_options (see the merge into the gridOptions memo below).
  const notesPresent = data.notes != null
  const debugGroupNotes = data.debug_group_notes === true
  const notesGroups = Array.isArray(data.notes_groups) ? data.notes_groups : null
  const notesDataSource = useMemo(() => {
    // Diagnostic probe (REQUIREMENT-group-dimension-notes.md): a full-width notes
    // datasource that, for every group row, logs its {field: key} dimension
    // ancestry and renders a note showing it. Confirms the full-width group-row
    // notes path works on a real grid and reveals the exact keys to use in a
    // future `notes_groups` matcher. Read-only; no write-back.
    if (debugGroupNotes) {
      return {
        supportsFullWidthRows: true,
        getNote: (p: any) => {
          const node = p?.rowNode
          if (!node || !node.group) return undefined
          // Only mark the group-displaying cell (or the full-width group row),
          // not every aggregated value cell on the row.
          const onGroupCell =
            p?.location === "fullWidthRow" ||
            p?.column?.getColId?.() === "ag-Grid-AutoColumn" ||
            p?.column?.getColDef?.()?.showRowGroup
          if (!onGroupCell) return undefined
          const ancestry = groupDimensionAncestry(node)
          console.log("[AgGridComponent] group-notes probe", {
            location: p?.location,
            colId: p?.column?.getColId?.(),
            field: node.field,
            key: node.key,
            ancestry,
          })
          return { text: JSON.stringify(ancestry), readOnly: true }
        },
        setNote: () => {},
      }
    }
    // Group-dimension Notes (notes_groups): a note is a predicate over a group
    // row's dimension ancestry, not a cell coordinate. A rule matches when its
    // `match` is a subset of the row's ancestry; it is drawn on the boundary row
    // (where the match first completes) and the most-specific rule wins on a
    // shared row. Read-only; no write-back. See REQUIREMENT-group-dimension-notes.md.
    if (notesGroups && notesGroups.length > 0) {
      const valEq = (av: any, mv: any): boolean => {
        const a = String(av)
        const m = String(mv)
        // Date dims stringify as "YYYY-MM-DD" or "YYYY-MM-DD HH:MM:SS" — compare a
        // YYYY-MM-DD match value against the key's first 10 chars; else compare exactly.
        if (/^\d{4}-\d{2}-\d{2}$/.test(m)) return a.slice(0, 10) === m
        return a === m
      }
      const matchesAll = (
        m: Record<string, any>,
        a: Record<string, any>
      ): boolean => {
        for (const k in m) {
          if (!(k in a) || !valEq(a[k], m[k])) return false
        }
        return true
      }
      return {
        supportsFullWidthRows: true,
        getNote: (p: any) => {
          const node = p?.rowNode
          if (!node || !node.group) return undefined
          // Pin to the cell that renders this node's group value, so the note is
          // not duplicated across the per-dimension auto columns (multipleColumns).
          const colDef = p?.column?.getColDef?.()
          const showsThis =
            !!colDef &&
            (colDef.showRowGroup === true || colDef.showRowGroup === node.field)
          const onGroupCell =
            p?.location === "fullWidthRow" ||
            p?.column?.getColId?.() === "ag-Grid-AutoColumn" ||
            showsThis
          if (!onGroupCell) return undefined
          const anc = groupDimensionAncestry(node)
          const ancParent = node.parent
            ? groupDimensionAncestry(node.parent)
            : {}
          let best: any = null
          let bestFields = -1
          for (const rule of notesGroups) {
            const m = (rule && rule.match) || {}
            if (!matchesAll(m, anc) || matchesAll(m, ancParent)) continue
            const nf = Object.keys(m).length
            if (nf > bestFields) {
              best = rule
              bestFields = nf
            }
          }
          if (!best) return undefined
          const note = best.note
          return typeof note === "object" && note !== null
            ? { ...note, readOnly: true }
            : { text: String(note), readOnly: true }
        },
        setNote: () => {},
      }
    }
    if (!notesPresent) return undefined
    return {
      getNote: ({ rowNode, column }: any) => {
        const colId = column?.getColId?.()
        if (rowNode?.id == null || colId == null) return undefined
        const stored = notesStoreRef.current?.[rowNode.id]?.[colId]
        if (stored == null) return undefined
        const editable = notesEditableRef.current
        // Accept either a plain string note or a full Note object from the host.
        const base =
          typeof stored === "object" && stored !== null
            ? { ...stored }
            : { text: String(stored) }
        return { ...base, readOnly: editable ? base.readOnly === true : true }
      },
      setNote: ({ rowNode, column, note }: any) => {
        if (!notesEditableRef.current) return
        const colId = column?.getColId?.()
        if (rowNode?.id == null || colId == null) return
        const store = notesStoreRef.current
        if (note === undefined) {
          if (store[rowNode.id]) {
            delete store[rowNode.id][colId]
            if (Object.keys(store[rowNode.id]).length === 0) {
              delete store[rowNode.id]
            }
          }
        } else {
          ;(store[rowNode.id] ??= {})[colId] = note
        }
        // Sticky write-back so the host can collect note edits across reruns
        // (mirrors the csv_export sticky contract). setTriggerValue would be lost
        // on the multi-rerun passes a multi-grid page makes.
        notesTokenRef.current += 1
        setStateValue("notes", {
          token: notesTokenRef.current,
          notes: cloneDeep(store),
        })
      },
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [notesPresent, debugGroupNotes, notesGroups, setStateValue])

  // Grid options WITHOUT rowData — recomputed only when config inputs change.
  const gridOptions = useMemo(() => {
    const go = parseGridOptions(data, streamlitTheme)
    // Defensive: strip any rowData that may have been carried over so the
    // separate <AgGridReact rowData> prop is the single source of truth.
    delete (go as any).rowData

    // Honor user-provided getRowId; fall back to the auto_unique_id marker.
    if (!("getRowId" in go) && autoGetRowId) {
      go.getRowId = autoGetRowId
    }

    // Inject the data-driven notes datasource unless the user supplied their own
    // via grid_options (the JsCode escape hatch wins).
    if (notesDataSource && !("notesDataSource" in go)) {
      ;(go as any).notesDataSource = notesDataSource
    }

    return go
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data.gridOptions, data.theme, streamlitTheme, data.allow_unsafe_jscode, autoGetRowId, notesDataSource])

  // Saved column layout applied at grid *creation* (pre-paint) via the
  // `initialState` prop, so restored columns never flash in then hide. AG-Grid
  // reads `initialState` only when the grid is created; Streamlit reruns reuse
  // the same component (key stable), and a view switch remounts (key changes)
  // to re-read it — exactly the restore boundaries we care about.
  const initialState = useMemo(() => {
    // A raw GridState (saved-view restore) wins pre-paint.
    if (data.initial_state) return data.initial_state
    // Merge mode is a partial overlay applied post-creation (onGridReady + the
    // columns_state effect). A partial delta must NOT seed initialState — that
    // is a full-state snapshot, so AG-Grid would treat the delta's value/agg
    // entries as the complete column state and drop colDef-driven row groups
    // and pivot at creation. Use the raw `initial_state` prop for pre-paint
    // restore instead.
    if (data.columns_state_mode === "merge") return undefined
    return columnStateToInitialState(
      data.columns_state,
      data.gridOptions?.pivotMode
    )
  }, [
    data.initial_state,
    data.columns_state,
    data.columns_state_mode,
    data.gridOptions?.pivotMode,
  ])

  // Memoize config arrays to avoid re-registering listeners on every render
  const collectConfig = useMemo(
    () => data.collect || ["getSelectedRows"],
    [data.collect]
  )
  const updateOn = useMemo(
    () => data.update_on || ["selectionChanged", "filterChanged", "sortChanged"],
    [data.update_on]
  )

  // Auto-collect hook — needs a stable `gridApi` value that changes exactly
  // once the grid becomes ready, so `useState` (not the ref) is the source.
  useAutoCollect({
    gridApi,
    collectConfig,
    updateOn,
    setStateValue,
    debug,
  })

  // Explicit API call hook
  useExplicitApiCall({
    gridApi,
    apiCallRequest: data.api_call,
    setTriggerValue,
    debug,
  })

  // Handle runtime updates that must go through the imperative API.
  // rowData is NOT handled here — it flows via the <AgGridReact rowData> prop.
  useEffect(() => {
    // Capture the previous data and always update the ref before any early
    // return — AG-Grid's onGridReady fires asynchronously after this effect,
    // so on first run gridApi is null. If we return early without updating
    // the ref, the next effect run sees prevData as undefined and skips the
    // diff block below, dropping the user's first widget-driven update.
    const prevData = prevDataRef.current
    prevDataRef.current = data

    if (!gridApiRef.current || gridApiRef.current.isDestroyed()) return

    // First commit — nothing to diff against; onGridReady already applied initial state.
    if (!prevData) return

    // Diff gridOptions (excluding rowData, which is handled by the prop)
    const prevGo = omit(prevData.gridOptions, "rowData")
    const currGo = omit(data.gridOptions, "rowData")
    if (!isEqual(prevGo, currGo)) {
      const go = parseGridOptions(data)
      delete (go as any).rowData

      // Snapshot the live sort before updateGridOptions. Re-processing
      // columnDefs reverts sort to the colDef `initialSort` default, so the
      // user's interactive sort would be lost. Sort is runtime state (like
      // selection/scroll) — preserve it across the config update rather than
      // letting the Python-declared default win.
      const savedSortState = gridApiRef.current
        .getColumnState()
        .filter((c) => c.sort != null)
        .map((c) => ({ colId: c.colId, sort: c.sort, sortIndex: c.sortIndex }))

      // Snapshot the open tool panel before updateGridOptions. Re-applying
      // gridOptions re-applies `sideBar` (whose defaultToolPanel is "" for our
      // grids), which AG-Grid resets to its closed default — collapsing a panel
      // the user had open while toggling column visibility. Captured now and
      // re-opened after the column re-apply. getOpenedToolPanel() returns null
      // when nothing is open, so the restore is naturally guarded.
      const openedToolPanel = gridApiRef.current.getOpenedToolPanel()

      gridApiRef.current.updateGridOptions(go)

      // updateGridOptions applies new columnDefs but AG-Grid preserves its
      // internal column state for properties like hide, rowGroup, pivot,
      // aggFunc, pinned. Extract these from the new columnDefs and force
      // them via applyColumnState so Python-side changes take effect.
      if (!isEqual(prevData.gridOptions?.columnDefs, data.gridOptions?.columnDefs)) {
        const colState = extractColumnStateFromDefs(data.gridOptions?.columnDefs)
        if (colState.length > 0) {
          gridApiRef.current.applyColumnState({
            state: colState,
            applyOrder: false,
          })
        }

        // Use dedicated setRowGroupColumns API instead of relying on
        // applyColumnState for row grouping — it's the only reliable
        // way to add/remove row groups on a live grid in pivot mode.
        const rowGroupCols = extractRowGroupColumns(data.gridOptions?.columnDefs)
        gridApiRef.current.setRowGroupColumns(rowGroupCols)

        if (debug) {
          console.log(
            "[AgGridComponent] Applied column state from columnDefs:",
            colState,
            "rowGroupColumns:",
            rowGroupCols
          )
        }

        // Re-assert the merge overlay after the colDef re-derive. The re-derive
        // above re-shows every governed column (each colDef carries its real
        // aggFunc), which would override the control/manual visibility the merge
        // delta encodes. The columns_state effect below only re-applies when the
        // delta CONTENT changed (isEqual guard) — but a colDef rebuild
        // (row-group / layout flip) leaves the delta unchanged, so without this
        // the excluded columns surface on every such rebuild. Runs only on a real
        // colDef change, fires with source:"api" (skipped by capture), and is
        // batched with the re-derive in this synchronous effect — no flash, no
        // capture<->delta oscillation.
        if (
          data.columns_state != null &&
          data.columns_state_mode === "merge"
        ) {
          gridApiRef.current.applyColumnState({
            state: data.columns_state,
            applyOrder: false,
          })
          if (debug) {
            console.log(
              "[AgGridComponent] Re-asserted merge columns_state after colDef rebuild"
            )
          }
        }
      }

      // pivotMode must be set explicitly after column state changes —
      // updateGridOptions bundles it with columnDefs which can cause
      // AG-Grid to process them in the wrong order.
      if (prevData.gridOptions?.pivotMode !== data.gridOptions?.pivotMode) {
        gridApiRef.current.setGridOption(
          "pivotMode",
          data.gridOptions?.pivotMode ?? false
        )
        if (debug) {
          console.log(
            "[AgGridComponent] Set pivotMode:",
            data.gridOptions?.pivotMode
          )
        }
      }

      // Force recalculation of the client-side row model from the
      // grouping step onwards. Without this, columns that transition
      // from hidden to visible show empty cells because AG-Grid
      // skips valueGetter/aggregation evaluation for hidden columns.
      try {
        gridApiRef.current.refreshClientSideRowModel("group")
      } catch (err) {
        if (debug) {
          console.warn("[AgGridComponent] refreshClientSideRowModel failed:", err)
        }
      }

      // Restore the interactive sort captured before updateGridOptions.
      // `defaultState: { sort: null }` clears sort on any column not in the
      // snapshot, so a grid the user explicitly un-sorted stays un-sorted.
      gridApiRef.current.applyColumnState({
        state: savedSortState,
        defaultState: { sort: null },
      })
      if (debug) {
        console.log(
          "[AgGridComponent] Restored sort state:",
          savedSortState
        )
      }

      // updateGridOptions swaps columnDefs in place but doesn't re-render
      // already-painted cells, so property changes such as cellStyle /
      // cellClass / cellRenderer won't clear stale inline styles. Redraw
      // rows to guarantee the DOM reflects the new configuration.
      gridApiRef.current.redrawRows()

      // Re-open the tool panel the config update collapsed. Guarded on a
      // non-null snapshot (a panel the user had closed stays closed) and on the
      // panel not already being open again (avoids a redundant re-open/flash).
      if (
        openedToolPanel &&
        gridApiRef.current.getOpenedToolPanel() !== openedToolPanel
      ) {
        gridApiRef.current.openToolPanel(openedToolPanel)
        if (debug) {
          console.log("[AgGridComponent] Restored tool panel:", openedToolPanel)
        }
      }
    }

    // Diff columns_state
    if (!isEqual(prevData.columns_state, data.columns_state)) {
      if (data.columns_state != null) {
        const mergeMode = data.columns_state_mode === "merge"

        // DIAGNOSTIC (debug only): this fires exactly when the merge/replace
        // overlay RE-APPLIES because the delta content changed since the last
        // render. If a column the user just hid in the Columns panel appears in
        // `shown` here, the overlay is re-showing it (the capture<->delta lag) —
        // the root-cause signal for the manual-hide jitter.
        if (debug) {
          const cs = data.columns_state as any[]
          const shown = cs
            .filter((e) => e?.aggFunc != null)
            .map((e) => e.colId)
          const hidden = cs
            .filter((e) => "aggFunc" in e && e.aggFunc == null)
            .map((e) => e.colId)
          console.log(
            `[AgGridComponent] columns_state ${
              mergeMode ? "merge" : "replace"
            } re-apply (delta changed): shown=${shown.length} hidden=${hidden.length}`,
            { shown, hidden }
          )
        }

        // merge: a partial overlay — apply only the listed columns' state
        //   (applyOrder:false, no defaultState) so the user's manual edits on
        //   other columns and the existing column order are preserved.
        // replace: a full layout restore — apply order too.
        gridApiRef.current.applyColumnState({
          state: data.columns_state,
          applyOrder: !mergeMode,
        })

        // applyColumnState does not reliably (re)build row groups while pivot
        // mode is on, so drive them explicitly from the same state. In replace
        // mode this runs unconditionally (an empty result honors an explicit
        // un-group). In merge mode the delta usually carries no row-group info
        // (e.g. a value-only visibility overlay) and feeding the resulting [] to
        // setRowGroupColumns would wrongly clear every row group — so only touch
        // grouping when the delta actually carries row-group entries.
        const rowGroupCols = extractRowGroupColumnsFromState(data.columns_state)
        if (!mergeMode || rowGroupCols.length > 0) {
          gridApiRef.current.setRowGroupColumns(rowGroupCols)
        }
      }
    }
  }, [data])

  // Apply theme changes imperatively on an already-initialized grid.
  // AG-Grid's Theming API doesn't pick up a new `theme` bundled in
  // gridOptions via reconciliation — it needs an explicit setGridOption.
  useEffect(() => {
    if (!gridApiRef.current || gridApiRef.current.isDestroyed()) return
    const themeParser = new ThemeParser()
    const newTheme = themeParser.parse(data.theme, streamlitTheme ?? undefined)
    gridApiRef.current.setGridOption("theme", newTheme)
    if (debug) {
      console.log("[AgGridComponent] Applied theme update:", streamlitTheme)
    }
  }, [streamlitTheme, data.theme, gridApi, debug])

  // Seed the notes store from host-provided notes and re-render notes on already
  // painted cells. Guarded on a CONTENT change (isEqual) — the host re-sends a
  // referentially-new but equal object every rerun, so a plain reference check
  // would re-seed on each pass and clobber unacknowledged local edits. Kept out
  // of the big `[data]` effect so it never triggers updateGridOptions/redrawRows.
  useEffect(() => {
    if (isEqual(lastNotesRef.current, data.notes)) return
    lastNotesRef.current = data.notes
    notesStoreRef.current = data.notes ? cloneDeep(data.notes) : {}
    if (
      data.notes != null &&
      gridApiRef.current &&
      !gridApiRef.current.isDestroyed()
    ) {
      try {
        gridApiRef.current.refreshNotes()
      } catch (err) {
        if (debug) {
          console.warn("[AgGridComponent] refreshNotes failed:", err)
        }
      }
    }
  }, [data.notes, debug])

  // Tear down the displayedColumnsChanged refit listener on unmount (a view
  // switch / key change remounts the component, so this fires per mount).
  useEffect(() => {
    return () => {
      refitCleanupRef.current?.()
      refitCleanupRef.current = null
      findCleanupRef.current?.()
      findCleanupRef.current = null
    }
  }, [])

  const onGridReady = useCallback(
    (event: GridReadyEvent) => {
      gridApiRef.current = event.api
      setGridApi(event.api)

      if (debug) {
        console.log("[AgGridComponent] Grid ready", event)
      }

      // Keep the toolbar Find widget's match counter in sync. `findChanged`
      // carries the settled totals (totalMatches + the active FindMatch whose
      // numOverall is the 1-based position), so we never read a stale count.
      // Harmless when Find is unused / community mode — the event simply never
      // fires (FindModule isn't registered). Torn down in the unmount effect.
      const onFindChanged = (e: any) => {
        setFindState({
          matches: e?.totalMatches ?? 0,
          active: e?.activeMatch?.numOverall ?? 0,
        })
      }
      event.api.addEventListener("findChanged", onFindChanged)
      findCleanupRef.current = () => {
        if (!event.api.isDestroyed()) {
          event.api.removeEventListener("findChanged", onFindChanged)
        }
      }

      // Re-fit columns to grid width whenever the displayed column set changes
      // (hide/show, pivot/group). autoSizeStrategy:{type:'fitGridWidth'} runs
      // only at grid CREATION; updateGridOptions never re-runs it, so after a
      // column is hidden the remaining columns don't refill the width. Gated on
      // fitGridWidth so only grids that opted in refit (others keep their own
      // sizing). sizeColumnsToFit emits columnResized (source 'sizeColumnsToFit'),
      // NOT displayedColumnsChanged, so there is no refit->event->refit loop, and
      // a user's manual drag (source 'uiColumnResized') never triggers it. The
      // emitted columnResized is filtered from capture in useAutoCollect.
      const fitsGridWidth =
        (gridOptions as any)?.autoSizeStrategy?.type === "fitGridWidth"
      if (fitsGridWidth) {
        const debouncedRefit = debounce(
          () => {
            if (gridApiRef.current && !gridApiRef.current.isDestroyed()) {
              gridApiRef.current.sizeColumnsToFit()
            }
          },
          50,
          { leading: false, trailing: true, maxWait: 200 }
        )
        event.api.addEventListener("displayedColumnsChanged", debouncedRefit)
        refitCleanupRef.current = () => {
          debouncedRefit.cancel()
          if (!event.api.isDestroyed()) {
            event.api.removeEventListener(
              "displayedColumnsChanged",
              debouncedRefit
            )
          }
        }
        if (debug) {
          console.log(
            "[AgGridComponent] Registered displayedColumnsChanged refit"
          )
        }
      }

      // Column layout is restored pre-paint via the `initialState` prop (see
      // the `initialState` memo) — no post-paint applyColumnState here, which
      // is what caused the restore flicker. Row groups are re-affirmed as a
      // safety net: AG-Grid's `initialState.rowGroup` is reliable at creation,
      // but setRowGroupColumns guards against pivot-mode edge cases and is a
      // no-op when groups already match (it touches grouping only, so it can't
      // flash a value column).
      if (data.columns_state) {
        const rg = extractRowGroupColumnsFromState(data.columns_state)
        if (rg.length > 0) {
          event.api.setRowGroupColumns(rg)
        }

        // Merge mode applies its partial overlay post-creation (not via
        // initialState — see the initialState memo). colDefs have already set
        // up row groups / pivot / default aggregation at creation; this lays
        // the control's visibility on top without disturbing them.
        if (data.columns_state_mode === "merge") {
          event.api.applyColumnState({
            state: data.columns_state,
            applyOrder: false,
          })
        }
      }

      // Handle pre-selection
      const preSelectAllRows = data.gridOptions?.preSelectAllRows || false
      if (preSelectAllRows) {
        event.api.selectAll()
      } else {
        const preselectedRows = data.gridOptions?.preSelectedRows
        if (preselectedRows && preselectedRows.length > 0) {
          for (const rowId of preselectedRows) {
            event.api.getRowNode(rowId)?.setSelected(true, false)
          }
        }
      }

      // Fire original onGridReady if provided
      const { onGridReady: userOnGridReady } = gridOptions
      if (userOnGridReady) {
        userOnGridReady(event)
      }
    },
    [data.columns_state, data.columns_state_mode, data.gridOptions, gridOptions, debug]
  )

  const isAutoHeight = data.gridOptions?.domLayout === "autoHeight"

  const containerStyle = useMemo(() => {
    if (isAutoHeight) {
      return { width: "100%" }
    }
    return { width: "100%", height: data.height }
  }, [isAutoHeight, data.height])

  if (debug) {
    console.log("[AgGridComponent] Render with data:", data)
  }

  return (
    <div
      id="gridContainer"
      ref={gridContainerRef}
      style={containerStyle}
    >
      <GridToolBar
        enabled={data.show_toolbar ?? false}
        showSearch={data.show_search ?? true}
        showDownloadButton={data.show_download_button ?? true}
        showFind={data.show_find ?? false}
        onQuickSearchChange={(value) => {
          gridApiRef.current?.setGridOption("quickFilterText", value)
          gridApiRef.current?.hideOverlay()
        }}
        onFindChange={(value) => {
          gridApiRef.current?.setGridOption("findSearchValue", value)
        }}
        onFindNext={() => gridApiRef.current?.findNext()}
        onFindPrev={() => gridApiRef.current?.findPrevious()}
        findMatches={findState.matches}
        findActive={findState.active}
        onDownloadClick={() => {
          gridApiRef.current?.exportDataAsCsv()
        }}
      />
      <AgGridReact
        onGridReady={onGridReady}
        rowData={rowData}
        gridOptions={gridOptions}
        initialState={initialState}
      />
    </div>
  )
}

export default AgGridComponent
