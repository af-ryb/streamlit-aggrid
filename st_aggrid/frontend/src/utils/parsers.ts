import { GridOptions } from "ag-grid-community"
import { cloneDeep } from "lodash"
import { deepMap } from "../utils"
import { parseJsCodeFromPython } from "./gridUtils"
import { columnFormaters } from "../customColumns"
import { ThemeParser } from "../ThemeParser"
import type { AgGridData, StreamlitThemeInfo } from "../types/AgGridTypes"
import { registerStRatio } from "../aggFuncs/stRatio"
import { registerStRatioOfRatios } from "../aggFuncs/stRatioOfRatios"
import { registerStWeightedAvg } from "../aggFuncs/stWeightedAvg"
import { registerStRollup, ST_ROLLUP_INDEX } from "../aggFuncs/stRollup"
import type { RollupHolder } from "../aggFuncs/stRollup"
import {
  ColorScaleRuntime,
  ST_COLOR_SCALE_OVERRIDES,
  isInteractive,
  registerColorScales,
} from "../colorScales"
import { registerColorScaleMenu } from "../colorScales/menu"

export function parseGridOptions(
  data: AgGridData,
  streamlitTheme?: StreamlitThemeInfo | null,
  colorScaleRuntime?: ColorScaleRuntime,
  rollupHolder?: RollupHolder
): GridOptions {
  let gridOptions: GridOptions = cloneDeep(data.gridOptions)

  if (data.allow_unsafe_jscode) {
    console.warn("flag allow_unsafe_jscode is on.")
    gridOptions = deepMap(gridOptions, parseJsCodeFromPython, ["rowData"])
  }

  if (!("getRowId" in gridOptions)) {
    console.warn(
      "getRowId was not set. Auto Rows hashes will be used as row ids."
    )
  }

  // Add custom column formatters
  gridOptions.columnTypes = Object.assign(
    gridOptions.columnTypes || {},
    columnFormaters
  )

  // Built-in aggregators. A caller-supplied `aggFuncs` entry of the same name
  // wins — see registerStRatio. Called from the one site both the mount path
  // (initial `gridOptions` memo) and the live-update path (`updateGridOptions`
  // effect) share, so a runtime config change never leaves either aggregator
  // unregistered.
  registerStRatio(gridOptions, data.debug === true)
  registerStRatioOfRatios(gridOptions, data.debug === true)
  registerStWeightedAvg(gridOptions, data.debug === true)
  registerStRollup(gridOptions, data.debug === true)

  // The server's totals for `stRollup`. The same holder on every parse — mount
  // and each live update — so a new table swaps `holder.index` without a
  // context change AG-Grid would ignore anyway (see AgGridComponent).
  if (rollupHolder) {
    gridOptions.context = {
      ...(gridOptions.context ?? {}),
      [ST_ROLLUP_INDEX]: rollupHolder,
    }
  }

  // Built-in colour scales. Same site as the aggregators above for the same
  // reason: both the mount path and the live-update path go through here, so a
  // runtime config change never leaves a declared column unpainted.
  registerColorScales(gridOptions, data.debug === true)

  // The reader's choices. Injected after the `cloneDeep` above, so every parse
  // — the mount and each live config update — hands AG-Grid a fresh `context`
  // object carrying the *same* map. That is what lets a choice survive
  // `updateGridOptions`, and being in `context` before the first cell is
  // styled is what lets a restored choice paint with no unpainted flash.
  // `context` is known to be an object here: `isInteractive` read it.
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

  // Process theming — prefer the live theme read from host CSS variables
  // over any server-side value, which can't see user-level theme toggles.
  const themeParser = new ThemeParser()
  gridOptions.theme = themeParser.parse(
    data.theme,
    streamlitTheme ?? undefined
  )

  return gridOptions
}

/** Rows from any shape a frame arrives in: a bare Arrow table (CCv2), a JSON
 * string (the `to_json` fallback), or a plain array. Shared by `rowData` and
 * `rollup_data`, so both reach the same JS values by the same code — what
 * lets a `stRollup` key match a group key at all. */
export function parseRows(raw: any): any[] {
  const bigintReplacer = (key: any, value: any): any => {
    if (typeof value === "bigint") return Number(value)
    if (Array.isArray(value))
      return value.map((item: any) => bigintReplacer(null, item))
    if (value && typeof value === "object") {
      const obj: any = {}
      for (const prop in value) {
        if (Object.prototype.hasOwnProperty.call(value, prop))
          obj[prop] = bigintReplacer(prop, value[prop])
      }
      return obj
    }
    return value
  }

  // CCv2: DataFrame arrives as a bare Arrow Table (schema, batches, _offsets)
  if (raw && raw.schema && raw.batches) {
    let indexColumns: string[] = []
    try {
      const pandasMeta = JSON.parse(raw.schema?.metadata?.get("pandas") || "{}")
      indexColumns = pandasMeta.index_columns || []
    } catch (e) {}

    const dataFields =
      raw.schema?.fields
        ?.map((f: any) => f.name)
        .filter((name: string) => !indexColumns.includes(name)) || []

    const filteredTable = raw.select(dataFields)
    return JSON.parse(JSON.stringify(filteredTable.toArray(), bigintReplacer))
  }

  if (raw && typeof raw === "string") {
    try {
      return JSON.parse(raw)
    } catch (e) {
      console.error("Failed to parse rows as JSON:", e)
      return []
    }
  }

  if (Array.isArray(raw)) return raw

  return []
}

export function parseData(data: AgGridData): any[] {
  const rawData = (data as any).rowData
  if (
    (rawData && (typeof rawData === "string" || (rawData.schema && rawData.batches))) ||
    Array.isArray(rawData)
  ) {
    return parseRows(rawData)
  }

  // Fallback: gridOptions.rowData as JSON string
  const gridOptionsRowData = data.gridOptions?.rowData
  if (gridOptionsRowData && typeof gridOptionsRowData === "string") {
    return parseRows(gridOptionsRowData)
  }

  return []
}
