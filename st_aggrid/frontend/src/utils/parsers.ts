import { GridOptions } from "ag-grid-community"
import { cloneDeep } from "lodash"
import { deepMap } from "../utils"
import { parseJsCodeFromPython } from "./gridUtils"
import { columnFormaters } from "../customColumns"
import { ThemeParser } from "../ThemeParser"
import type { AgGridData } from "../types/AgGridTypes"

export function parseGridOptions(data: AgGridData): GridOptions {
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

  // Process theming
  const themeParser = new ThemeParser()
  gridOptions.theme = themeParser.parse(data.theme, data.streamlit_theme)

  return gridOptions
}

export function parseData(data: AgGridData): any[] {
  const rawData = (data as any).rowData
  const gridOptionsRowData = data.gridOptions?.rowData

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
  if (rawData && rawData.schema && rawData.batches) {
    let indexColumns: string[] = []
    try {
      const pandasMeta = JSON.parse(
        rawData.schema?.metadata?.get("pandas") || "{}"
      )
      indexColumns = pandasMeta.index_columns || []
    } catch (e) {}

    const dataFields =
      rawData.schema?.fields
        ?.map((f: any) => f.name)
        .filter((name: string) => !indexColumns.includes(name)) || []

    const filteredTable = rawData.select(dataFields)
    return JSON.parse(JSON.stringify(filteredTable.toArray(), bigintReplacer))
  }

  // Fallback: rowData as JSON string
  if (rawData && typeof rawData === "string") {
    try {
      return JSON.parse(rawData)
    } catch (e) {
      console.error("Failed to parse rowData as JSON:", e)
      return []
    }
  }

  // Fallback: rowData as plain array
  if (Array.isArray(rawData)) return rawData

  // Fallback: gridOptions.rowData as JSON string
  if (gridOptionsRowData && typeof gridOptionsRowData === "string") {
    try {
      return JSON.parse(gridOptionsRowData)
    } catch (e) {
      console.error("Failed to parse gridOptions.rowData as JSON:", e)
      return []
    }
  }

  return []
}
