import type { ColDef, GridOptions, IAggFuncParams } from "ag-grid-community"

/** Name callers reference from `colDef.aggFunc`, and the key their parameters
 * are nested under inside `colDef.context` so they cannot collide with other
 * uses of that field. */
export const ST_RATIO = "stRatio"

export interface StRatioConfig {
  num: string[]
  den: string[]
  num_signs?: number[]
  multiplier?: number
  scale?: number
  /** Value when the denominator sums to zero. Defaults to null — an empty
   * cell — which is what the JavaScript this replaces already renders. */
  fill_null?: number | null
}

/**
 * AG-Grid 36's `IAggFuncResult` shape. `toNumber` is what the framework calls
 * for sorting, for `RowNode.getValue`, and when unwrapping the value for
 * export and charts, so it is the hook that matters — `valueOf` is not on any
 * of those paths.
 */
export interface StRatioValue {
  value: number | null
  /** Component sums for this node's subtree. Carried so a parent group can
   * fold its children instead of rescanning leaves; mechanism, not API. */
  sums: Record<string, number>
  toNumber(): number | null
  toString(): string
}

function asNumber(raw: unknown): number {
  const parsed = Number(raw)
  return Number.isFinite(parsed) ? parsed : 0
}

export function readStRatioConfig(colDef?: ColDef | null): StRatioConfig | null {
  const config = (colDef?.context as Record<string, unknown> | undefined)?.[ST_RATIO]
  if (!config || typeof config !== "object") return null
  const candidate = config as StRatioConfig
  if (!Array.isArray(candidate.num) || !Array.isArray(candidate.den)) return null
  return candidate
}

/**
 * `(Σ signᵢ·numᵢ · multiplier / Σden) · scale`, where every field name resolves
 * to the sum of that field over the node's subtree.
 *
 * Each node is visited once. A leaf group's `aggregatedChildren` are data rows,
 * so their components are read straight off `row.data`; a higher group's
 * children are groups, so their already-computed `sums` are folded instead.
 * Re-walking `allLeafChildren` at every level would be correct but quadratic in
 * depth — and, being blind to pivot keys, wrong in a pivot cell.
 */
export function stRatioAggFunc(params: IAggFuncParams): StRatioValue | null {
  const config = readStRatioConfig(params.colDef)
  if (!config) return null

  const fields = [...config.num, ...config.den]
  const sums: Record<string, number> = {}
  for (const field of fields) sums[field] = 0

  const colId = params.column.getColId()

  for (const child of params.aggregatedChildren ?? []) {
    if (child.data) {
      for (const field of fields) sums[field] += asNumber(child.data[field])
    } else {
      const stored = (child.aggData ?? {})[colId] as StRatioValue | undefined
      if (stored?.sums) {
        for (const field of fields) sums[field] += asNumber(stored.sums[field])
      }
    }
  }

  const signs = config.num_signs ?? config.num.map(() => 1)
  let numerator = 0
  for (let i = 0; i < config.num.length; i++) {
    numerator += signs[i] * sums[config.num[i]]
  }

  let denominator = 0
  for (const field of config.den) denominator += sums[field]

  const multiplier = config.multiplier ?? 1
  const scale = config.scale ?? 1
  // `?? null` and not `|| null`: an explicit fill_null of 0 must survive.
  const fillNull = config.fill_null ?? null

  const value =
    denominator !== 0
      ? ((numerator * multiplier) / denominator) * scale
      : fillNull

  return {
    value,
    sums,
    toNumber: () => value,
    toString: () => (value == null ? "" : String(value)),
  }
}

/**
 * Merge the built-in aggregator into `gridOptions.aggFuncs`.
 *
 * A caller-supplied entry of the same name wins: the built-in is a default,
 * not a reservation. The override is logged under `debug` because a silently
 * shadowed aggregator would be baffling to track down.
 */
export function registerStRatio(
  gridOptions: GridOptions,
  debug: boolean = false
): GridOptions {
  const supplied = gridOptions.aggFuncs ?? {}

  if (ST_RATIO in supplied) {
    if (debug) {
      console.log(
        `[st_aggrid] gridOptions.aggFuncs["${ST_RATIO}"] was supplied by the ` +
          `caller and overrides the built-in ratio aggregator.`
      )
    }
  } else {
    gridOptions.aggFuncs = { ...supplied, [ST_RATIO]: stRatioAggFunc }
  }

  return gridOptions
}
