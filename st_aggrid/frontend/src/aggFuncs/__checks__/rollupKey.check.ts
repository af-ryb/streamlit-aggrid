/** Runnable check for `rollupKey.ts`. Run it with:
 *
 *     node st_aggrid/frontend/src/aggFuncs/__checks__/rollupKey.check.ts
 *
 * Same arrangement as `colorScales/__checks__`: Node 22 strips the types.
 * The rules mirror AG-Grid 36.1's `getKeyForNode` and empty-group handling
 * (cited in the spec); what needs a live grid is in `test/test_grid_rollup.py`.
 */
import assert from "node:assert/strict"
import { canonicalKey, nodeKey, toGroupKey } from "../rollupKey.ts"
import type { KeyNode } from "../rollupKey.ts"

// --- toGroupKey: AG-Grid's key for a value ---------------------------------
assert.equal(toGroupKey("1.19.1"), "1.19.1")
assert.equal(toGroupKey(7), "7") // a number groups under its string
assert.equal(toGroupKey(true), "true")
assert.equal(toGroupKey(null), "") // NULL groups under ""
assert.equal(toGroupKey(undefined), "")
assert.equal(toGroupKey(""), "") // ...and so does the empty string
assert.equal(toGroupKey("x", (v) => `k:${v}`), "k:x") // keyCreator wins
assert.equal(toGroupKey("x", () => null), "") // a null key is still ""
assert.equal(toGroupKey("x", () => 3), "3")

// --- canonicalKey: order-free ----------------------------------------------
assert.equal(
  canonicalKey({ event_date: "2026-10-01", app_version: "1.19.1" }),
  canonicalKey({ app_version: "1.19.1", event_date: "2026-10-01" })
)
assert.equal(canonicalKey({}), "[]")
assert.notEqual(canonicalKey({ a: "" }), canonicalKey({})) // NULL ≠ absent

// --- nodeKey: the ancestry -------------------------------------------------
const column = (field: string | undefined, colId: string) => ({
  getColId: () => colId,
  getColDef: () => ({ field }),
})
const root: KeyNode = { level: -1, key: null, parent: null, rowGroupColumn: null }
const day: KeyNode = {
  level: 0,
  key: "2026-10-01",
  parent: root,
  rowGroupColumn: column("event_date", "event_date"),
}
const version: KeyNode = {
  level: 1,
  key: "1.19.1",
  parent: day,
  rowGroupColumn: column("app_version", "app_version"),
}
const nullVersion: KeyNode = { ...version, key: "" }
const byColId: KeyNode = {
  level: 0,
  key: "x",
  parent: root,
  rowGroupColumn: column(undefined, "computed"),
}

assert.deepEqual(nodeKey(root), {})
assert.deepEqual(nodeKey(null), {})
assert.deepEqual(nodeKey(day), { event_date: "2026-10-01" })
assert.deepEqual(nodeKey(version), { event_date: "2026-10-01", app_version: "1.19.1" })
assert.deepEqual(nodeKey(nullVersion), { event_date: "2026-10-01", app_version: "" })
assert.deepEqual(nodeKey(byColId), { computed: "x" }) // no field → colId
// A dimension named like an Object.prototype member is still a dimension.
const ctor: KeyNode = {
  level: 0,
  key: "x",
  parent: root,
  rowGroupColumn: column("constructor", "constructor"),
}
assert.deepEqual(nodeKey(ctor), { constructor: "x" })
assert.equal(
  canonicalKey(nodeKey(version)),
  canonicalKey({ app_version: "1.19.1", event_date: "2026-10-01" })
)

console.log("rollupKey.check.ts: ok")
