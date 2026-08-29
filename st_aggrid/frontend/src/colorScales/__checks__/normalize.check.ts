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
import { minmaxT, popStats, zIntensity, zScore } from "../normalize.ts"

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

// Uniformity floor uses |mean|, so a negative-mean column still paints.
const negative = popStats([-100, -200, -300, -400, -500, -600])
assert.ok(zScore(negative, -600) !== null)

// mean === 0 skips the floor rather than dividing by zero.
assert.ok(zScore(popStats([-10, 0, 10]), 10) !== null)

assert.equal(zIntensity(0), 0)
assert.equal(zIntensity(-1.5), 0.5)
assert.equal(zIntensity(9), 1)

console.log("normalize.check.ts ok")
