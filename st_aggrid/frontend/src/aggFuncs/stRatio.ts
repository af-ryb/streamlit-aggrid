import type { ColDef, GridOptions, IAggFuncParams } from "ag-grid-community"
import {
  asNumber,
  foldChildren,
  makeAggValue,
  registerAggFunc,
  stAggComparator,
  StAggValue,
} from "./foldSums"

/** Back-compat: existing imports of `stRatioComparator` / `StRatioValue`
 * keep resolving to the shared implementation. */
export { stAggComparator as stRatioComparator }
export type StRatioValue = StAggValue

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
export function stRatioAggFunc(params: IAggFuncParams): StAggValue | null {
  const config = readStRatioConfig(params.colDef)
  if (!config) return null

  // Deduplicated: a name may legitimately appear in both `num` and `den`
  // (`part / (part + rest)` — retention, conversion, share-of-total). `sums`
  // is keyed by name, so iterating a concatenation would add such a field's
  // contribution twice into the one slot — and because the inflated `sums` is
  // what the parent folds, the error compounds as 2^depth.
  const fields = Array.from(new Set([...config.num, ...config.den]))
  const sums = foldChildren(params, fields, (data) =>
    Object.fromEntries(fields.map((f) => [f, asNumber(data[f])]))
  )

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

  return makeAggValue(value, sums)
}

/** Registers `stRatioAggFunc` under `ST_RATIO` and wires up its comparator;
 * see `registerAggFunc` for the merge/override/comparator-attach behaviour. */
export function registerStRatio(
  gridOptions: GridOptions,
  debug: boolean = false
): GridOptions {
  return registerAggFunc(gridOptions, ST_RATIO, stRatioAggFunc, debug)
}
