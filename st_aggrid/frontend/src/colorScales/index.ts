import type {
  CellClassParams,
  CellStyle,
  Column,
  ColDef,
  GridApi,
  GridOptions,
} from "ag-grid-community"
import { eachColDef } from "../aggFuncs/foldSums"
import { anchorD, minmaxT, zIntensity, zScore } from "./normalize"
import {
  PopulationScope,
  RANK_STYLE,
  RampMode,
  SCHEMES,
  Scheme,
  colorFor,
  isRampScheme,
} from "./schemes"
import { clearStats, extractValue, isTopLevel, statsFor } from "./population"
import { Override, declarationCandidates } from "./overrides"

// Re-exported so `AgGridComponent.tsx` can invalidate the statistics cache
// ahead of a `redrawRows()` that is not preceded by `modelUpdated` — see
// `attachColorScaleInvalidation` below for the event-driven case, and the
// call sites in `AgGridComponent.tsx` for the config-only-rerun case this
// covers instead.
export { clearStats }

/** The key a declaration lives under inside `context`, at both levels.
 * Matches `st_aggrid/color_scale.py`'s COLOR_SCALE_CONTEXT_KEY. */
export const ST_COLOR_SCALE = "stColorScale"

/** Reserved key of the grid `context` that holds the reader's live choices —
 * a `Map<sourceColId, Override>` owned by `AgGridComponent` and injected by
 * `parseGridOptions`. It lives in `context` rather than on a colDef because
 * `updateGridOptions` installs fresh colDefs on every config rerun, and
 * because a pivot result column's `colDef.context` is a copy, not the source
 * column's object (measured 2026-09-20). `params.context`, by contrast, is the
 * grid's own object by identity. Matches `color_scale.py`'s
 * COLOR_SCALE_OVERRIDES_CONTEXT_KEY. */
export const ST_COLOR_SCALE_OVERRIDES = "stColorScaleOverrides"

/** What `AgGridComponent` hands to `parseGridOptions`: the live choices and
 * the callback a menu action reports to. */
export interface ColorScaleRuntime {
  overrides: Map<string, Override>
  onChange: (colId: string) => void
}

function gridDeclaration(gridContext: unknown): unknown {
  return (gridContext as Record<string, unknown> | undefined)?.[ST_COLOR_SCALE]
}

function ownDeclaration(colDef: ColDef | null | undefined): unknown {
  return (colDef?.context as Record<string, unknown> | undefined)?.[ST_COLOR_SCALE]
}

/** The grid-level opt-in for the reader's picker. */
export function isInteractive(gridContext: unknown): boolean {
  const declaration = gridDeclaration(gridContext)
  return (
    !!declaration &&
    typeof declaration === "object" &&
    (declaration as Record<string, unknown>).interactive === true
  )
}

/** Grid defaults merged with the column's own declaration — the two layers
 * below the reader's. The menu reads it to know whether an `anchor` exists. */
export function lowerLayers(
  colDef: ColDef | null | undefined,
  gridContext: unknown
): Record<string, unknown> {
  const own = ownDeclaration(colDef)
  const [merged] = declarationCandidates(
    gridDeclaration(gridContext),
    own === undefined || own === null || own === false ? true : own,
    undefined
  )
  return merged ?? {}
}

/** What an unpainted cell returns once a declaration has resolved. Not
 * `null`: ag-grid-react keeps a cell's previous inline style when the
 * callback returns nothing, so a cell that was painted in one model
 * generation and is not in the next would keep the old colour — for
 * `rank`, a stale second winner after a filter is cleared. Empty strings
 * remove exactly the two properties any built-in style can set and leave
 * the theme's own painting untouched. Always spread into a fresh object. */
const UNPAINTED: CellStyle = { backgroundColor: "", fontWeight: "" }

/** The raw, merged declaration. Every key optional; the shape Python's
 * validator accepts. */
interface Declaration {
  scheme?: unknown
  mode?: unknown
  scope?: unknown
  reverse?: unknown
  skip_non_positive?: unknown
  anchor?: unknown
  span?: unknown
  color?: unknown
}

/**
 * What a declaration resolves to. Discriminated on `kind` so the cell-style
 * function dispatches on one field and the compiler — not a runtime check —
 * guarantees a `fill` never reaches `statsFor` and an `anchor` always carries
 * its two numbers.
 */
export type ResolvedColorScale =
  | {
      kind: "ramp"
      scheme: Scheme
      mode: RampMode
      scope: PopulationScope
      reverse: boolean
      skipNonPositive: boolean
    }
  | {
      kind: "anchor"
      scheme: Scheme
      reverse: boolean
      skipNonPositive: boolean
      anchor: number
      span: number
    }
  | { kind: "rank"; scope: PopulationScope; reverse: boolean; skipNonPositive: boolean }
  | { kind: "fill"; color: string }

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value)
}

