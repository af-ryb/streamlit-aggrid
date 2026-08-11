import type {
  ColDef,
  ColGroupDef,
  GridOptions,
  IAggFuncParams,
} from "ag-grid-community"

/** The IAggFuncResult shape every built-in aggregator returns. `sums` is the
 * node's folded component totals — mechanism, not API — and is what a parent
 * folds instead of rescanning leaves.
 *
 * AG-Grid 36's `IAggFuncResult` shape. `toNumber` is what the framework calls
 * for sorting, for `RowNode.getValue`, and when unwrapping the value for
 * export and charts, so it is the hook that matters — `valueOf` is not on any
 * of those paths. */
export interface StAggValue {
  value: number | null
  sums: Record<string, number>
  toNumber(): number | null
  toString(): string
}

/** Non-finite (including a dataframe NaN) becomes 0. */
export function asNumber(raw: unknown): number {
  const parsed = Number(raw)
  return Number.isFinite(parsed) ? parsed : 0
}

/** In pivot mode a child stores its aggregation under the *pivot result*
 * column's id; folding through the source column's id finds nothing. */
export function resolveColId(params: IAggFuncParams): string {
  return (params.pivotResultColumn ?? params.column).getColId()
}

/** Fold this node's children into per-key totals. Leaf children (`child.data`
 * present) contribute `leafContribution(child.data)`; group children
 * contribute their stored `sums`. Every key in `keys` is initialised to 0. */
export function foldChildren(
  params: IAggFuncParams,
  keys: string[],
  leafContribution: (data: any) => Record<string, number>
): Record<string, number> {
  const sums: Record<string, number> = {}
  for (const key of keys) sums[key] = 0

  // In pivot mode the value is produced for a pivot result column, and a child
  // group stores its aggregation under *that* column's id. Folding through the
  // source column's id would find nothing, silently dropping that child's
  // contribution. `aggregatedChildren` is already filtered to the pivot key,
  // so the two compose: each child contributes only its own cell's components.
  const colId = resolveColId(params)

  for (const child of params.aggregatedChildren ?? []) {
    if (child.data) {
      const contribution = leafContribution(child.data)
      for (const key of keys) sums[key] += asNumber(contribution[key])
    } else {
      const stored = (child.aggData ?? {})[colId] as StAggValue | undefined
      if (stored?.sums) {
        for (const key of keys) sums[key] += asNumber(stored.sums[key])
      }
    }
  }

  return sums
}

/** Build the returned value object. */
export function makeAggValue(
  value: number | null,
  sums: Record<string, number>
): StAggValue {
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
    raw && typeof (raw as StAggValue).toNumber === "function"
      ? (raw as StAggValue).toNumber()
      : raw
  return typeof unwrapped === "number" && Number.isFinite(unwrapped)
    ? unwrapped
    : null
}

/**
 * Numeric order, empty cells last in BOTH directions.
 *
 * AG-Grid negates a comparator's result for a descending sort, so "last in
 * both directions" cannot be expressed by the return value alone — the null
 * branch reads `isDescending` and flips to compensate.
 */
export function stAggComparator(
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
export function eachColDef(
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
 * Merge `fn` into `gridOptions.aggFuncs` under `name`.
 *
 * A caller-supplied entry of the same name wins: a built-in is a default,
 * not a reservation. The override is logged under `debug` because a silently
 * shadowed aggregator would be baffling to track down.
 */
export function registerAggFunc(
  gridOptions: GridOptions,
  name: string,
  fn: (params: IAggFuncParams) => unknown,
  debug: boolean = false
): GridOptions {
  const supplied = gridOptions.aggFuncs ?? {}

  if (name in supplied) {
    if (debug) {
      console.log(
        `[st_aggrid] gridOptions.aggFuncs["${name}"] was supplied by the ` +
          `caller and overrides the built-in aggregator.`
      )
    }
  } else {
    gridOptions.aggFuncs = { ...supplied, [name]: fn }
  }

  // An aggregated column's value is an object, so the default comparator would
  // need `toNumber` unwrapping *and* would place empty cells first ascending.
  // Both are handled here rather than by every application. A caller who
  // supplied a comparator meant it, so theirs is left alone.
  eachColDef(gridOptions.columnDefs, (def) => {
    if (def.aggFunc === name && !def.comparator) {
      def.comparator = stAggComparator
    }
  })

  return gridOptions
}
