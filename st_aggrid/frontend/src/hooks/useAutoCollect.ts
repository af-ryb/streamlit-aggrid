import { useEffect, useRef, useCallback } from "react"
import { GridApi } from "ag-grid-community"
import debounce from "lodash/debounce"
import type { GridStateResult } from "../types/AgGridTypes"

/**
 * Events served as lifecycle callbacks bound at grid creation, not as
 * subscriptions. AG-Grid emits each at most once per grid instance, and
 * `gridReady` is the event that makes subscription possible in the first
 * place, so a listener attached from the effect below is either dead
 * (`gridReady`) or a duplicate on top of the callback (`firstDataRendered`,
 * whose dispatch is queued into requestAnimationFrame and so loses to a React
 * effect committed in the same tick — this was measured, not assumed).
 *
 * `AgGridComponent` imports this set, and `LIFECYCLE_UPDATE_ON_EVENTS` in
 * `st_aggrid/aggrid.py` mirrors it. All three must agree.
 */
export const LIFECYCLE_EVENTS: ReadonlySet<string> = new Set([
  "gridReady",
  "firstDataRendered",
])

/**
 * Run one auto-collect under `eventName` and post the result to the host.
 *
 * `api` overrides the hook's own grid API. That is what lets a grid-creation
 * callback collect while the `gridApi` state it is about to set is still null,
 * which is exactly where the naive fix for lifecycle triggers fails.
 *
 * A synthetic caller must not pass an `eventData` whose `source` starts with
 * `api`, or equals `sizeColumnsToFit`, `flex` or `autosizeColumns` — the
 * collector drops those as programmatic. Correct for real AG-Grid events, a
 * trap for a synthetic one: passing such a `source` silently discards the
 * collect.
 */
export type CollectNow = (
  eventName: string,
  eventData: any,
  api?: GridApi
) => void

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
}: UseAutoCollectOptions): CollectNow {
  const cleanupRef = useRef<(() => void)[]>([])
  // Live grid API, read at call time so `collectNow` stays referentially
  // stable across the null -> api transition. Assigned during render, the
  // same way `AgGridComponent` maintains `notesEditableRef`.
  const apiRef = useRef<GridApi | null>(null)
  apiRef.current = gridApi

  const collectNow = useCallback<CollectNow>(
    (eventName, eventData, api) => {
      const target = api ?? apiRef.current
      if (!target || target.isDestroyed()) return

      // Skip programmatic (api-sourced) column events. Applying saved column
      // state on mount/restore (initialState + onGridReady setRowGroupColumns
      // + the columns_state re-apply effect) fires AG-Grid events with
      // source="api"/"apiNoSortChange". Echoing those back via setStateValue
      // triggers a Streamlit fragment rerun (and a restore->capture->re-apply
      // loop / column flicker). Only user actions should sync state — this
      // mirrors dash_app's is_programmatic_grid_event, moved upstream so the
      // rerun is never triggered, not merely the capture suppressed.
      //
      // Also skip sizing-driven sources: the fitGridWidth refit listener calls
      // sizeColumnsToFit() on displayedColumnsChanged, which emits a
      // columnResized with source="sizeColumnsToFit" (likewise "flex" /
      // "autosizeColumns"). Capturing those would persist the auto-fit widths
      // as if the user set them and fire a needless rerun.
      //
      // Neither GridReadyEvent nor FirstDataRenderedEvent carries a `source`,
      // so both pass this filter. That is deliberate: nothing about a
      // lifecycle trigger is programmatic in the sense meant here.
      const source = eventData?.source
      const isProgrammatic =
        typeof source === "string" &&
        (source.startsWith("api") ||
          source === "sizeColumnsToFit" ||
          source === "flex" ||
          source === "autosizeColumns")
      if (isProgrammatic) {
        if (debug) {
          console.log(`[useAutoCollect] Skipping programmatic "${eventName}" (source=${source})`)
        }
        return
      }

      const result: GridStateResult = {
        eventName,
        eventData: serializeEventData(eventData),
      }

      for (const method of collectConfig) {
        try {
          const fn = (target as any)[method]
          if (typeof fn === "function") {
            const value = fn.call(target)
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
    [collectConfig, setStateValue, debug]
  )

  useEffect(() => {
    if (!gridApi) return

    // Clean up previous listeners
    cleanupRef.current.forEach((fn) => fn())
    cleanupRef.current = []

    for (const entry of updateOn) {
      const name = Array.isArray(entry) ? entry[0] : entry

      // Served by AgGridComponent as a grid-creation callback. A listener here
      // would never fire (gridReady) or would fire on top of the callback
      // (firstDataRendered) — one collect turning into two.
      if (LIFECYCLE_EVENTS.has(name)) {
        if (debug) {
          console.log(
            `[useAutoCollect] Lifecycle trigger, no listener: ${name}`
          )
        }
        continue
      }

      if (Array.isArray(entry)) {
        const [eventName, timeout] = entry
        const debouncedHandler = debounce(
          (e: any) => collectNow(eventName, e),
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
        const handler = (e: any) => collectNow(entry, e)
        ;(gridApi as any).addEventListener(entry, handler)
        cleanupRef.current.push(() => {
          if (!gridApi.isDestroyed()) {
            ;(gridApi as any).removeEventListener(entry, handler)
          }
        })
      }

      if (debug) {
        console.log(`[useAutoCollect] Attached listener: ${name}`)
      }
    }

    return () => {
      cleanupRef.current.forEach((fn) => fn())
      cleanupRef.current = []
    }
  }, [gridApi, updateOn, collectNow, debug])

  return collectNow
}
