import type {
  ColDef,
  ColGroupDef,
  GridOptions,
  IAggFuncParams,
} from "ag-grid-community"

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

  // Deduplicated: a name may legitimately appear in both `num` and `den`
  // (`part / (part + rest)` — retention, conversion, share-of-total). `sums`
  // is keyed by name, so iterating a concatenation would add such a field's
  // contribution twice into the one slot — and because the inflated `sums` is
  // what the parent folds, the error compounds as 2^depth.
  const fields = Array.from(new Set([...config.num, ...config.den]))
  const sums: Record<string, number> = {}
  for (const field of fields) sums[field] = 0

  // In pivot mode the value is produced for a pivot result column, and a child
  // group stores its aggregation under *that* column's id. Folding through the
  // source column's id would find nothing and collapse every group to
  // fill_null. `aggregatedChildren` is already filtered to the pivot key, so
  // the two compose: each child contributes only its own cell's components.
  const colId = (params.pivotResultColumn ?? params.column).getColId()

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

/** The number a value sorts by: the aggregation's `toNumber()` on a group row,
 * the raw cell value on a leaf. Anything non-finite — including the NaN a
 * dataframe carries for a missing precomputed ratio — sorts as absent. */
function sortValue(raw: unknown): number | null {
  const unwrapped =
    raw && typeof (raw as StRatioValue).toNumber === "function"
      ? (raw as StRatioValue).toNumber()
      : raw
  return typeof unwrapped === "number" && Number.isFinite(unwrapped)
    ? unwrapped
    : null
}

/**
 * Orders ratio values numerically and puts empty cells last in **both**
 * directions.
 *
 * AG-Grid negates a comparator's result for a descending sort, so "last in
 * both directions" cannot be expressed by the return value alone — the null
 * branch reads `isDescending` and flips to compensate.
 */
export function stRatioComparator(
  a: unknown,
  b: unknown,
  _nodeA: unknown,
  _nodeB: unknown,
  isDescending: boolean
): number {
  const left = sortValue(a)
  const right = sortValue(b)

  if (left === null && right === null) return 0
  if (left === null) return isDescending ? -1 : 1
  if (right === null) return isDescending ? 1 : -1

  return left > right ? 1 : left < right ? -1 : 0
}

/** Visit every leaf colDef, descending into column groups. A walk that stopped
 * at the top level would miss every column on a grouped grid — and the
 * consumer wraps all of its metric columns in groups. */
function eachColDef(
  defs: (ColDef | ColGroupDef)[] | null | undefined,
  visit: (def: ColDef) => void
): void {
  for (const def of defs ?? []) {
    const children = (def as ColGroupDef).children
    if (children) eachColDef(children, visit)
    else visit(def as ColDef)
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

  // A ratio column's value is an object, so the default comparator would need
  // `toNumber` unwrapping *and* would place empty cells first ascending. Both
  // are handled here rather than by every application. A caller who supplied a
  // comparator meant it, so theirs is left alone.
  eachColDef(gridOptions.columnDefs, (def) => {
    if (def.aggFunc === ST_RATIO && !def.comparator) {
      def.comparator = stRatioComparator
    }
  })

  return gridOptions
}
