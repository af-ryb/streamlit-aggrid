import React from "react"
import { createRoot, Root } from "react-dom/client"
import type { FrontendRenderer } from "@streamlit/component-v2-lib"
import AgGridComponent from "./AgGridComponent"
import ErrorBoundary from "./components/ErrorBoundary"
import type { AgGridData } from "./types/AgGridTypes"

const rootMap = new Map<string, { root: Root; container: HTMLElement }>()

const render: FrontendRenderer = ({
  data: rawData,
  key,
  setStateValue,
  setTriggerValue,
  parentElement,
}) => {
  const data = rawData as AgGridData
  let entry = rootMap.get(key)
  if (!entry) {
    const container = document.createElement("div")
    container.className = "st-aggrid-scope"
    parentElement.appendChild(container)
    const root = createRoot(container)
    entry = { root, container }
    rootMap.set(key, entry)
  } else if (!parentElement.contains(entry.container)) {
    parentElement.appendChild(entry.container)
  }

  entry.root.render(
    <ErrorBoundary>
      <AgGridComponent
        data={data}
        setStateValue={setStateValue}
        setTriggerValue={setTriggerValue}
      />
    </ErrorBoundary>
  )

  return () => {
    entry!.root.unmount()
    entry!.container.remove()
    rootMap.delete(key)
  }
}

export default render
