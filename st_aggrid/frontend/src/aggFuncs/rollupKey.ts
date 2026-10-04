/**
 * The key a `stRollup` total is looked up by: a group's unordered set of
 * `{field: groupKey}` pairs.
 *
 * Pure and import-free, so `__checks__/rollupKey.check.ts` runs it under plain
 * Node. Every rule here reproduces what AG-Grid 36.1 does when it groups —
 * the spec cites the compiled code for each — because a totals row matches a
 * group only if both sides produce the same string.
 */

export type KeyCreator = (value: unknown) => unknown

/** The part of an AG-Grid `RowNode` the ancestry walk reads. Structural, so
 * this module needs no AG-Grid import. */
export interface KeyNode {
  level: number
  key: string | null
  parent: KeyNode | null
  rowGroupColumn?: { getColId(): string; getColDef(): { field?: string } } | null
}

/**
 * AG-Grid's group key for a value: `getKeyForNode` (the column's
 * `keyCreator` when given, else a string as is, else `String(value)`), then
 * the empty-group rule — `null`, `undefined` and `""` all group under `""`
 * when `groupAllowUnbalanced` is off. A real NULL is therefore `""`: present
 * in the key, unlike a rolled-up level, which is absent from it.
 */
export function toGroupKey(value: unknown, keyCreator?: KeyCreator | null): string {
  const result = keyCreator ? keyCreator(value) : value
  if (result == null) return ""
  return typeof result === "string" ? result : String(result)
}

/** Pairs sorted by field name, then serialised. Order-free on purpose: a
 * panel that reorders or drops a grouping level must find its totals without
 * a re-query. */
export function canonicalKey(pairs: Record<string, string>): string {
  return JSON.stringify(
    Object.keys(pairs)
      .sort()
      .map((field) => [field, pairs[field]])
  )
}

/** A group's pairs, from the node up to the root. The field is the grouping
 * column's `field` (the row-data name the totals use), falling back to its
 * colId. The root — the grand total — yields `{}`. */
export function nodeKey(node: KeyNode | null | undefined): Record<string, string> {
  const pairs: Record<string, string> = {}
  for (let current = node; current && current.level >= 0; current = current.parent) {
    const column = current.rowGroupColumn
    if (!column) continue
    const field = column.getColDef().field ?? column.getColId()
    if (!Object.prototype.hasOwnProperty.call(pairs, field)) pairs[field] = current.key ?? ""
  }
  return pairs
}
