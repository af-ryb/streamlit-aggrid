/**
 * The reader's layer of a colour-scale declaration.
 *
 * Resolution has three layers: grid-level defaults, the column's own
 * declaration, and what the reader picked from a menu. This module owns the
 * third one's arithmetic and the order in which merged declarations are tried.
 * It imports nothing, so `__checks__/overrides.check.ts` runs it under plain
 * `node`; turning a merged declaration into a `ResolvedColorScale` stays in
 * `index.ts`.
 *
 * An override stores only what the reader touched, never a full declaration,
 * so a page that later changes its defaults still reaches every column the
 * reader left alone.
 */

/** `false` — unpainted whatever the column declares. An object — merged per
 * key over the two lower layers; activates a column with no declaration. */
export type Override = false | { scheme?: string; mode?: string; reverse?: boolean }

/**
 * One menu action.
 *
 * The mode variant carries an optional `scheme` because a mode on its own does
 * not always name a scale. A declaration of `mode: "anchor"` and nothing else
 * is complete — `index.ts` resolves it to `diverging` — but store `{mode:
 * "zscore"}` over it and the merge names no scheme at all, resolves to
 * nothing, and the declaration-only fallback repaints the column exactly as it
 * was. The menu therefore passes the scheme it resolved with whenever the
 * lower layers do not spell one out.
 */
export type Choice =
  | { kind: "none" }
  | { kind: "reset" }
  | { kind: "scheme"; scheme: string }
  | { kind: "mode"; mode: string; scheme?: string }
  | { kind: "reverse"; reverse: boolean }

/** `fill` is absent on purpose: it needs a colour, which no menu offers. */
export const PICKABLE_SCHEMES: readonly string[] = [
  "neutral",
  "positive",
  "diverging",
  "rank",
]
const PICKABLE_MODES: readonly string[] = ["minmax", "zscore", "anchor"]

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}

/**
 * The guard copy of Python's `validate_color_scale_state`. Python raises on a
 * malformed state because that is where a developer can act on it; here a bad
 * entry is dropped, because throwing while a grid mounts helps nobody. Returns
 * a map that owns its entries.
 */
export function sanitizeState(raw: unknown): Map<string, Override> {
  const state = new Map<string, Override>()
  if (!isPlainObject(raw)) return state

  for (const [colId, entry] of Object.entries(raw)) {
    if (entry === false) {
      state.set(colId, false)
      continue
    }
    if (!isPlainObject(entry)) continue

    const override: Exclude<Override, false> = {}
    if (typeof entry.scheme === "string" && PICKABLE_SCHEMES.includes(entry.scheme)) {
      override.scheme = entry.scheme
    }
    if (typeof entry.mode === "string" && PICKABLE_MODES.includes(entry.mode)) {
      override.mode = entry.mode
    }
    if (typeof entry.reverse === "boolean") override.reverse = entry.reverse
    state.set(colId, override)
  }
  return state
}

/** A plain, detached object — what the collector posts to Python. */
export function serializeState(map: Map<string, Override>): Record<string, Override> {
  const out: Record<string, Override> = {}
  for (const [colId, entry] of map) out[colId] = entry === false ? false : { ...entry }
  return out
}

/**
 * The menu's one write path.
 *
 * "none" writes `false` only where there is a declaration to outvote; on an
 * undeclared column there is nothing to switch off, and deleting the entry
 * keeps the saved state free of noise. Keys accumulate as written and are
 * never normalised away — "reset" is the only thing that removes them.
 */
export function applyChoice(
  map: Map<string, Override>,
  colId: string,
  choice: Choice,
  hasOwnDeclaration: boolean
): void {
  if (choice.kind === "reset") {
    map.delete(colId)
    return
  }
  if (choice.kind === "none") {
    if (hasOwnDeclaration) map.set(colId, false)
    else map.delete(colId)
    return
  }

  const current = map.get(colId)
  const next: Exclude<Override, false> = current ? { ...current } : {}
  if (choice.kind === "scheme") next.scheme = choice.scheme
  else if (choice.kind === "mode") {
    next.mode = choice.mode
    // Pinning the scheme the mode was chosen against; see `Choice`.
    if (choice.scheme !== undefined) next.scheme = choice.scheme
  } else next.reverse = choice.reverse
  map.set(colId, next)
}

/**
 * The merged declarations to try, in order; the first that resolves wins and
 * an empty list means "unpainted".
 *
 * With `override === undefined` this is exactly the two-layer rule that
 * predates the picker: a column is painted only when its own declaration is
 * present and not `false`. An override object adds a first candidate — and is
 * the only candidate on an undeclared column. The declaration-only fallback is
 * what keeps a stale saved choice (say `mode: "anchor"` on a column that has
 * since lost its `anchor`) from blanking a column the page still declares.
 *
 * The page author's `false` outvotes the reader: it is an explicit "not this
 * column", and the menu does not offer such a column either.
 */
export function declarationCandidates(
  gridDefaults: unknown,
  own: unknown,
  override: Override | undefined
): Record<string, unknown>[] {
  if (own === false || override === false) return []

  const hasOwn = own !== undefined && own !== null
  if (!hasOwn && override === undefined) return []

  const base = isPlainObject(gridDefaults) ? gridDefaults : {}
  const declared = isPlainObject(own) ? own : {}

  const candidates: Record<string, unknown>[] = []
  if (override !== undefined) candidates.push({ ...base, ...declared, ...override })
  if (hasOwn) candidates.push({ ...base, ...declared })
  return candidates
}
