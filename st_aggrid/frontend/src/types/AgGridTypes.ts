import { GridApi, GridOptions } from "ag-grid-community"

export interface AgGridData {
  gridOptions: any
  rowData: any[] | string | null
  height: number
  collect: string[]
  update_on: (string | [string, number])[]
  allow_unsafe_jscode: boolean
  enable_enterprise_modules: boolean | "enterpriseOnly" | "enterprise+AgCharts"
  license_key?: string
  columns_state?: any
  columns_state_mode?: "replace" | "merge"
  initial_state?: any
  theme: any
  custom_css?: { [key: string]: { [key: string]: string } }
  show_toolbar: boolean
  show_search: boolean
  show_download_button: boolean
  show_find: boolean
  notes?: { [rowId: string]: { [colId: string]: any } } | null
  notes_editable?: boolean
  notes_groups?: NotesGroupRule[] | null
  debug_group_notes?: boolean
  api_call?: ApiCallRequest | null
  pro_assets?: { js?: string; css?: string }[]
  debug?: boolean
}

// A group-dimension Notes rule (AG-Grid 35.3 Enterprise): a note is a predicate
// over a group row's dimension ancestry. `match` is a {field: value} subset that
// must hold on the row (every field must be an active row group); `note` is the
// shown text (or a Note object). Matched on the boundary row; the most-specific
// (most fields) rule wins on a shared row. See REQUIREMENT-group-dimension-notes.md.
export interface NotesGroupRule {
  match: { [field: string]: string | number }
  note: string | { text: string; [key: string]: any }
}

export interface StreamlitThemeInfo {
  primaryColor: string
  textColor: string
  backgroundColor: string
  secondaryBackgroundColor: string
  font: string
  base: "light" | "dark"
}

export interface ApiCallRequest {
  method: string
  params?: any
  call_id: string
}

export interface ApiCallResponse {
  call_id: string
  result?: any
  error?: string
}

export interface GridStateResult {
  eventName: string
  eventData?: any
  [key: string]: any
}
