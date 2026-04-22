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

import { useAutoCollect } from "./hooks/useAutoCollect"
import { useExplicitApiCall } from "./hooks/useExplicitApiCall"

import GridToolBar from "./components/GridToolBar"

import {
  addCustomCSS,
  extractColumnStateFromDefs,
  extractRowGroupColumns,
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

// Track whether custom CSS has been injected
let cssInjected = false
let proAssetsInjected = false

const AgGridComponent: React.FC<AgGridComponentProps> = ({
  data,
  setStateValue,
  setTriggerValue,
}) => {
  // Grid API is held both as a ref (for imperative calls from callbacks and
  // effects that don't need to re-run on mount) and as state (so hooks like
  // `useAutoCollect` that attach event listeners re-run once the grid signals
  // readiness, not just on the next Streamlit-driven re-render).
  const gridApiRef = useRef<GridApi | null>(null)
  const [gridApi, setGridApi] = useState<GridApi | null>(null)
  const gridContainerRef = useRef<HTMLDivElement>(null)
  const prevDataRef = useRef<AgGridData | undefined>(undefined)

  const debug = data.debug || false

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

  // Grid options WITHOUT rowData — recomputed only when config inputs change.
  const gridOptions = useMemo(() => {
    const go = parseGridOptions(data)
    // Defensive: strip any rowData that may have been carried over so the
    // separate <AgGridReact rowData> prop is the single source of truth.
    delete (go as any).rowData

    // Honor user-provided getRowId; fall back to the auto_unique_id marker.
    if (!("getRowId" in go) && autoGetRowId) {
      go.getRowId = autoGetRowId
    }

    return go
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data.gridOptions, data.theme, data.streamlit_theme, data.allow_unsafe_jscode, autoGetRowId])

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

      // updateGridOptions swaps columnDefs in place but doesn't re-render
      // already-painted cells, so property changes such as cellStyle /
      // cellClass / cellRenderer won't clear stale inline styles. Redraw
      // rows to guarantee the DOM reflects the new configuration.
      gridApiRef.current.redrawRows()
    }

    // Diff columns_state
    if (!isEqual(prevData.columns_state, data.columns_state)) {
      if (data.columns_state != null) {
        gridApiRef.current.applyColumnState({
          state: data.columns_state,
          applyOrder: true,
        })
      }
    }
  }, [data])

  const onGridReady = useCallback(
    (event: GridReadyEvent) => {
      gridApiRef.current = event.api
      setGridApi(event.api)

      if (debug) {
        console.log("[AgGridComponent] Grid ready", event)
      }

      // Apply initial columns state
      if (data.columns_state) {
        event.api.applyColumnState({
          state: data.columns_state,
          applyOrder: true,
        })
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
    [data.columns_state, data.gridOptions, gridOptions, debug]
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
        onQuickSearchChange={(value) => {
          gridApiRef.current?.setGridOption("quickFilterText", value)
          gridApiRef.current?.hideOverlay()
        }}
        onDownloadClick={() => {
          gridApiRef.current?.exportDataAsCsv()
        }}
      />
      <AgGridReact
        onGridReady={onGridReady}
        rowData={rowData}
        gridOptions={gridOptions}
      />
    </div>
  )
}

export default AgGridComponent
