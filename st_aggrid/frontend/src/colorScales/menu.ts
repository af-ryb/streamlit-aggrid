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
 * config update switches the opt-in off on a grid whose column-menu hook —
 * `@initial` in AG-Grid — can no longer be removed.
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
    action: () => apply({ kind: "mode", mode: value }),
  }))
  if (anchorAvailable) {
    modeItems.push({
      name: "Anchor",
      checked: mode === "anchor",
      action: () => apply({ kind: "mode", mode: "anchor" }),
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

function withColorScale(
  items: Items | null | undefined,
  api: GridApi,
  column: Column | null | undefined,
  runtime: ColorScaleRuntime
): Items {
  const base = items ?? []
  if (!column) return base
  const item = colorScaleItem(api, column, runtime)
  return item ? [...base, "separator", item] : base
}

/**
 * Install the picker on the grid's menus. Called only for parsed options that
 * are interactive, so a grid that never opts in gets no wrapper around its
 * menus at all. `getColumnMenuItems` is an `@initial` grid option — AG-Grid
 * reads it at creation only — while `getContextMenuItems` is re-applied by
 * `updateGridOptions`. Hence the asymmetry when `interactive` is switched on
 * for a live grid: the cell menu gains the item at once, the column menu and
 * the Columns panel only after a remount. Switching it off needs neither:
 * every open re-checks the live flag (`isEligible`).
 *
 * `getColumnMenuItems` (AG-Grid 36.1) serves the column menu, the Columns tool
 * panel and the Column Chooser. It takes precedence over `getMainMenuItems`
 * for the column menu, so a caller's `getMainMenuItems` is delegated to here
 * or it would be shadowed. Whatever the caller supplied is kept and the item
 * appended — a built-in is a default, not a reservation. A colDef-level
 * `mainMenuItems`/`contextMenuItems` overrides these grid-level hooks for its
 * column and is left alone.
 */
export function registerColorScaleMenu(
  gridOptions: GridOptions,
  runtime: ColorScaleRuntime
): GridOptions {
  const callerColumn = gridOptions.getColumnMenuItems
  const callerMain = gridOptions.getMainMenuItems
  const callerContext = gridOptions.getContextMenuItems

  gridOptions.getColumnMenuItems = (params: GetColumnMenuItemsParams) => {
    let items: Items
    if (typeof callerColumn === "function") {
      items = callerColumn(params) as Items
    } else if (params.source === "columnMenu" && typeof callerMain === "function") {
      // `GetMainMenuItemsParams` differs only in the token union of
      // `defaultItems`, which a caller reads and never constructs.
      items = callerMain(params as any) as Items
    } else {
      items = params.defaultItems as Items
    }
    // `MenuCallbackReturn<DefaultColumnMenuItem>` is narrower than `Items`:
    // its strings are the built-in tokens, and a caller's arbitrary string is
    // not in that union.
    return withColorScale(items, params.api, params.column, runtime) as any
  }

  gridOptions.getContextMenuItems = (params: GetContextMenuItemsParams) => {
    const result: unknown =
      typeof callerContext === "function" ? callerContext(params) : params.defaultItems
    // A caller's hook may be async (`gridOptions.d.ts:2728`).
    if (result && typeof (result as Promise<Items>).then === "function") {
      return (result as Promise<Items>).then(
        // As above: `MenuCallbackReturn<DefaultMenuItem>`.
        (items) => withColorScale(items, params.api, params.column, runtime) as any
      )
    }
    return withColorScale(result as Items, params.api, params.column, runtime) as any
  }

  return gridOptions
}
