import type { Column, GridApi, IRowNode } from "ag-grid-community"
import { popStats, Stats } from "./normalize"

/** The number behind a cell, whatever wrapper it arrives in.
 *
 * A strict superset of `foldSums.ts`'s private `sortValue`, and deliberately a
 * separate function: widening `sortValue` to also unwrap `.value` and the
 * legacy `{numerator, denominator}` shape would change the **sort order** of
 * any column carrying that shape, which is a separate decision and not a side
 * effect of adding colour.
 */
export function extractValue(raw: unknown): number | null {
  if (raw === null || raw === undefined || raw === "") return null

  if (typeof raw === "object") {
    const object = raw as Record<string, any>
    if (typeof object.toNumber === "function") return finite(object.toNumber())
    if (object.value !== undefined) return finite(object.value)
    if (object.numerator !== undefined && object.denominator !== undefined) {
      return object.denominator > 0
        ? finite(object.numerator / object.denominator)
        : null
    }
    return null
  }

  return typeof raw === "number" ? finite(raw) : null
}

function finite(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null
}

/** Per-grid, per-`colId:level` statistics for the current model generation.
 * A `WeakMap` so a destroyed grid's entry goes with it. */
const statsCache = new WeakMap<GridApi, Map<string, Stats | null>>()

/** Drop everything cached for one grid. Called when the model changes. */
export function clearStats(api: GridApi): void {
  statsCache.delete(api)
}

/**
 * The population statistics for one column at one group level, computed once
 * per model generation.
 *
 * The population is deliberately level-scoped: a group row's aggregate and a
 * leaf's own value are not comparable quantities, and pooling them lets a
 * group total set the maximum and wash every leaf out — which is what the
 * summed columns of the styler this replaces do today.
 *
 * Values are read through `api.getCellValue` rather than
 * `row.data[colId]` / `row.aggData[colId]`: that resolves `field`,
 * `valueGetter` and pivot result columns the way the grid itself does, so a
 * column whose `colId` differs from its `field` is not silently blank.
 *
 * `skipNonPositive` is not part of the cache key. It is fixed per column by
 * the resolved declaration, so `colId` already implies it.
 */
export function statsFor(
  api: GridApi,
  column: Column,
  level: number,
  skipNonPositive: boolean
): Stats | null {
  let byKey = statsCache.get(api)
  if (!byKey) {
    byKey = new Map()
    statsCache.set(api, byKey)
  }

  // `has`, not truthiness: `null` — "this column has no population at this
  // level" — is a stable answer for the generation and is memoised too.
  const key = `${column.getColId()}:${level}`
  if (byKey.has(key)) return byKey.get(key) ?? null

  const values: number[] = []
  api.forEachNodeAfterFilterAndSort((row: IRowNode) => {
    // The grand total is a window-wide aggregate, not a comparable row:
    // neither painted nor scanned. Same for a pinned row.
    if (row.footer || row.rowPinned != null) return
    if (row.level !== level) return
    const value = extractValue(api.getCellValue({ rowNode: row, colKey: column }))
    if (value === null) return
    if (skipNonPositive && value <= 0) return
    values.push(value)
  })

  const stats = values.length ? popStats(values) : null
  byKey.set(key, stats)
  return stats
}
