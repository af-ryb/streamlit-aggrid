/** Runnable check for `overrides.ts`. Run it with:
 *
 *     node st_aggrid/frontend/src/colorScales/__checks__/overrides.check.ts
 *
 * Same arrangement as `normalize.check.ts`: Node 22 strips the types, so the
 * layer arithmetic is tested without a JS test runner. What needs a live grid
 * is in `test/test_grid_color_scale_picker.py`.
 */
import assert from "node:assert/strict"
import {
  applyChoice,
  declarationCandidates,
  sanitizeState,
  serializeState,
} from "../overrides.ts"
import type { Override } from "../overrides.ts"

// --- sanitizeState: junk in, clean map out, never throws -------------------
for (const junk of [undefined, null, 7, "x", [], [["a", false]]]) {
  assert.equal(sanitizeState(junk).size, 0)
}
const clean = sanitizeState({
  a: false,
  b: { scheme: "diverging", mode: "zscore", reverse: true },
  c: { scheme: "fill" }, // not pickable: key dropped, entry kept as {}
  d: { scheme: "rainbow", mode: 3, reverse: "yes", scope: "parent" },
  e: true, // not an override
  f: "neutral",
  g: null,
})
assert.deepEqual([...clean.keys()], ["a", "b", "c", "d"])
assert.equal(clean.get("a"), false)
assert.deepEqual(clean.get("b"), { scheme: "diverging", mode: "zscore", reverse: true })
assert.deepEqual(clean.get("c"), {})
assert.deepEqual(clean.get("d"), {})

// The map owns its entries: mutating the input afterwards changes nothing.
const input = { a: { scheme: "neutral" } }
const owned = sanitizeState(input)
input.a.scheme = "rank"
assert.deepEqual(owned.get("a"), { scheme: "neutral" })

// --- serializeState: a plain, detached object ------------------------------
const plain = serializeState(clean)
assert.deepEqual(plain, {
  a: false,
  b: { scheme: "diverging", mode: "zscore", reverse: true },
  c: {},
  d: {},
})
;(plain.b as { scheme?: string }).scheme = "rank"
assert.deepEqual(clean.get("b"), { scheme: "diverging", mode: "zscore", reverse: true })
assert.deepEqual(serializeState(new Map()), {})

// --- applyChoice ------------------------------------------------------------
const map = new Map<string, Override>()
applyChoice(map, "m", { kind: "scheme", scheme: "neutral" }, false)
assert.deepEqual(map.get("m"), { scheme: "neutral" })
// Keys accumulate; nothing is normalised away.
applyChoice(map, "m", { kind: "mode", mode: "minmax" }, false)
applyChoice(map, "m", { kind: "reverse", reverse: true }, false)
assert.deepEqual(map.get("m"), { scheme: "neutral", mode: "minmax", reverse: true })
applyChoice(map, "m", { kind: "scheme", scheme: "diverging" }, false)
assert.deepEqual(map.get("m"), { scheme: "diverging", mode: "minmax", reverse: true })

// "none" on an undeclared column has nothing to switch off: the entry goes.
applyChoice(map, "m", { kind: "none" }, false)
assert.equal(map.has("m"), false)
// "none" on a declared column must outvote the declaration.
applyChoice(map, "d", { kind: "none" }, true)
assert.equal(map.get("d"), false)
// A choice after "none" starts from scratch, not from `false`.
applyChoice(map, "d", { kind: "reverse", reverse: true }, true)
assert.deepEqual(map.get("d"), { reverse: true })
applyChoice(map, "d", { kind: "reset" }, true)
assert.equal(map.has("d"), false)
// Reset on a column with no entry is a no-op, not an error.
applyChoice(map, "d", { kind: "reset" }, true)
assert.equal(map.size, 0)

// --- declarationCandidates --------------------------------------------------
const GRID = { scheme: "neutral", interactive: true }

// No override: exactly the two-layer behaviour that exists today.
assert.deepEqual(declarationCandidates(GRID, undefined, undefined), [])
assert.deepEqual(declarationCandidates(GRID, null, undefined), [])
assert.deepEqual(declarationCandidates(GRID, false, undefined), [])
assert.deepEqual(declarationCandidates(GRID, true, undefined), [GRID])
assert.deepEqual(declarationCandidates(undefined, { scheme: "rank" }, undefined), [
  { scheme: "rank" },
])
assert.deepEqual(declarationCandidates(GRID, { mode: "minmax" }, undefined), [
  { scheme: "neutral", interactive: true, mode: "minmax" },
])
// A non-object, non-true declaration contributes no keys (as today).
assert.deepEqual(declarationCandidates(GRID, 5, undefined), [GRID])

// `false` from the reader switches a declared column off.
assert.deepEqual(declarationCandidates(GRID, true, false), [])
// The page author's `false` outvotes the reader.
assert.deepEqual(declarationCandidates(GRID, false, { scheme: "rank" }), [])

// An override activates an undeclared column — one candidate, no fallback.
assert.deepEqual(declarationCandidates(GRID, undefined, { scheme: "rank" }), [
  { scheme: "rank", interactive: true },
])
// On a declared column the override wins per key, and the declaration alone
// is the fallback if the merge does not resolve.
assert.deepEqual(
  declarationCandidates(GRID, { mode: "minmax" }, { scheme: "diverging", mode: "anchor" }),
  [
    { scheme: "diverging", interactive: true, mode: "anchor" },
    { scheme: "neutral", interactive: true, mode: "minmax" },
  ]
)

console.log("overrides.check.ts: ok")