/**
 * Merge a column's declaration over the grid-level defaults and resolve it.
 *
 * A column is painted only when its own colDef carries an entry that is not
 * `false`; the grid level supplies defaults and never activates anything. The
 * merge is per key with the column winning. A key the resolved scheme does
 * not read is ignored — a grid default of `mode: "minmax"` must not switch
 * off a `fill` column.
 *
 * `mode: "anchor"` with no scheme at either level resolves to `diverging`:
 * the one asymmetry, because an anchored scale is almost always "above or
 * below a reference". An explicit scheme always wins.
 *
 * Python's `validate_color_scale_columns` implements the same rules and is
 * the copy that produces an actionable error. This one exists because grid
 * options do not always come from `GridOptionsBuilder`, and returning `null`
 * inside a cell renderer is a better failure than throwing there.
 *
 * The optional third argument is the reader's layer, the one the picker
 * writes. With it absent this is the two-layer rule above, unchanged. With it
 * present the candidate order — and the fallback that keeps a stale choice
 * from blanking a column the page still declares — is documented on
 * `declarationCandidates`.
 */
export function readColorScaleConfig(
  colDef: ColDef | null | undefined,
  gridContext: unknown,
  override?: Override
): ResolvedColorScale | null {
  const candidates = declarationCandidates(
    gridDeclaration(gridContext),
    ownDeclaration(colDef),
    override
  )
  for (const candidate of candidates) {
    const resolved = resolveMerged(candidate as Declaration)
    if (resolved) return resolved
  }
  return null
}

/** Turn one merged declaration into what it paints, or `null`. */
function resolveMerged(merged: Declaration): ResolvedColorScale | null {
  const schemeName =
    merged.scheme ?? (merged.mode === "anchor" ? "diverging" : undefined)

  if (schemeName === "fill") {
    return typeof merged.color === "string" && merged.color.trim() !== ""
      ? { kind: "fill", color: merged.color }
      : null
  }

  const scope: PopulationScope = merged.scope === "parent" ? "parent" : "level"
  const reverse = merged.reverse === true

  if (schemeName === "rank") {
    return {
      kind: "rank",
      scope,
      reverse,
      skipNonPositive: merged.skip_non_positive === true,
    }
  }

  if (!isRampScheme(schemeName)) return null
  const scheme = SCHEMES[schemeName]
  const skipNonPositive =
    typeof merged.skip_non_positive === "boolean"
      ? merged.skip_non_positive
      : scheme.defaultSkipNonPositive
  const mode: unknown = merged.mode ?? scheme.defaultMode

  if (mode === "anchor") {
    const { anchor, span } = merged
    if (!isFiniteNumber(anchor) || !isFiniteNumber(span) || span <= 0) return null
    return { kind: "anchor", scheme, reverse, skipNonPositive, anchor, span }
  }
  // Positive equality narrows `unknown` to the two literals; a negative
  // early return would leave `mode` as `unknown` for the object below.
  if (mode === "minmax" || mode === "zscore") {
    return { kind: "ramp", scheme, mode, scope, reverse, skipNonPositive }
  }
  return null
}

/** The column a choice is keyed by: a pivot result column stands for its
 * value column, so one choice on a metric reaches every pivot key. */
export function sourceColumnOf(
  colDef: ColDef | null | undefined,
  column: Column | null | undefined
): Column | null {
  return colDef?.pivotValueColumn ?? column ?? null
}

/** Resolve a displayed column including the reader's layer. The one place
 * that looks a choice up, shared by the cell style and the invalidation. */
export function resolveFor(
  colDef: ColDef | null | undefined,
  column: Column | null | undefined,
  gridContext: unknown
): ResolvedColorScale | null {
  const overrides = (gridContext as Record<string, unknown> | undefined)?.[
    ST_COLOR_SCALE_OVERRIDES
  ]
  const colId = sourceColumnOf(colDef, column)?.getColId()
  const override =
    overrides instanceof Map && colId !== undefined
      ? (overrides.get(colId) as Override | undefined)
      : undefined
  return readColorScaleConfig(colDef, gridContext, override)
}

/** The built-in `cellStyle`. Returns `null` only when no declaration resolves
 * **on a grid without the picker**.
 * Every other unpainted outcome returns `UNPAINTED` (see above) so a cell that
 * stops being painted actually loses its colour.
 *
 * `fill` is answered before the footer/pinned guard the other kinds share: a
 * fill marks a column as structural, and a stripe that stopped at the grand
 * total would be a visible regression against the styler it replaces. */
