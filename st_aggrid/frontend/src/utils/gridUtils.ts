import type { ColumnState, GridState } from "ag-grid-community"

type CSSDict = { [key: string]: { [key: string]: string } }

export function getCSS(styles: CSSDict): string {
  var css = []
  for (let selector in styles) {
    let style = selector + " {"
    for (let prop in styles[selector]) {
      style += prop + ": " + styles[selector][prop] + ";"
    }
    style += "}"
    css.push(style)
  }
  return css.join("\n")
}

export function addCustomCSS(custom_css: CSSDict): void {
  var css = getCSS(custom_css)
  var styleSheet = document.createElement("style")
  styleSheet.type = "text/css"
  styleSheet.innerText = css
  document.head.appendChild(styleSheet)
}

export function injectProAssets(jsCode?: string, cssCode?: string) {
  if (jsCode) {
    const script = document.createElement("script")
    script.textContent = jsCode
    document.body.appendChild(script)
  }
  if (cssCode) {
    const style = document.createElement("style")
    style.textContent = cssCode
    document.head.appendChild(style)
  }
}

export function parseJsCodeFromPython(v: string) {
  const JS_PLACEHOLDER = "::JSCODE::"
  const funcReg = new RegExp(`${JS_PLACEHOLDER}(.*?)${JS_PLACEHOLDER}`, "s")
  let match = funcReg.exec(v)
  if (match) {
    const funcStr = match[1]
    // eslint-disable-next-line
    return new Function("return " + funcStr)()
  } else {
    return v
  }
}

/**
 * Mapping from colDef properties to ColumnState properties.
 * "initial*" variants are mapped to their runtime equivalents because
 * AG-Grid only reads them on column creation, not on update.
 *
 * Ordered so non-initial variants come first — the extraction loop
 * skips initial variants when the non-initial is already set.
 */
const COL_DEF_TO_STATE: [string, keyof ColumnState][] = [
  ["hide", "hide"],
  ["rowGroup", "rowGroup"],
  ["rowGroupIndex", "rowGroupIndex"],
  ["initialRowGroupIndex", "rowGroupIndex"],
  ["pivot", "pivot"],
  ["pivotIndex", "pivotIndex"],
  ["initialPivot", "pivot"],
  ["initialPivotIndex", "pivotIndex"],
  ["aggFunc", "aggFunc"],
  ["pinned", "pinned"],
]

/**
 * Walk a columnDefs array (which may contain column groups with `children`)
 * and extract ColumnState entries for columns that have state-relevant
 * properties explicitly set.
 *
 * Only properties present in the colDef are included in each entry, so
 * omitted properties won't accidentally reset AG-Grid's internal state.
 *
 * Returns an array suitable for `gridApi.applyColumnState({ state: ... })`.
 */
export function extractColumnStateFromDefs(
  columnDefs: any[] | undefined
): ColumnState[] {
  if (!columnDefs || !Array.isArray(columnDefs)) return []

  const result: ColumnState[] = []

  for (const def of columnDefs) {
    if (def.children && Array.isArray(def.children)) {
      result.push(...extractColumnStateFromDefs(def.children))
      continue
    }

    const colId = def.colId ?? def.field
    if (!colId) continue

    const entry: Record<string, any> = {}
    let hasStateProps = false

    for (const [defProp, stateProp] of COL_DEF_TO_STATE) {
      if (!(defProp in def)) continue
      // Non-initial variant takes precedence — skip initial if already set
      if (defProp.startsWith("initial") && stateProp in entry) continue

      entry[stateProp] = def[defProp]
      hasStateProps = true
    }

    // Derive the rowGroup boolean from the effective index. Explicit
    // rowGroupIndex wins over initialRowGroupIndex even when it's null —
    // otherwise we'd emit the contradictory state `{rowGroupIndex: null,
    // rowGroup: true}` that leaves the column stuck as a row group.
    if (!("rowGroup" in def) && ("rowGroupIndex" in def || "initialRowGroupIndex" in def)) {
      const effectiveIdx =
        "rowGroupIndex" in def ? def.rowGroupIndex : def.initialRowGroupIndex
      entry.rowGroup = effectiveIdx != null
      hasStateProps = true
    }

    // Same logic for pivot — explicit pivotIndex (including null) wins.
    if (!("pivot" in def) && ("pivotIndex" in def || "initialPivotIndex" in def || "initialPivot" in def)) {
      const effectiveIdx =
        "pivotIndex" in def ? def.pivotIndex : def.initialPivotIndex
      entry.pivot = effectiveIdx != null || def.initialPivot === true
      hasStateProps = true
    }

    if (hasStateProps) {
      entry.colId = colId
      result.push(entry as ColumnState)
    }
  }

  return result
}

/**
 * Extract ordered row group column IDs from columnDefs.
 * Returns column IDs sorted by their group index, suitable for
 * `gridApi.setRowGroupColumns()`.
 */
