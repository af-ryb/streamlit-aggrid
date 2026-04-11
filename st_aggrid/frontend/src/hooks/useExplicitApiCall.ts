import { useEffect, useRef } from "react"
import { GridApi } from "ag-grid-community"
import type { ApiCallRequest, ApiCallResponse } from "../types/AgGridTypes"

interface UseExplicitApiCallOptions {
  gridApi: GridApi | null
  apiCallRequest: ApiCallRequest | null | undefined
  setTriggerValue: (key: string, value: any) => void
  debug: boolean
}

export function useExplicitApiCall({
  gridApi,
  apiCallRequest,
  setTriggerValue,
  debug,
}: UseExplicitApiCallOptions) {
  const lastCallIdRef = useRef<string | null>(null)

  useEffect(() => {
    if (!gridApi || !apiCallRequest) return
    if (apiCallRequest.call_id === lastCallIdRef.current) return

    lastCallIdRef.current = apiCallRequest.call_id

    const { method, params, call_id } = apiCallRequest

    if (debug) {
      console.log(`[useExplicitApiCall] Executing: ${method}`, params)
    }

    try {
      const fn = (gridApi as any)[method]
      if (typeof fn !== "function") {
        const response: ApiCallResponse = {
          call_id,
          error: `AG-Grid API method "${method}" not found`,
        }
        setTriggerValue("api_response", response)
        return
      }

      const result = fn.call(gridApi, params ?? undefined)

      // Handle both sync and async results
      if (result && typeof result.then === "function") {
        result
          .then((asyncResult: any) => {
            const response: ApiCallResponse = {
              call_id,
              result: asyncResult,
            }
            setTriggerValue("api_response", response)
          })
          .catch((err: any) => {
            const response: ApiCallResponse = {
              call_id,
              error: String(err),
            }
            setTriggerValue("api_response", response)
          })
      } else {
        const response: ApiCallResponse = { call_id, result }
        setTriggerValue("api_response", response)
      }
    } catch (err) {
      if (debug) {
        console.error(`[useExplicitApiCall] Error:`, err)
      }
      const response: ApiCallResponse = {
        call_id,
        error: String(err),
      }
      setTriggerValue("api_response", response)
    }
  }, [gridApi, apiCallRequest, setTriggerValue, debug])
}
