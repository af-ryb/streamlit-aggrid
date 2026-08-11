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
  /** Added to the denominator once per node, not folded through
   * `foldChildren` like a `den` entry. A `den` field is a component summed
   * over the subtree, so its contribution naturally scales with however many
   * leaves a group has; a window-wide constant (e.g. a total computed once in
   * Python and repeated on every row) must not scale that way — folding it as
   * another `den` entry would multiply it by the child count and shrink every
   * group's share. `den` may be empty when this alone is the denominator. */
  den_const?: number
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
 * `stRatio` is registered into `gridOptions.aggFuncs` on every grid (see
 * `parseGridOptions`), so AG-Grid offers it in the columns tool panel's
 * aggregation picker for *any* value column — including one with no
 * `context["stRatio"]` declaration, and one that acquires `aggFunc: "stRatio"`
 * purely at runtime (grid state restore, the columns panel), which
 * `readStRatioConfig` never sees because it only runs per-node at aggregation
 * time, not at parse time. Returning `null` there blanks the column; summing
 * instead degrades it to a plain `sum` — sane, if not necessarily what the
 * user meant by picking "stRatio".
 *
 * `params.values` already carries each immediate child's own value — a raw
 * cell on a leaf, that child's own returned total on a group — correctly
 * scoped to the current pivot key by AG-Grid itself, so summing it is the
 * same one-level fold every other aggregator here does, just without needing
 * `foldChildren`: a plain sum is associative, so summing each level's own
 * `values` reproduces the grand total without re-walking leaves.
 *
 * Returns a plain `number`, never an `StAggValue`, for two reasons:
 *
 * 1. A `valueFormatter` written for a number keeps working. The concrete
 *    case this task exists for: a column already declared `aggFunc: "sum"`
 *    with a formatter written for a raw number (`params.value.toFixed(2)`,
 *    say) is switched to `stRatio` at runtime, through the columns tool
 *    panel or grid state — the formatter is never told the value's shape
 *    changed, and `.toFixed` does not exist on a plain object. An
 *    `StAggValue` carrying an all-zero `sums` would in any case be no more
 *    useful than the blank it replaces.
 * 2. `registerAggFunc` attaches `stAggComparator` by walking `columnDefs` at
 *    parse time, so a column that acquires `stRatio` only at runtime never
 *    gets a comparator, and sorts under AG-Grid's own default instead.
 *    Measured against AG-Grid 36's compiled default comparator
 *    (`ag-grid-community.js`'s `_defaultComparator`): it already unwraps a
 *    `toNumber()`-bearing object before comparing, the same way
 *    `stAggComparator` does, so for a *non-null* result the plain-number
 *    choice does not, in fact, change sort order here — reason (1) alone
 *    already requires it, and not relying on that AG-Grid internal is the
 *    more future-proof habit regardless.
 */
function sumFallback(params: IAggFuncParams): number | null {
  let total = 0
  let sawValue = false
  for (const raw of params.values ?? []) {
    const unwrapped =
      raw && typeof (raw as StAggValue).toNumber === "function"
        ? (raw as StAggValue).toNumber()
        : raw
    if (typeof unwrapped !== "number" || !Number.isFinite(unwrapped)) continue
    total += unwrapped
    sawValue = true
  }
  return sawValue ? total : null
}

/**
 * `(Σ signᵢ·numᵢ · multiplier / (den_const + Σden)) · scale`, where every
 * field name resolves to the sum of that field over the node's subtree.
 *
 * Each node is visited once. A leaf group's `aggregatedChildren` are data rows,
 * so their components are read straight off `row.data`; a higher group's
 * children are groups, so their already-computed `sums` are folded instead.
 * Re-walking `allLeafChildren` at every level would be correct but quadratic in
 * depth — and, being blind to pivot keys, wrong in a pivot cell.
 */
export function stRatioAggFunc(
  params: IAggFuncParams
): StAggValue | number | null {
  const config = readStRatioConfig(params.colDef)
  if (!config) return sumFallback(params)

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

  // `den_const` is a window-wide constant, not a per-leaf component: it is
  // added once here rather than folded through `sums`, which would multiply
  // it by the subtree's child count. See `StRatioConfig.den_const`.
  let denominator = config.den_const ?? 0
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
