import type {
  Column,
  GetColumnMenuItemsParams,
  GetContextMenuItemsParams,
  GridApi,
  GridOptions,
  MenuItemDef,
} from "ag-grid-community"
import {
  ColorScaleRuntime,
  ST_COLOR_SCALE,
  clearStats,
  isInteractive,
  lowerLayers,
  readColorScaleConfig,
  sourceColumnOf,
  stColorScaleCellStyle,
} from "./index"
import { Choice, applyChoice } from "./overrides"

type Items = (string | MenuItemDef)[]

const SCHEME_ITEMS: readonly [string, string][] = [
  ["neutral", "Neutral"],
  ["positive", "Positive"],
  ["diverging", "Diverging"],
  ["rank", "Rank"],
]
const MODE_ITEMS: readonly [string, string][] = [
  ["minmax", "Min–max"],
  ["zscore", "Z-score"],
]

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value)
}

/**
 * Whether the picker is offered on `source` — a real column, never a pivot
 * result column (callers pass `sourceColumnOf`'s result).
 *
 * The first check is the load-bearing one: the slot is ours only where
 * `registerColorScales` attached the built-in, so this single identity test
 * covers a caller's `cellStyle` from any of its three sources, the auto-group
 * column (never walked by `eachColDef`), and a column `registerColorScales`
 * skipped. The live `isInteractive` check is what takes the item away when a
 * config update switches the opt-in off: the hooks stay installed on the grid
 * for as long as it lives — `updateGridOptions` writes the keys it is given
 * and cannot clear one it is not — while the flag under them can change.
 */
export function isEligible(source: Column, gridContext: unknown): boolean {
  if (!isInteractive(gridContext)) return false
  const def = source.getColDef()
  if (def.cellStyle !== stColorScaleCellStyle) return false

  const own = (def.context as Record<string, unknown> | undefined)?.[ST_COLOR_SCALE]
  // The page author's explicit "not this column".
  if (own === false) return false
  // A fill marks a structural column, not a measurement.
  if (readColorScaleConfig(def, gridContext)?.kind === "fill") return false

  // A measure: declared, aggregated, or numeric. `cellDataType` is the
  // inferred one — AG-Grid writes it into the colDef (measured 2026-09-20).
  if (own !== undefined && own !== null) return true
  if (def.aggFunc != null || source.getAggFunc() != null) return true
  if (def.cellDataType === "number") return true
  const types = def.type == null ? [] : Array.isArray(def.type) ? def.type : [def.type]
  return types.includes("numericColumn")
}

/** The `Colour scale ▸` item for one column, or `null` when not offered. */
function colorScaleItem(
  api: GridApi,
  column: Column,
  runtime: ColorScaleRuntime
): MenuItemDef | null {
  const context = api.getGridOption("context")
  const source = sourceColumnOf(column.getColDef(), column)
  if (!source || !isEligible(source, context)) return null

  const colId = source.getColId()
  const def = source.getColDef()
  const own = (def.context as Record<string, unknown> | undefined)?.[ST_COLOR_SCALE]
  const hasOwn = own !== undefined && own !== null

  // Read fresh on every open — AG-Grid calls the hook each time — so a tick
  // can never be stale.
  const override = runtime.overrides.get(colId)
  const resolved = readColorScaleConfig(def, context, override)
  const lower = lowerLayers(def, context)
  const anchorAvailable =
    isFiniteNumber(lower.anchor) && isFiniteNumber(lower.span) && lower.span > 0

  const scheme =
    resolved === null || resolved.kind === "fill"
      ? null
      : resolved.kind === "rank"
        ? "rank"
        : resolved.scheme.name
  const mode =
    resolved?.kind === "ramp" ? resolved.mode : resolved?.kind === "anchor" ? "anchor" : null
  const reverse = resolved !== null && resolved.kind !== "fill" && resolved.reverse
  const isRamp = resolved?.kind === "ramp" || resolved?.kind === "anchor"

  // A mode alone does not always name a scale: `mode: "anchor"` and nothing
  // else resolves to `diverging`, and storing another mode over it would leave
  // the merge schemeless. So the mode items carry the resolved scheme whenever
  // neither lower layer spells one out and the reader has not already picked
  // one. See `Choice` in `overrides.ts`.
  const overrideScheme = override === undefined || override === false ? undefined : override.scheme
  const modeScheme =
    lower.scheme === undefined && overrideScheme === undefined && scheme !== null
      ? scheme
      : undefined

  const apply = (choice: Choice) => {
    applyChoice(runtime.overrides, colId, choice, hasOwn)
    // A different scheme can change the skip rule, hence the population.
    clearStats(api)
    const displayed = [...(api.getColumns() ?? []), ...(api.getPivotResultColumns() ?? [])]
    const columns = displayed
      .filter((c) => sourceColumnOf(c.getColDef(), c) === source)
      .map((c) => c.getColId())
    api.refreshCells({ force: true, columns })
    runtime.onChange(colId)
  }

  const modeItems: MenuItemDef[] = MODE_ITEMS.map(([value, name]) => ({
    name,
    checked: mode === value,
    action: () => apply({ kind: "mode", mode: value, scheme: modeScheme }),
  }))
  if (anchorAvailable) {
    modeItems.push({
      name: "Anchor",
      checked: mode === "anchor",
      action: () => apply({ kind: "mode", mode: "anchor", scheme: modeScheme }),
    })
  }

  const subMenu: Items = [
    { name: "None", checked: resolved === null, action: () => apply({ kind: "none" }) },
    ...SCHEME_ITEMS.map(
      ([value, name]): MenuItemDef => ({
        name,
        checked: scheme === value,
        action: () => apply({ kind: "scheme", scheme: value }),
      })
    ),
    "separator",
    { name: "Mode", disabled: !isRamp, subMenu: modeItems },
    {
      name: "Reverse",
      disabled: resolved === null,
      checked: reverse,
      action: () => apply({ kind: "reverse", reverse: !reverse }),
    },
  ]
  if (override !== undefined) {
    subMenu.push("separator", {
      name: "Reset to default",
      action: () => apply({ kind: "reset" }),
    })
  }

  return { name: "Colour scale", subMenu }
}

