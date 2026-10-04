import type { GridOptions, IAggFuncParams } from "ag-grid-community"
import { eachColDef, registerAggFunc } from "./foldSums"
import { canonicalKey, nodeKey, toGroupKey } from "./rollupKey"
import type { KeyNode } from "./rollupKey"

/** Name callers reference from `colDef.aggFunc`, and the key of a column's
 * optional `context["stRollup"] = {field}` declaration. */
export const ST_ROLLUP = "stRollup"

/** The grid `context` key the per-mount holder lives under. */
export const ST_ROLLUP_INDEX = "stRollup"

/** `component_data["rollup_meta"]`: defaults already filled in by Python. */
export interface RollupMeta {
  dimensions: string[]
  flags: Record<string, string>
}

export interface RollupIndex {
  map: Map<string, Record<string, unknown>>
  dimensions: Set<string>
  /** A few table keys, quoted in the desync warning. */
  sampleKeys: string[]
}

/**
 * One per mount, injected into every `context` `parseGridOptions` builds — the
 * colour-scale override `Map`'s pattern. A new totals table replaces `index`
 * in place, so it never needs `setGridOption("context")`, and the flags below
 * outlive the index rebuilds a theme or config change causes.
 */
export interface RollupHolder {
  index: RollupIndex | null
  debug: boolean
  /** The desync warning fired for the current table (reset on a new one). */
  warned: boolean
  notedPivot: boolean
}

/**
 * Index the totals by `canonicalKey`. A row's key is its present dimensions
 * (flag 0) only, each converted exactly as AG-Grid keys a group — including
 * the dimension column's own `keyCreator` (called with value, colDef, data
 * and context; one that needs a node cannot be reproduced for a totals row).
 */
export function buildRollupIndex(
  rows: Record<string, unknown>[],
  meta: RollupMeta | null | undefined,
  columnDefs: unknown,
  context?: unknown
): RollupIndex | null {
  if (!meta || !Array.isArray(meta.dimensions)) return null

  const keyCreators = new Map<string, (params: Record<string, unknown>) => unknown>()
  const colDefsByField = new Map<string, unknown>()
  eachColDef(columnDefs as any, (def) => {
    if (!def.field) return
    colDefsByField.set(def.field, def)
    if (typeof def.keyCreator === "function") keyCreators.set(def.field, def.keyCreator as any)
  })

  // A creator that reads `params.node`, `params.api` or `params.column` throws
  // here (a totals row has none of them). That row is skipped — it then misses
  // — and the first throw per call is named, not swallowed.
  let warnedCreator = false

  const map = new Map<string, Record<string, unknown>>()
  rows: for (const row of rows) {
    const pairs: Record<string, string> = {}
    for (const dimension of meta.dimensions) {
      if (Number(row[meta.flags[dimension]]) !== 0) continue
      const creator = keyCreators.get(dimension)
      try {
        pairs[dimension] = toGroupKey(
          row[dimension],
          creator
            ? (value) =>
                creator({ value, colDef: colDefsByField.get(dimension), data: row, context })
            : null
        )
      } catch (error) {
        if (!warnedCreator) {
          warnedCreator = true
          console.warn(
            `[st_aggrid] stRollup: the keyCreator of dimension "${dimension}" threw on a ` +
              `totals row (${String(error)}). It is called with value, colDef, data and ` +
              `context only — no node, api or column — so rows it cannot key are skipped ` +
              `and their groups show no total.`
          )
        }
        continue rows
      }
    }
    map.set(canonicalKey(pairs), row)
  }

  return {
    map,
    dimensions: new Set(meta.dimensions),
    sampleKeys: Array.from(map.keys()).slice(0, 3),
  }
}

/** A number, or `null` for anything that is not a finite one (a server NULL
 * arrives as `null` or `NaN`). A numeric string counts; an empty one does not. */
function finiteOrNull(raw: unknown): number | null {
  if (typeof raw === "string" && raw.trim() === "") return null
  const value = typeof raw === "string" ? Number(raw) : raw
  return typeof value === "number" && Number.isFinite(value) ? value : null
}

