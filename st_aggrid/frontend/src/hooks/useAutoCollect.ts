import { useEffect, useRef, useCallback } from "react"
import { GridApi } from "ag-grid-community"
import debounce from "lodash/debounce"
import type { GridStateResult } from "../types/AgGridTypes"

/**
 * Convert AG-Grid API method names to friendly result keys.
 * "getSelectedRows" -> "selectedRows", "getFilterModel" -> "filterModel"
 */
function toKey(method: string): string {
  if (method.startsWith("get")) {
    return method.charAt(3).toLowerCase() + method.slice(4)
  }
  return method
}

/**
 * Safely serialize event data, stripping non-serializable values.
 * Limits depth to avoid circular references.
 */
function serializeEventData(eventData: any, maxDepth = 2): any {
  if (maxDepth <= 0 || eventData == null) return null

  if (typeof eventData !== "object") {
    if (typeof eventData === "function" || typeof eventData === "symbol") {
      return undefined
    }
    return eventData
  }

  if (Array.isArray(eventData)) {
    return eventData.map((item) => serializeEventData(item, maxDepth - 1))
  }

  const result: any = {}
  for (const key of Object.keys(eventData)) {
    const val = eventData[key]
    if (typeof val === "function" || typeof val === "symbol") continue
    if (val instanceof HTMLElement) continue
    result[key] = serializeEventData(val, maxDepth - 1)
  }
  return result
}

interface UseAutoCollectOptions {
  gridApi: GridApi | null
  collectConfig: string[]
  updateOn: (string | [string, number])[]
  setStateValue: (key: string, value: any) => void
  debug: boolean
}

export function useAutoCollect({
  gridApi,
  collectConfig,
  updateOn,
  setStateValue,
  debug,
}: UseAutoCollectOptions) {
  const cleanupRef = useRef<(() => void)[]>([])

  const collectAndSend = useCallback(
    (eventName: string, eventData: any) => {
      if (!gridApi) return

      const result: GridStateResult = {
        eventName,
        eventData: serializeEventData(eventData),
      }

      for (const method of collectConfig) {
        try {
          const fn = (gridApi as any)[method]
          if (typeof fn === "function") {
            const value = fn.call(gridApi)
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
    [gridApi, collectConfig, setStateValue, debug]
  )

  useEffect(() => {
    if (!gridApi) return

    // Clean up previous listeners
    cleanupRef.current.forEach((fn) => fn())
    cleanupRef.current = []

    for (const entry of updateOn) {
      if (Array.isArray(entry)) {
        const [eventName, timeout] = entry
        const debouncedHandler = debounce(
          (e: any) => collectAndSend(eventName, e),
          timeout,
          { leading: false, trailing: true, maxWait: timeout }
        )
        ;(gridApi as any).addEventListener(eventName, debouncedHandler)
        cleanupRef.current.push(() => {
          debouncedHandler.cancel()
          if (!gridApi.isDestroyed()) {
            ;(gridApi as any).removeEventListener(eventName, debouncedHandler)
          }
        })
      } else {
        const handler = (e: any) => collectAndSend(entry, e)
        ;(gridApi as any).addEventListener(entry, handler)
        cleanupRef.current.push(() => {
          if (!gridApi.isDestroyed()) {
            ;(gridApi as any).removeEventListener(entry, handler)
          }
        })
      }

      if (debug) {
        console.log(`[useAutoCollect] Attached listener: ${entry}`)
      }
    }

    return () => {
      cleanupRef.current.forEach((fn) => fn())
      cleanupRef.current = []
    }
  }, [gridApi, updateOn, collectAndSend, debug])
}
