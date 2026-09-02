/** Runnable check for `schemes.ts`. Run it with:
 *
 *     node st_aggrid/frontend/src/colorScales/__checks__/schemes.check.ts
 *
 * The expected colours are the same anchors
 * `test/unit/test_color_scale_fixture.py` pins on the Python side; if these
 * two ever disagree, one of them transcribed a ramp wrong.
 */
import assert from "node:assert/strict"
import {
  MODE_NAMES,
  RANK_STYLE,
  SCHEME_NAMES,
  SCHEMES,
  SCOPE_NAMES,
  colorFor,
  isRampScheme,
} from "../schemes.ts"
import { zIntensity } from "../normalize.ts"

const Z = -1.4638501094227998 // metric_a = 100 against the 100..600 ramp

const minmax = (raw: number) => ({ mode: "minmax" as const, raw, intensity: 0 })
const zscore = (raw: number) => ({
  mode: "zscore" as const,
  raw,
  intensity: zIntensity(raw),
})

assert.equal(colorFor(SCHEMES.positive, minmax(0)), "rgba(29, 158, 117, 0.06)")
assert.equal(colorFor(SCHEMES.positive, minmax(1)), "rgba(29, 158, 117, 0.55)")
assert.equal(colorFor(SCHEMES.positive, minmax(0.4)), "rgba(29, 158, 117, 0.256)")

assert.equal(colorFor(SCHEMES.neutral, zscore(Z)), "rgba(51, 120, 200, 0.241)")
assert.equal(colorFor(SCHEMES.neutral, zscore(-0.87831006565368)), "rgba(51, 120, 200, 0.125)")
assert.equal(colorFor(SCHEMES.neutral, minmax(0)), "rgba(51, 120, 200, 0.08)")
assert.equal(colorFor(SCHEMES.neutral, minmax(1)), "rgba(51, 120, 200, 0.55)")

assert.equal(colorFor(SCHEMES.diverging, zscore(Z)), "rgba(233, 18, 15, 0.365)")
assert.equal(colorFor(SCHEMES.diverging, zscore(-Z)), "rgba(35, 183, 40, 0.365)")
assert.equal(colorFor(SCHEMES.diverging, minmax(0)), "rgba(225, 18, 15, 0.7)")
assert.equal(colorFor(SCHEMES.diverging, minmax(1)), "rgba(35, 175, 40, 0.7)")
assert.equal(colorFor(SCHEMES.diverging, minmax(0.4)), "rgba(237, 18, 15, 0.22)")

// s === 0 exactly. The sign test is `signed < 0`, so the midpoint takes the
// green branch; a `<=` would silently flip it to red.
assert.equal(colorFor(SCHEMES.diverging, minmax(0.5)), "rgba(35, 190, 40, 0.1)")

// The z >= 3 saturation arms. Nothing else in the feature reaches them: the
// e2e fixture's largest attainable |z| is about 1.52, so without these the
// caps have no regression protection at all.
assert.equal(colorFor(SCHEMES.neutral, zscore(-4)), "rgba(51, 120, 200, 0.55)")
assert.equal(colorFor(SCHEMES.diverging, zscore(4)), "rgba(35, 175, 40, 0.7)")
assert.equal(colorFor(SCHEMES.diverging, zscore(-4)), "rgba(225, 18, 15, 0.7)")

// positive has no piecewise ramp, so zscore interpolates its own endpoints.
assert.equal(colorFor(SCHEMES.positive, zscore(Z)), "rgba(29, 158, 117, 0.299)")

// Defaults, which `index.ts` fills in when the declaration omits them.
assert.equal(SCHEMES.neutral.defaultMode, "zscore")
assert.equal(SCHEMES.positive.defaultMode, "minmax")
assert.equal(SCHEMES.diverging.defaultMode, "zscore")
assert.equal(SCHEMES.neutral.defaultSkipNonPositive, true)
assert.equal(SCHEMES.positive.defaultSkipNonPositive, false)
assert.equal(SCHEMES.diverging.defaultSkipNonPositive, true)

// These must equal st_aggrid/color_scale.py's COLOR_SCALE_SCHEMES and
// COLOR_SCALE_MODES, which test/unit/test_public_exports.py pins on the
// Python side. Nothing mechanical keeps the two languages in step.
assert.deepEqual(SCHEME_NAMES, ["neutral", "positive", "diverging", "rank", "fill"])
assert.deepEqual(MODE_NAMES, ["minmax", "zscore", "anchor"])
assert.deepEqual(SCOPE_NAMES, ["level", "parent"])

// Anchor mode: `raw` is the clamped signed deviation, `intensity` its
// magnitude, and alpha is the scheme's *linear* ramp — never `zRamp`. The
// same numbers `test/unit/test_color_scale_fixture.py` pins.
const anchor = (raw: number) => ({ mode: "anchor" as const, raw, intensity: Math.abs(raw) })

assert.equal(colorFor(SCHEMES.diverging, anchor(-0.5)), "rgba(233, 18, 15, 0.4)")
assert.equal(colorFor(SCHEMES.diverging, anchor(0.5)), "rgba(35, 183, 40, 0.4)")
assert.equal(colorFor(SCHEMES.diverging, anchor(1)), "rgba(35, 175, 40, 0.7)")
assert.equal(colorFor(SCHEMES.diverging, anchor(-1)), "rgba(225, 18, 15, 0.7)")
// zRamp provably not consulted: diverging's z-ramp at |z| = 0.5 is 0.1, the
// linear ramp at u = 0.5 is 0.4. The line above holds 0.4.
assert.equal(colorFor(SCHEMES.diverging, anchor(-0.09999999999999998)), "rgba(239, 18, 15, 0.16)")
assert.equal(colorFor(SCHEMES.diverging, anchor(0.10000000000000009)), "rgba(35, 189, 40, 0.16)")
assert.equal(colorFor(SCHEMES.positive, anchor(1)), "rgba(29, 158, 117, 0.55)")
assert.equal(colorFor(SCHEMES.positive, anchor(-1)), "rgba(29, 158, 117, 0.55)")
assert.equal(colorFor(SCHEMES.positive, anchor(-0.5)), "rgba(29, 158, 117, 0.305)")
assert.equal(colorFor(SCHEMES.positive, anchor(0.25)), "rgba(29, 158, 117, 0.183)")
assert.equal(colorFor(SCHEMES.neutral, anchor(1)), "rgba(51, 120, 200, 0.55)")
assert.equal(colorFor(SCHEMES.neutral, anchor(-0.5)), "rgba(51, 120, 200, 0.315)")

// rank's highlight is derived from diverging's saturated green.
assert.deepEqual(RANK_STYLE, { backgroundColor: "rgba(35, 175, 40, 0.35)", fontWeight: 600 })

// The ramp predicate must not be fooled by Object.prototype.
assert.ok(isRampScheme("neutral"))
assert.ok(!isRampScheme("rank"))
assert.ok(!isRampScheme("fill"))
assert.ok(!isRampScheme("toString"))
assert.ok(!isRampScheme(undefined))

console.log("schemes.check.ts ok")