function valueField(colDef: IAggFuncParams["colDef"]): string | undefined {
  const config = (colDef?.context as Record<string, any> | undefined)?.[ST_ROLLUP]
  return (config && typeof config.field === "string" && config.field) || colDef?.field
}

/** The part of a `RowNode` the filter rule reads. */
interface FilterNode {
  group?: boolean
  childrenAfterFilter?: FilterNode[] | null
  allLeafChildren?: unknown[] | null
}

/** Leaves under `node` that passed the filter. Counted here, not read from
 * `allChildrenCount`: AG-Grid sets that in `filter_aggregates`, which runs
 * *after* aggregation, so during an aggFunc call it holds the previous pass's
 * count. `O(subtree)` per group. */
function filteredLeafCount(node: FilterNode): number {
  let count = 0
  for (const child of node.childrenAfterFilter ?? []) {
    count += child.group ? filteredLeafCount(child) : 1
  }
  return count
}

/** True when AG-Grid aggregates only the filtered children — its own
 * `filteredOnly` condition. With `suppressAggFilteredOnly` (or
 * `groupAggFiltering`) the grid aggregates every leaf, and the server total
 * agrees with that. */
function aggregatesFilteredOnly(params: IAggFuncParams): boolean {
  return (
    !params.api.getGridOption("groupAggFiltering") &&
    !params.api.getGridOption("suppressAggFilteredOnly")
  )
}

/**
 * A group row's total from the server's table — never computed from the
 * children. `null` (an empty cell) in pivot mode, without a table, when the
 * key is not in the table, or when a grid filter removed a leaf beneath the
 * group. Leaves never reach here: AG-Grid shows their own value.
 */
export function stRollupAggFunc(params: IAggFuncParams): number | null {
  const holder = (params.context as Record<string, unknown> | undefined)?.[
    ST_ROLLUP_INDEX
  ] as RollupHolder | undefined

  if (params.api.isPivotMode()) {
    if (holder?.debug && !holder.notedPivot) {
      holder.notedPivot = true
      console.log("[st_aggrid] stRollup: pivot mode is not supported; totals are empty.")
    }
    return null
  }

  // No holder: this grid got no `rollup` (e.g. `stRollup` arrived from restored
  // state). Empty, not a sum — a sum is the error this aggregator exists for.
  if (!holder?.index) return null
  const index = holder.index

  // A server total covers every leaf of the group. If a grid filter removed
  // one, the total no longer describes the visible rows: empty, not wrong.
  const filterNode = params.rowNode as unknown as FilterNode
  if (
    params.api.isAnyFilterPresent() &&
    aggregatesFilteredOnly(params) &&
    filteredLeafCount(filterNode) < (filterNode.allLeafChildren?.length ?? 0)
  ) {
    return null
  }

  const node = params.rowNode as unknown as KeyNode
  const pairs = nodeKey(node)
  const row = index.map.get(canonicalKey(pairs))
  if (row) return finiteOrNull(row[valueField(params.colDef) ?? ""])

  // `CUBE` returns every subset of the dimensions for every value combination
  // the leaves carry, so a miss whose fields are all dimensions is a desync —
  // serialisation, a stale table, flags lost upstream — not a missing total.
  if (!holder.warned && Object.keys(pairs).every((field) => index.dimensions.has(field))) {
    holder.warned = true
    console.warn(
      `[st_aggrid] stRollup: no total for ${canonicalKey(pairs)} although every ` +
        `field is a declared dimension — the totals table and the rows disagree ` +
        `(value serialisation, a stale table, or grouping flags lost upstream). ` +
        `Table keys look like: ${index.sampleKeys.join(" ")}`
    )
  }
  return null
}

/** Registers `stRollupAggFunc` under `ST_ROLLUP`; see `registerAggFunc` for the
 * caller-wins merge and the null-last comparator it attaches. */
export function registerStRollup(
  gridOptions: GridOptions,
  debug: boolean = false
): GridOptions {
  return registerAggFunc(gridOptions, ST_ROLLUP, stRollupAggFunc, debug)
}
