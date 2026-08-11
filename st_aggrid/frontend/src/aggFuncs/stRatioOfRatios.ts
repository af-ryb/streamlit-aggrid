import type { ColDef, GridOptions, IAggFuncParams } from "ag-grid-community"
import { asNumber, foldChildren, makeAggValue, registerAggFunc, StAggValue } from "./foldSums"
import { evaluateLeg, StRatioLeg } from "./stRatio"

/** Name callers reference from `colDef.aggFunc`, and the key their parameters
 * are nested under inside `colDef.context` — same convention as `ST_RATIO`. */
export const ST_RATIO_OF_RATIOS = "stRatioOfRatios"

/** `to_ratio / from_ratio`, each leg a full `StRatioLeg` (`num`, `den`, and
 * optionally `num_signs`, `multiplier`, `scale`, `den_const`) — the shape
 * `evaluateLeg` already knows how to compute. A leg has no `fill_null` of its
 * own; only the outer division does. */
export interface StRatioOfRatiosConfig {
  from: StRatioLeg
  to: StRatioLeg
  /** Value when either leg's denominator sums to zero, or when `from_ratio`
   * itself is exactly zero (the outer division's own `!== 0` gate). Defaults
   * to null — an empty cell — same key, same semantics as `StRatioConfig`. */
  fill_null?: number | null
}

function isLeg(value: unknown): value is StRatioLeg {
  return (
    !!value &&
    typeof value === "object" &&
    Array.isArray((value as StRatioLeg).num) &&
    Array.isArray((value as StRatioLeg).den)
  )
}

export function readStRatioOfRatiosConfig(
  colDef?: ColDef | null
): StRatioOfRatiosConfig | null {
  const config = (colDef?.context as Record<string, unknown> | undefined)?.[
    ST_RATIO_OF_RATIOS
  ]
  if (!config || typeof config !== "object") return null
  const candidate = config as StRatioOfRatiosConfig
  if (!isLeg(candidate.from) || !isLeg(candidate.to)) return null
  return candidate
}

/**
 * `(Σnum_to/Σden_to) / (Σnum_from/Σden_from)`, each leg re-derived at *this*
 * node from `sums` via `evaluateLeg` — never combined from the children's
 * already-computed outer ratios. That is what makes a pivot cell, a pivot row
 * total and the grand total each correct independently rather than each one
 * inheriting whatever its row (or the whole grid) computed — the defect the
 * retired JavaScript this aggregator replaces has, summing over
 * `rowNode.allLeafChildren` regardless of pivot key. See the design spec's
 * "Why `stRatio` cannot express it": `(A/B)/(C/D) = A·D/(B·C)` is a product of
 * sums in both numerator and denominator, which no single `stRatio` fraction
 * can express — hence two `evaluateLeg` calls and an outer division here,
 * rather than one.
 *
 * `!== 0` throughout (Global Constraints): both legs gate on their own
 * denominator, and the outer division additionally gates on `from_ratio`
 * itself. The retired JavaScript gated all three on `> 0` — a deliberate,
 * documented behaviour change, not an oversight (see `growth_neg` in
 * `test/ratio_fixture.py`).
 */
export function stRatioOfRatiosAggFunc(
  params: IAggFuncParams
): StAggValue | null {
  const config = readStRatioOfRatiosConfig(params.colDef)
  if (!config) return null

  // Deduplicated union of all four field lists: a name may legitimately
  // appear more than once (across legs, or within a leg's own `num`/`den`),
  // and `sums` is keyed by name, so folding a concatenation would inflate
  // such a field's contribution — see `stRatioAggFunc`'s identical reasoning.
  const fields = Array.from(
    new Set([
      ...config.from.num,
      ...config.from.den,
      ...config.to.num,
      ...config.to.den,
    ])
  )
  const sums = foldChildren(params, fields, (data) =>
    Object.fromEntries(fields.map((f) => [f, asNumber(data[f])]))
  )

  const fromRatio = evaluateLeg(sums, config.from)
  const toRatio = evaluateLeg(sums, config.to)
  // `?? null` and not `|| null`: an explicit fill_null of 0 must survive.
  const value =
    fromRatio != null && toRatio != null && fromRatio !== 0
      ? toRatio / fromRatio
      : (config.fill_null ?? null)

  return makeAggValue(value, sums)
}

/** Registers `stRatioOfRatiosAggFunc` under `ST_RATIO_OF_RATIOS` and wires up
 * its comparator; see `registerAggFunc` for the merge/override/comparator-
 * attach behaviour. */
export function registerStRatioOfRatios(
  gridOptions: GridOptions,
  debug: boolean = false
): GridOptions {
  return registerAggFunc(gridOptions, ST_RATIO_OF_RATIOS, stRatioOfRatiosAggFunc, debug)
}