export function extractRowGroupColumns(
  columnDefs: any[] | undefined
): string[] {
  if (!columnDefs || !Array.isArray(columnDefs)) return []

  const groups: { colId: string; index: number }[] = []

  function walk(defs: any[]) {
    for (const def of defs) {
      if (def.children && Array.isArray(def.children)) {
        walk(def.children)
        continue
      }
      const colId = def.colId ?? def.field
      if (!colId) continue

      // rowGroupIndex takes precedence over initialRowGroupIndex. Python
      // passes `null` to mean "not grouped", so use `in` rather than `??`
      // to distinguish explicit-null from not-set — otherwise the nullish
      // fallback would re-group the column on the ungroup transition.
      const idx =
        "rowGroupIndex" in def ? def.rowGroupIndex : def.initialRowGroupIndex
      if (idx != null) {
        groups.push({ colId, index: idx })
      } else if (def.rowGroup === true) {
        groups.push({ colId, index: groups.length })
      }
    }
  }

  walk(columnDefs)
  groups.sort((a, b) => a.index - b.index)
  return groups.map((g) => g.colId)
}

/**
 * Extract ordered row group column IDs from a ColumnState[] array — i.e. the
 * shape produced by `gridApi.getColumnState()` and round-tripped through the
 * `columns_state` prop. `applyColumnState` alone does not reliably (re)build
 * row groups while pivot mode is on, so callers pair it with
 * `gridApi.setRowGroupColumns()` fed by this function.
 */
export function extractRowGroupColumnsFromState(
  state: ColumnState[] | null | undefined
): string[] {
  if (!state || !Array.isArray(state)) return []

  const groups = state
    .filter((c) => c.rowGroup === true || c.rowGroupIndex != null)
    .map((c) => ({
      colId: c.colId as string,
      index: c.rowGroupIndex ?? Number.MAX_SAFE_INTEGER,
    }))

  groups.sort((a, b) => a.index - b.index)
  return groups.map((g) => g.colId)
}

/**
 * Convert a `ColumnState[]` (the shape produced by `gridApi.getColumnState()`
 * and round-tripped through the `columns_state` prop) into an AG-Grid
 * `GridState`, so saved column layout can be applied at grid *creation* via the
 * `initialState` prop — before the first paint — instead of in `onGridReady`
 * after the grid has already rendered its default columns (which causes a
 * visible column flicker).
 *
 * `partialColumnState` is intentionally left unset (complete state): a value
 * column that is present in the colDefs but absent from `aggregationModel` is
 * cleared at creation, so a column the saved state hides never flashes into
 * view. (Tradeoff: a metric column added *after* a view was saved is hidden
 * until the view is re-saved — the project's accepted "re-save to migrate"
 * drift behaviour.)
 *
 * Only the Tier A sections are emitted (visibility / order / sizing / pinning /
 * sort / row-group / pivot / aggregation). Filters, group expansion and
 * scroll/focus are out of scope.
 */
export function columnStateToInitialState(
  state: ColumnState[] | null | undefined,
  pivotMode?: boolean
): GridState | undefined {
  if (!state || !Array.isArray(state) || state.length === 0) return undefined

  const colIds = (cs: ColumnState[]): string[] =>
    cs.map((c) => c.colId).filter((id): id is string => !!id)

  const initial: GridState = {}

  const orderedColIds = colIds(state)
  if (orderedColIds.length > 0) initial.columnOrder = { orderedColIds }

  const hiddenColIds = colIds(state.filter((c) => c.hide === true))
  if (hiddenColIds.length > 0) initial.columnVisibility = { hiddenColIds }

  const columnSizingModel = state
    .filter((c) => c.colId && c.width != null)
    .map((c) => ({ colId: c.colId as string, width: c.width as number }))
  if (columnSizingModel.length > 0)
    initial.columnSizing = { columnSizingModel }

  const leftColIds = colIds(
    state.filter((c) => c.pinned === "left" || c.pinned === true)
  )
  const rightColIds = colIds(state.filter((c) => c.pinned === "right"))
  if (leftColIds.length > 0 || rightColIds.length > 0)
    initial.columnPinning = { leftColIds, rightColIds }

  const sortModel = state
    .filter((c) => c.colId && c.sort != null)
    .slice()
    .sort((a, b) => (a.sortIndex ?? 0) - (b.sortIndex ?? 0))
    .map((c) => ({ colId: c.colId as string, sort: c.sort as "asc" | "desc" }))
  if (sortModel.length > 0) initial.sort = { sortModel }

  const groupColIds = extractRowGroupColumnsFromState(state)
  if (groupColIds.length > 0) initial.rowGroup = { groupColIds }

  // Only named aggregation functions can live in grid state; non-string
  // aggFuncs (inline JS) and cleared columns (null) are omitted.
  const aggregationModel = state
    .filter((c) => c.colId && typeof c.aggFunc === "string")
    .map((c) => ({ colId: c.colId as string, aggFunc: c.aggFunc as string }))
  if (aggregationModel.length > 0)
    initial.aggregation = { aggregationModel }

  const pivotColIds = colIds(
    state
      .filter((c) => c.pivot === true || c.pivotIndex != null)
      .slice()
      .sort(
        (a, b) =>
          (a.pivotIndex ?? Number.MAX_SAFE_INTEGER) -
          (b.pivotIndex ?? Number.MAX_SAFE_INTEGER)
      )
  )
  // pivotMode activation is driven by gridOptions.pivotMode (the caller passes
  // it in), NOT inferred from the presence of pivot columns: a column can be
  // configured as a pivot column while pivot mode is off. Default to `false`
  // when the option is absent so a saved view never force-enables pivot mode.
  if (pivotColIds.length > 0)
    initial.pivot = { pivotMode: pivotMode ?? false, pivotColIds }

  return Object.keys(initial).length > 0 ? initial : undefined
}
