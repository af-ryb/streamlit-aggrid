import type { ColDef, GridOptions, IAggFuncParams } from "ag-grid-community"
import { foldChildren, makeAggValue, registerAggFunc, StAggValue } from "./foldSums"

/** Name callers reference from `colDef.aggFunc`, and the key their parameters
 * are nested under inside `colDef.context` — same convention as `stRatio`
 * and `stRatioOfRatios`. */
export const ST_WEIGHTED_AVG = "stWeightedAvg"

export interface StWeightedAvgConfig {
  /** Field carrying a precomputed per-row ratio (a leaf's own CPI, ARPU,
   * ...). Read straight off `data`, never summed — there is no numerator/
   * denominator field pair here the way `stRatio` has. */
  value: string
  /** Field carrying that row's weight (installs, sessions, ...). */
  weight: string
  scale?: number
  /** Value when the surviving weight sums to zero — every leaf was skipped
   * because its value was non-finite or its weight was not strictly
   * positive. Defaults to null — an empty cell — same key, same semantics as
   * `StRatioConfig.fill_null`. */
  fill_null?: number | null
}

export function readStWeightedAvgConfig(
  colDef?: ColDef | null
): StWeightedAvgConfig | null {
  const config = (colDef?.context as Record<string, unknown> | undefined)?.[
    ST_WEIGHTED_AVG
  ]
  if (!config || typeof config !== "object") return null
  const candidate = config as StWeightedAvgConfig
  return typeof candidate.value === "string" && typeof candidate.weight === "string"
    ? candidate
    : null
}

// Synthetic `sums` keys this aggregator folds under. Not field names: a
// leaf's contribution is the *product* `v·w` evaluated per row, not a field
// summed as-is, so there is nothing named `value`/`weight` to fold — instead
// every leaf contributes to these two accumulators, and `foldChildren`
// doesn't need to know what they mean to fold them correctly.
const WNUM = "wnum"
const WDEN = "wden"

/**
 * `Σ(vᵢ·wᵢ)/Σwᵢ` over a precomputed per-row ratio `value`, weighted by
 * `weight` — an install-weighted blended CPI/ARPU, the shape the consumer's
 * retired `installWeightedAvg` JavaScript computed. Neither `stRatio` (a sum
 * of fields) nor `stRatioOfRatios` (a product of sums) can express this: the
 * numerator here is a **sum of products** evaluated per leaf, which is why
 * this is its own aggregator rather than a third `evaluateLeg` shape.
 *
 * Leaf skip rule, reproduced from the retired JavaScript exactly — both-or-
 * neither, not two independent gates:
 *
 *     Number.isFinite(v) && w > 0 ? { wnum: v * w, wden: w } : { wnum: 0, wden: 0 }
 *
 * A leaf with a null/NaN value, or a non-positive weight, contributes to
 * *neither* accumulator. Dropping it from the numerator alone while leaving
 * its weight in `wden` would pull every ancestor group toward zero; keeping
 * `v·w` in the numerator while dropping only the weight would let a
 * non-positive weight masquerade as a real observation.
 *
 * Unlike `stRatioOfRatios`, this port has no behaviour delta from the
 * retired JavaScript worth hunting for: because a weight only ever
 * accumulates into `wden` when `w > 0`, `wden` can never go negative, so the
 * Global Constraints' `!== 0` final-division gate and the JavaScript's
 * `w > 0` leaf gate coincide here.
 *
 * One implementation wrinkle the retired JavaScript never had to deal with:
 * `parseData` (`utils/parsers.ts`) round-trips a DataFrame's Arrow table
 * through `JSON.stringify`/`JSON.parse` to strip BigInts, and `JSON.stringify`
 * has no representation for `NaN` — it serialises to `null`. So a missing
 * `value` reaches this aggregator as raw `null`, not `NaN`, and `Number(null)`
 * is `0`, which *is* finite — `Number.isFinite` alone would let a missing
 * value silently pass as a real zero. `rawValue != null` catches it ahead of
 * that coercion; the weight side needs no equivalent guard because
 * `Number(null)` is `0` and `0 > 0` is already false.
 */
export function stWeightedAvgAggFunc(
  params: IAggFuncParams
): StAggValue | null {
  const config = readStWeightedAvgConfig(params.colDef)
  if (!config) return null

  const sums = foldChildren(params, [WNUM, WDEN], (data) => {
    const rawValue = data[config.value]
    const v = Number(rawValue)
    const w = Number(data[config.weight])
    return rawValue != null && Number.isFinite(v) && w > 0
      ? { [WNUM]: v * w, [WDEN]: w }
      : { [WNUM]: 0, [WDEN]: 0 }
  })

  const scale = config.scale ?? 1
  // `?? null`, not `||`: an explicit `fill_null: 0` must survive, and a
  // computed value of exactly 0 (nonzero surviving weight, zero weighted sum)
  // is a real value, not a signal to fall back to `fill_null`.
  const value =
    sums[WDEN] !== 0 ? (sums[WNUM] / sums[WDEN]) * scale : (config.fill_null ?? null)

  return makeAggValue(value, sums)
}

/** Registers `stWeightedAvgAggFunc` under `ST_WEIGHTED_AVG` and wires up its
 * comparator; see `registerAggFunc` for the merge/override/comparator-attach
 * behaviour. */
export function registerStWeightedAvg(
  gridOptions: GridOptions,
  debug: boolean = false
): GridOptions {
  return registerAggFunc(gridOptions, ST_WEIGHTED_AVG, stWeightedAvgAggFunc, debug)
}
