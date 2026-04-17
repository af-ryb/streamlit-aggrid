import type { ColumnState } from "ag-grid-community"

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

    // initialRowGroupIndex needs rowGroup boolean for applyColumnState
    if ("initialRowGroupIndex" in def && !("rowGroup" in def)) {
      entry.rowGroup = def.initialRowGroupIndex != null
    }

    // Same for initialPivotIndex / initialPivot
    if (("initialPivotIndex" in def || "initialPivot" in def) && !("pivot" in def)) {
      entry.pivot =
        (def.initialPivotIndex != null) || (def.initialPivot === true)
    }

    if (hasStateProps) {
      entry.colId = colId
      result.push(entry as ColumnState)
    }
  }

  return result
}
