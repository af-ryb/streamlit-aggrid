import type { Column, GridApi, IRowNode } from "ag-grid-community"
import { popStats, Stats } from "./normalize"
import type { PopulationScope } from "./schemes"

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

/** Whether a row's parent is the root — a top-level group, or a leaf of a
 * flat grid. Under `scope: "parent"` such rows are neither painted nor
 * counted: they *are* the groups, and comparing them across is what a
 * consumer choosing that scope is declining to do. */
export function isTopLevel(node: IRowNode): boolean {
  return !node.parent || node.parent.level < 0
}

/** The chain of group keys from `group` upward, stopping at the root, as one
 * string. Stable for the life of a model generation, unlike `node.id`, which
 * is not guaranteed to survive every rebuild; unambiguous because the keys
 * are JSON-encoded rather than joined on a separator a key could contain.
 * Group keys are unique among siblings and each level groups on one field,
 * so the chain identifies a parent exactly. */
function groupPath(group: IRowNode | null): string {
  const keys: (string | null)[] = []
  for (let p = group; p && p.level >= 0; p = p.parent) keys.push(p.key)
  return JSON.stringify(keys)
}

/** The cache-key half of a row's parent identity. The root's path is `[]`. */
export function parentPath(node: IRowNode): string {
  return groupPath(node.parent)
}

/** Per-grid statistics for the current model generation, keyed by column,
 * scope and skip rule. A `WeakMap` so a destroyed grid's entry goes with it. */
const statsCache = new WeakMap<GridApi, Map<string, Stats | null>>()

/** Drop everything cached for one grid. Called when the model changes. */
export function clearStats(api: GridApi): void {
  statsCache.delete(api)
}

function cacheFor(api: GridApi): Map<string, Stats | null> {
  let byKey = statsCache.get(api)
  if (!byKey) {
    byKey = new Map()
    statsCache.set(api, byKey)
  }
  return byKey
}

/**
 * The population statistics for one column in one scope, computed once per
 * model generation.
 *
 * `scope: "level"` — the 2.4.0 rule, on the 2.4.0 code: every row at the same
 * `node.level`. Deliberately level-scoped: a group row's aggregate and a
 * leaf's own value are not comparable quantities, and pooling them lets a
 * group total set the maximum and wash every leaf out.
 *
 * `scope: "parent"` — only the row's siblings under the same parent. A miss
 * runs one walk and fills the entry for *every* parent at once (see
 * `fillParentStats`), so a generation costs one pass per painted column in
 * either scope, not one pass per group.
 *
 * Values are read through `api.getCellValue` rather than
 * `row.data[colId]` / `row.aggData[colId]`: that resolves `field`,
 * `valueGetter` and pivot result columns the way the grid itself does, so a
 * column whose `colId` differs from its `field` is not silently blank.
 *
 * `skipNonPositive` *is* part of the cache key, even though it's fixed by
 * the resolved declaration for a given `colId` at any one instant: the
 * declaration is re-read per call (see `index.ts`'s `stColorScaleCellStyle`),
 * so within one grid's life the same `colId` can resolve to either skip rule
 * across a config-only rerun — a Streamlit rerun that flips
 * `skip_non_positive` on an existing column never changes `colId`. Keying on
 * `colId` alone would let the old rule's population survive under the new
 * one until some unrelated model change happened to clear the cache.
 */
export function statsFor(
  api: GridApi,
  column: Column,
  node: IRowNode,
  scope: PopulationScope,
  skipNonPositive: boolean
): Stats | null {
  const byKey = cacheFor(api)
  const colId = column.getColId()

  if (scope === "parent") {
    const key = `${colId}:P${parentPath(node)}:${skipNonPositive}`
    if (byKey.has(key)) return byKey.get(key) ?? null
    fillParentStats(api, column, colId, skipNonPositive, byKey)
    // A parent with no qualifying values got no entry from the walk. Memoise
    // the "no population" answer under the requested key so the next cell of
    // the same parent does not walk again.
    if (!byKey.has(key)) byKey.set(key, null)
    return byKey.get(key) ?? null
  }

  // `has`, not truthiness: `null` — "this column has no population at this
  // level" — is a stable answer for the generation and is memoised too.
  const level = node.level
  const key = `${colId}:${level}:${skipNonPositive}`
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

/** One pass over the model that buckets every qualifying row's value by its
 * parent and writes one `Stats` per parent into the cache. Top-level rows
 * (parent is the root) are skipped, per `isTopLevel`. */
function fillParentStats(
  api: GridApi,
  column: Column,
  colId: string,
  skipNonPositive: boolean,
  byKey: Map<string, Stats | null>
): void {
  const buckets = new Map<IRowNode, number[]>()
  api.forEachNodeAfterFilterAndSort((row: IRowNode) => {
    if (row.footer || row.rowPinned != null) return
    if (isTopLevel(row)) return
    const value = extractValue(api.getCellValue({ rowNode: row, colKey: column }))
    if (value === null) return
    if (skipNonPositive && value <= 0) return
    const parent = row.parent as IRowNode
    let values = buckets.get(parent)
    if (!values) {
      values = []
      buckets.set(parent, values)
    }
    values.push(value)
  })

  for (const [parent, values] of buckets) {
    byKey.set(`${colId}:P${groupPath(parent)}:${skipNonPositive}`, popStats(values))
  }
}
