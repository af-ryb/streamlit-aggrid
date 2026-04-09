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
  const rawData = (data as any).data
  const gridOptionsRowData = data.gridOptions?.rowData
  let rowData: any[] = []

  if (rawData) {
    // Quick fix for bigInt serializations
    const bigintReplacer = (key: any, value: any): any => {
      if (typeof value === "bigint") {
        return Number(value)
      }
      if (Array.isArray(value)) {
        return value.map((item: any) => bigintReplacer(null, item))
      }
      if (value && typeof value === "object") {
        const replacedObj: any = {}
        for (const prop in value) {
          if (Object.prototype.hasOwnProperty.call(value, prop)) {
            replacedObj[prop] = bigintReplacer(prop, value[prop])
          }
        }
        return replacedObj
      }
      return value
    }

    const arrowTable = rawData.dataTable || rawData.table

    if (arrowTable) {
      // Extract index column names from pandas metadata
      let indexColumns: string[] = []
      try {
        const pandasMeta = JSON.parse(
          arrowTable?.schema?.metadata?.get("pandas") || "{}"
        )
        indexColumns = pandasMeta.index_columns || []
      } catch (e) {}

      // Filter out index columns and select only data fields
      const dataFields =
        arrowTable?.schema?.fields
          ?.map((f: any) => f.name)
          .filter((name: string) => !indexColumns.includes(name)) || []

      const filteredTable = arrowTable.select(dataFields)
      rowData = JSON.parse(
        JSON.stringify(filteredTable.toArray(), bigintReplacer)
      )
    }
  } else if (data.rowData) {
    // rowData passed directly (e.g. as JSON string from Python)
    if (typeof data.rowData === "string") {
      try {
        rowData = JSON.parse(data.rowData)
      } catch (e) {
        console.error("Failed to parse rowData as JSON:", e)
        throw e
      }
    } else if (Array.isArray(data.rowData)) {
      rowData = data.rowData
    }
  } else if (gridOptionsRowData && typeof gridOptionsRowData === "string") {
    try {
      rowData = JSON.parse(gridOptionsRowData)
    } catch (e) {
      console.error("Failed to parse gridOptions.rowData as JSON:", e)
      throw e
    }
  }

  return rowData
}