/** The three fields both hooks' params share, and all `withColorScale` reads. */
interface MenuParams {
  api: GridApi
  column: Column | null
  defaultItems?: readonly (string | MenuItemDef)[]
}

/**
 * Append the picker to whatever the caller's hook produced.
 *
 * A hook that returns nothing means "show the defaults" to AG-Grid, so the
 * defaults — not an empty menu — are the fallback here too. And a separator
 * only separates: with nothing above it, it would be a rule across the top of
 * the menu.
 */
function withColorScale(
  items: Items | null | undefined,
  params: MenuParams,
  runtime: ColorScaleRuntime
): Items {
  const base: Items = [...(items ?? params.defaultItems ?? [])]
  if (!params.column) return base
  const item = colorScaleItem(params.api, params.column, runtime)
  if (!item) return base
  return base.length ? [...base, "separator", item] : [item]
}

/**
 * Install the picker on the grid's menus. Called only for parsed options that
 * are interactive, so a grid that never opts in gets no wrapper around its
 * menus at all.
 *
 * Both hooks reach a live grid through `updateGridOptions`, in both
 * directions. `getColumnMenuItems` carries an `@initial` tag in AG-Grid's
 * typings, but that tag is typings-only: the key is not in the runtime's
 * `INITIAL_GRID_OPTION_KEYS`, `updateGridOptions` writes every key it is
 * handed, and `_resolveColumnMenuItems` reads the callback through
 * `gos.getCallback` on every open (measured against the shipped 36.1.0
 * bundles, and pinned by the e2e test
 * `test_interactive_takes_effect_on_a_live_grid_in_both_directions`).
 * Switching the opt-in *off* is the case the live re-check in `isEligible`
 * serves: a wrapper already installed cannot be taken off again — an absent
 * key is not written, so `updateGridOptions` cannot clear it — and the flag it
 * was installed for can change underneath it.
 *
 * `getColumnMenuItems` (AG-Grid 36.1) serves the column menu, the Columns tool
 * panel and the Column Chooser. Whatever the caller supplied is kept and the
 * item appended — a built-in is a default, not a reservation. It sits ahead of
 * two things in AG-Grid's own resolution order, and installing one
 * unconditionally would swallow both, so the wrapper reproduces them: the
 * caller's grid-level `getMainMenuItems`, and a colDef-level `mainMenuItems`.
 * A colDef-level `columnMenuItems` (36.1) and `contextMenuItems` need no such
 * care — AG-Grid resolves both *before* the grid-level hook, so the wrapper
 * never runs for that column at all.
 */
export function registerColorScaleMenu(
  gridOptions: GridOptions,
  runtime: ColorScaleRuntime
): GridOptions {
  const callerColumn = gridOptions.getColumnMenuItems
  const callerMain = gridOptions.getMainMenuItems
  const callerContext = gridOptions.getContextMenuItems

  gridOptions.getColumnMenuItems = (params: GetColumnMenuItemsParams) => {
    // `undefined` and an empty array are not the same answer: the first means
    // "whatever AG-Grid would have shown", the second an empty menu.
    let items: Items | null | undefined
    if (typeof callerColumn === "function") {
      items = callerColumn(params) as Items
    } else if (params.source === "columnMenu") {
      // The two steps AG-Grid's `_resolveColumnMenuItems` would have taken
      // next had no grid-level `getColumnMenuItems` been installed. The
      // colDef's own menu is returned as AG-Grid would have shown it, picker
      // and all defaults left out: a per-column `mainMenuItems` replaces its
      // column's menu, and appending to it would be taking the column over.
      const ownDef = params.column?.getColDef() ?? params.columnGroup?.getColGroupDef()
      const ownItems = ownDef?.mainMenuItems
      if (Array.isArray(ownItems)) return ownItems as any
      // `GetMainMenuItemsParams` differs only in the token union of
      // `defaultItems`, which a caller reads and never constructs.
      if (typeof ownItems === "function") return ownItems(params as any) as any
      items = typeof callerMain === "function" ? (callerMain(params as any) as Items) : undefined
    }
    // Anything else — the Columns panel and the Column Chooser — leaves
    // `items` undefined, i.e. `params.defaultItems`.
    //
    // `MenuCallbackReturn<DefaultColumnMenuItem>` is narrower than `Items`:
    // its strings are the built-in tokens, and a caller's arbitrary string is
    // not in that union.
    return withColorScale(items, params, runtime) as any
  }

  gridOptions.getContextMenuItems = (params: GetContextMenuItemsParams) => {
    const result: unknown = typeof callerContext === "function" ? callerContext(params) : undefined
    // A caller's hook may be async (`gridOptions.d.ts:2728`).
    if (result && typeof (result as Promise<Items>).then === "function") {
      return (result as Promise<Items>).then(
        // As above: `MenuCallbackReturn<DefaultMenuItem>`.
        (items) => withColorScale(items, params, runtime) as any
      )
    }
    return withColorScale(result as Items | null | undefined, params, runtime) as any
  }

  return gridOptions
}
