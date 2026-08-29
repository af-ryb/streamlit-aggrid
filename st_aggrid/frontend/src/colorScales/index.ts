import type {
  CellClassParams,
  Column,
  ColDef,
  GridApi,
  GridOptions,
} from "ag-grid-community"
import { eachColDef } from "../aggFuncs/foldSums"
import { minmaxT, zIntensity, zScore } from "./normalize"
import {
  ColorScaleMode,
  Normalized,
  SCHEMES,
  Scheme,
  SchemeName,
  colorFor,
} from "./schemes"
import { clearStats, extractValue, statsFor } from "./population"

// Re-exported so `AgGridComponent.tsx` can invalidate the statistics cache
// ahead of a `redrawRows()` that is not preceded by `modelUpdated` — see
// `attachColorScaleInvalidation` below for the event-driven case, and the
// call sites in `AgGridComponent.tsx` for the config-only-rerun case this
// covers instead.
export { clearStats }

/** The key a declaration lives under inside `context`, at both levels.
 * Matches `st_aggrid/color_scale.py`'s COLOR_SCALE_CONTEXT_KEY. */
export const ST_COLOR_SCALE = "stColorScale"

export interface ResolvedColorScale {
  scheme: Scheme
  mode: ColorScaleMode
  skipNonPositive: boolean
}

/**
 * Merge a column's declaration over the grid-level defaults.
 *
 * A column is painted only when its own colDef carries an entry that is not
 * `false`; the grid level supplies defaults and never activates anything. The
 * merge is per key with the column winning, which is what will let phase 2's
 * `reverse` be one more key rather than a change to the shape of the API.
 *
 * Python's `validate_color_scale_columns` implements the same merge and is the
 * copy that produces an actionable error. This one exists because grid options
 * do not always come from `GridOptionsBuilder`, and returning `null` inside a
 * cell renderer is a better failure than throwing there.
 */
export function readColorScaleConfig(
  colDef: ColDef | null | undefined,
  gridContext: unknown
): ResolvedColorScale | null {
  const own = (colDef?.context as Record<string, unknown> | undefined)?.[ST_COLOR_SCALE]
  if (own === undefined || own === null || own === false) return null

  const gridDefaults = (gridContext as Record<string, unknown> | undefined)?.[
    ST_COLOR_SCALE
  ]
  const base = gridDefaults && typeof gridDefaults === "object" ? gridDefaults : {}
  const overrides = own === true ? {} : typeof own === "object" ? own : {}
  const merged = { ...base, ...overrides } as {
    scheme?: SchemeName
    mode?: ColorScaleMode
    skip_non_positive?: boolean
  }

  const scheme = merged.scheme ? SCHEMES[merged.scheme] : undefined
  if (!scheme) return null

  return {
    scheme,
    mode: merged.mode ?? scheme.defaultMode,
    skipNonPositive: merged.skip_non_positive ?? scheme.defaultSkipNonPositive,
  }
}

/** The built-in `cellStyle`. Returns `null` — not `{}` — for an unpainted cell,
 * so the theme paints it as it normally would. */
export function stColorScaleCellStyle(
  params: CellClassParams
): { backgroundColor: string } | null {
  const node = params.node
  if (!node || node.footer || node.rowPinned != null) return null

  const config = readColorScaleConfig(params.colDef, params.context)
  if (!config) return null

  const value = extractValue(params.value)
  if (value === null) return null
  if (config.skipNonPositive && value <= 0) return null

  const stats = statsFor(
    params.api,
    params.column as Column,
    node.level,
    config.skipNonPositive
  )
  if (!stats) return null

  const raw = config.mode === "minmax" ? minmaxT(stats, value) : zScore(stats, value)
  if (raw === null) return null

  const normalized: Normalized = {
    mode: config.mode,
    raw,
    intensity: config.mode === "zscore" ? zIntensity(raw) : 0,
  }
  return { backgroundColor: colorFor(config.scheme, normalized) }
}

/**
 * Where a caller-supplied `cellStyle` that would shadow the built-in comes
 * from, or `null` if none applies.
 *
 * AG-Grid resolves a cell's `cellStyle` from the colDef itself, over any
 * `columnTypes` entry named by `def.type`, over `defaultColDef` — so a caller
 * who never touched this column's own colDef can still supply its `cellStyle`
 * through either of the other two, most commonly a `defaultColDef.cellStyle`
 * set for grid-wide alignment or font. All three are checked, in that same
 * precedence order, so the reported source is the one that will actually
 * render.
 */
function callerCellStyleSource(def: ColDef, gridOptions: GridOptions): string | null {
  if (def.cellStyle) return "the column's own cellStyle"

  const types = def.type == null ? [] : Array.isArray(def.type) ? def.type : [def.type]
  for (const t of types) {
    if (gridOptions.columnTypes?.[t]?.cellStyle) return `columnTypes["${t}"].cellStyle`
  }

  if (gridOptions.defaultColDef?.cellStyle) return "defaultColDef.cellStyle"

  return null
}

