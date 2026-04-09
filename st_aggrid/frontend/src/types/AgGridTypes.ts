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
  theme: any
  streamlit_theme?: StreamlitThemeInfo
  custom_css?: { [key: string]: { [key: string]: string } }
  show_toolbar: boolean
  show_search: boolean
  show_download_button: boolean
  api_call?: ApiCallRequest | null
  pro_assets?: { js?: string; css?: string }[]
  debug?: boolean
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
