/** Runnable check for `normalize.ts`. Run it with:
 *
 *     node st_aggrid/frontend/src/colorScales/__checks__/normalize.check.ts
 *
 * Node 22 strips the types and runs the module directly, so the pure
 * arithmetic gets a fast test cycle without adding a test runner to a package
 * that ships to the browser. Anything that needs a live grid is covered by
 * `test/test_grid_color_scale.py` instead.
 */
import assert from "node:assert/strict"
import { anchorD, minmaxT, popStats, zIntensity, zScore } from "../normalize.ts"

const RAMP = [100, 200, 300, 400, 500, 600]
const stats = popStats(RAMP)

// Population standard deviation (divisor N), matching the JavaScript being
// replaced: sqrt(175000 / 6).
assert.equal(stats.count, 6)
assert.equal(stats.min, 100)
assert.equal(stats.max, 600)
assert.equal(stats.mean, 350)
assert.equal(stats.sd, 170.78251276599332)

assert.equal(minmaxT(stats, 100), 0)
assert.equal(minmaxT(stats, 600), 1)
assert.equal(minmaxT(stats, 300), 0.4)

// No spread: nothing to show.
assert.equal(minmaxT(popStats([7, 7, 7]), 7), null)
assert.equal(zScore(popStats([7, 7, 7]), 7), null)

// Dead zone: |z| = 0.29277 for 300.
assert.equal(zScore(stats, 300), null)
assert.equal(zScore(stats, 400), null)
assert.ok(Math.abs(zScore(stats, 100)! + 1.4638501094227998) < 1e-12)

// The dead-zone boundary, exactly. mean 1.5, sd 0.5, so 1.75 is |z| = 0.5 to
// the bit and 1.7 is inside it. The gate is a strict `<`, so the boundary
// value itself paints — that asymmetry is what these two lines hold.
const twoElement = popStats([1, 2])
assert.equal(zScore(twoElement, 1.75), 0.5)
assert.equal(zScore(twoElement, 1.7), null)

// Uniformity floor uses |mean|, so a negative-mean column still paints.
const negative = popStats([-100, -200, -300, -400, -500, -600])
assert.ok(zScore(negative, -600) !== null)

// mean === 0 skips the floor rather than dividing by zero.
assert.ok(zScore(popStats([-10, 0, 10]), 10) !== null)

// Near-uniform but NOT constant: sd is 2.05e-4, so this passes the sd === 0
// guard and is stopped by the coefficient-of-variation floor specifically.
// `popStats([7, 7, 7])` above cannot reach the floor — it returns one line
// earlier — so this is the only thing holding CV_FLOOR in place.
const nearUniform = popStats([1000, 1000.0005, 1000.0002])
assert.ok(nearUniform.sd > 0)
assert.equal(zScore(nearUniform, 1000.0005), null)

assert.equal(zIntensity(0), 0)
assert.equal(zIntensity(-1.5), 0.5)
assert.equal(zIntensity(9), 1)

// Anchored deviation, in spans, clamped. The sign survives; the exact anchor
// is 0 and `index.ts` leaves it unpainted.
assert.equal(anchorD(1, 1, 0.5), -0.5)
assert.equal(anchorD(1, 1, 1.5), 0.5)
assert.equal(anchorD(1, 1, 1), 0)
assert.equal(anchorD(1, 1, 2.5), 1) // clamped
assert.equal(anchorD(1, 1, -3), -1) // clamped
assert.equal(anchorD(1, 0.5, 1.25), 0.5) // span scales the deviation
assert.equal(anchorD(100, 40, 110), 0.25)

console.log("normalize.check.ts ok")