export function stColorScaleCellStyle(params: CellClassParams): CellStyle | null {
  const config = resolveFor(params.colDef, params.column, params.context)
  // `null` keeps ag-grid-react's previous inline style. Harmless while a
  // declaration can only ever be absent from the start; on an interactive grid
  // the reader can remove one ("None"), and the old colour would stay.
  if (!config) return isInteractive(params.context) ? { ...UNPAINTED } : null
  if (config.kind === "fill") return { backgroundColor: config.color }

  const node = params.node
  if (!node || node.footer || node.rowPinned != null) return { ...UNPAINTED }

  const value = extractValue(params.value)
  if (value === null) return { ...UNPAINTED }
  if (config.skipNonPositive && value <= 0) return { ...UNPAINTED }

  if (config.kind === "anchor") {
    let d = anchorD(config.anchor, config.span, value)
    if (config.reverse) d = -d
    // `-0 === 0`, so a reversed exact anchor stays unpainted too.
    if (d === 0) return { ...UNPAINTED }
    return {
      backgroundColor: colorFor(config.scheme, { mode: "anchor", raw: d, intensity: Math.abs(d) }),
    }
  }

  // Population-based from here on. Under parent scope a top-level row has no
  // siblings to be compared with — it is one of the groups.
  if (config.scope === "parent" && isTopLevel(node)) return { ...UNPAINTED }
  const stats = statsFor(
    params.api,
    params.column as Column,
    node,
    config.scope,
    config.skipNonPositive
  )
  if (!stats) return { ...UNPAINTED }

  if (config.kind === "rank") {
    // "Best of one" carries no information — the same rule the ramps apply
    // through their spread gates. Equality is exact: both sides come from the
    // same `getCellValue` walk, so the best *is* one of the values.
    if (stats.count < 2) return { ...UNPAINTED }
    const best = config.reverse ? stats.min : stats.max
    return value === best ? { ...RANK_STYLE } : { ...UNPAINTED }
  }

  let raw = config.mode === "minmax" ? minmaxT(stats, value) : zScore(stats, value)
  if (raw === null) return { ...UNPAINTED }
  // The dead zone and the uniformity gate are symmetric, so flipping after
  // them is equivalent to flipping before.
  if (config.reverse) raw = config.mode === "minmax" ? 1 - raw : -raw

  return {
    backgroundColor: colorFor(config.scheme, {
      mode: config.mode,
      raw,
      intensity: config.mode === "zscore" ? zIntensity(raw) : 0,
    }),
  }
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
 * On an interactive grid the `defaultColDef.cellStyle` warning is raised once
 * for the grid rather than once per column: in that mode the built-in is not
 * about one column's declaration, it is the picker itself being unavailable.
 *
 * The attached function does not close over the declaration; it re-reads it
 * per call from `params.colDef.context` and `params.context`. The reader's
 * picker relies on exactly that: a choice changes the override map and
 * refreshes, with nothing re-attached. On an interactive grid every column
 * without a caller-supplied `cellStyle` gets the built-in, declared or not.
 *
 * Pivot needs no handling here: AG-Grid copies `cellStyle` from the source
 * value colDef onto the pivot result column it generates.
 */
export function registerColorScales(
  gridOptions: GridOptions,
  debug: boolean = false
): GridOptions {
  const interactive = isInteractive(gridOptions.context)
  let warnedDefaultColDef = false

  eachColDef(gridOptions.columnDefs, (def) => {
    const declared = readColorScaleConfig(def, gridOptions.context) !== null
    // Without the picker: same predicate `paintedColumnIds` and
    // `stColorScaleCellStyle` use — a declaration that resolves to nothing
    // must not occupy the slot. With it, the slot has to exist *before* the
    // reader asks: a choice is a context mutation plus `refreshCells`, and
    // there is nothing to refresh on a column that carries no function.
    if (!declared && !interactive) return

    const source = callerCellStyleSource(def, gridOptions)
    if (source) {
      const colId = def.colId ?? def.field
      if (source === "defaultColDef.cellStyle") {
        if (interactive) {
          if (!warnedDefaultColDef) {
            warnedDefaultColDef = true
            console.warn(
              `[st_aggrid] This grid is interactive for colour scales, but ` +
                `defaultColDef.cellStyle wins for every column, so the built-in ` +
                `was not attached anywhere: nothing will be painted and the ` +
                `picker is unavailable.`
            )
          }
        } else {
          console.warn(
            `[st_aggrid] "${colId}" declares a colour scale, but defaultColDef.cellStyle ` +
              `wins for every column in this grid, so the built-in was not attached and ` +
              `"${colId}" will not be painted.`
          )
        }
      } else if (debug && declared) {
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
    .filter((column) => resolveFor(column.getColDef(), column, context) !== null)
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
 * `(column, level)` — or, under `scope: "parent"`, each `(column)` once for
 * every parent at once — pays a full `statsFor` walk of the entire model, one
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