/**
 * Attach `stColorScaleCellStyle` to every column carrying a declaration.
 *
 * A caller-supplied `cellStyle` wins and the built-in is not attached — the
 * same rule, for the same reason, that `registerAggFunc` applies to a
 * caller-supplied aggregator: a built-in is a default, not a reservation, and
 * a silently shadowed one would be baffling to track down. "Caller-supplied"
 * is checked through `callerCellStyleSource`, not just `def.cellStyle`:
 * `defaultColDef` and `columnTypes` can each supply one too, and writing
 * `def.cellStyle` unconditionally would silently displace either.
 *
 * Logging is not uniform across the three sources. A colDef's own `cellStyle`
 * or a `columnTypes` entry named through `def.type` was written by someone
 * working on that column, so it is logged only under `debug`. A grid-wide
 * `defaultColDef.cellStyle` belongs to someone who never touched this column
 * at all — most likely set for alignment or fonts on every column in the
 * grid — and a debug-gated log leaves them nothing to find when it silently
 * turns their colour scale off. That one is an unconditional `console.warn`.
 *
 * The attached function does not close over the declaration; it re-reads it
 * per call from `params.colDef.context` and `params.context`. Phase 2's
 * runtime toggle therefore only has to change a declaration and refresh, with
 * nothing re-attached.
 *
 * Pivot needs no handling here: AG-Grid copies `cellStyle` from the source
 * value colDef onto the pivot result column it generates.
 */
export function registerColorScales(
  gridOptions: GridOptions,
  debug: boolean = false
): GridOptions {
  eachColDef(gridOptions.columnDefs, (def) => {
    // Same predicate `paintedColumnIds` and `stColorScaleCellStyle` use: a
    // declaration that resolves to no valid scheme paints nothing, so it must
    // not occupy the cellStyle slot either.
    if (readColorScaleConfig(def, gridOptions.context) === null) return

    const source = callerCellStyleSource(def, gridOptions)
    if (source) {
      const colId = def.colId ?? def.field
      if (source === "defaultColDef.cellStyle") {
        console.warn(
          `[st_aggrid] "${colId}" declares a colour scale, but defaultColDef.cellStyle ` +
            `wins for every column in this grid, so the built-in was not attached and ` +
            `"${colId}" will not be painted.`
        )
      } else if (debug) {
        console.log(
          `[st_aggrid] cellStyle on "${colId}" was supplied ` +
            `by ${source} and overrides the built-in colour scale.`
        )
      }
      return
    }
    def.cellStyle = stColorScaleCellStyle
  })

  return gridOptions
}

/** Every displayed column that the colour scale paints. Derived on demand
 * rather than cached at attach time so it stays correct across
 * `updateGridOptions` and across pivot mode being toggled. */
function paintedColumnIds(api: GridApi): string[] {
  const columns = (api.isPivotMode() ? api.getPivotResultColumns() : api.getColumns()) ?? []
  const context = api.getGridOption("context")
  return columns
    .filter((column) => readColorScaleConfig(column.getColDef(), context) !== null)
    .map((column) => column.getColId())
}

/**
 * Keep the cached statistics honest across filtering, sorting and new data.
 * Returns its own teardown.
 *
 * Clearing the cache would be enough if this listener were guaranteed to run
 * before AG-Grid re-renders its rows, but listener ordering is not ours to
 * control — so the refresh is the safety net that repaints anything already
 * drawn from stale statistics. `refreshCells` does not raise `modelUpdated`,
 * so this cannot loop; the `refreshing` flag says so explicitly rather than
 * leaving it implicit.
 *
 * The cost is not uniform across the repaint. `refreshCells` itself only
 * re-renders the rendered viewport, a few dozen rows however large the grid
 * is — but clearing the cache means the *first* cell it repaints in each
 * `(column, level)` pays a full `statsFor` walk of the entire model, one
 * `api.getCellValue` per row, to rebuild that entry. Still a large win over
 * the per-cell `forEachNodeAfterFilterAndSort` scan this replaces, just not
 * the flat "a few dozen rows total" cost that description alone would imply.
 */
export function attachColorScaleInvalidation(api: GridApi): () => void {
  let frame = 0
  let refreshing = false

  const onModelUpdated = () => {
    if (refreshing) return
    clearStats(api)
    if (frame) return
    frame = requestAnimationFrame(() => {
      frame = 0
      if (api.isDestroyed()) return
      const columns = paintedColumnIds(api)
      if (!columns.length) return
      refreshing = true
      try {
        api.refreshCells({ force: true, columns })
      } finally {
        refreshing = false
      }
    })
  }

  api.addEventListener("modelUpdated", onModelUpdated)

  return () => {
    if (frame) {
      cancelAnimationFrame(frame)
      frame = 0
    }
    if (!api.isDestroyed()) api.removeEventListener("modelUpdated", onModelUpdated)
  }
}
