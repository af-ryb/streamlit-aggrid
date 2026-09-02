/** The three built-in palettes, and the two non-ramp schemes.
 *
 * Each ramp reproduces one of the hand-written stylers the feature first
 * replaced, exactly: `neutral` the blue statistical wash from `funnel_saj`,
 * `positive` the green min/max ramp from `payers_intelligence`, `diverging`
 * the red/green split from the cohort report. `rank` (the best value in a
 * population, and nothing else) and `fill` (one constant colour) are not
 * palettes; they are listed in `SCHEME_NAMES` so Python and the frontend
 * agree on the full set, and resolved in `index.ts`.
 *
 * Two invariants hold for all three ramps. The fill is always `rgba(...)`
 * over the cell's own background and never an opaque colour — an opaque
 * ramp paints a light cell under the dark theme's light text and the number
 * disappears, which is a bug that already shipped once. And `diverging`
 * reaches alpha 0.7, above the 0.55 the other two stop at; that is what the
 * cohort report draws today, and it stays a named endpoint here so changing
 * it later is one edit.
 *
 * Imports nothing, so `__checks__/schemes.check.ts` can run it under `node`.
 */

export type RampSchemeName = "neutral" | "positive" | "diverging"
export type SchemeName = RampSchemeName | "rank" | "fill"
/** The modes a ramp scheme runs in. `anchor` consults no population. */
export type ColorScaleMode = "minmax" | "zscore" | "anchor"
/** The population-based modes — the only ones a scheme can default to. */
export type RampMode = "minmax" | "zscore"
/** What a population-based scheme is compared against. */
export type PopulationScope = "level" | "parent"

/** Must stay in step with `st_aggrid/color_scale.py`'s COLOR_SCALE_SCHEMES /
 * COLOR_SCALE_MODES / COLOR_SCALE_SCOPES, which
 * `test/unit/test_public_exports.py` pins. */
export const SCHEME_NAMES: readonly SchemeName[] = [
  "neutral",
  "positive",
  "diverging",
  "rank",
  "fill",
]
export const MODE_NAMES: readonly ColorScaleMode[] = ["minmax", "zscore", "anchor"]
export const SCOPE_NAMES: readonly PopulationScope[] = ["level", "parent"]

export interface Normalized {
  mode: ColorScaleMode
  /** `minmax`: `t` in `[0, 1]`. `zscore`: the signed z. `anchor`: the
   * clamped signed deviation `d` in `[-1, 1]`. */
  raw: number
  /** `zscore`: `zIntensity(z)`. `anchor`: `|d|`. Ignored under `minmax`,
   * where the intensity depends on whether the scheme is diverging and so is
   * derived from `raw` here. */
  intensity: number
}

export interface Scheme {
  name: RampSchemeName
  defaultMode: RampMode
  defaultSkipNonPositive: boolean
  /** Endpoints of the linear ramp, used whenever `zRamp` does not apply. Not
   * invented numbers: they are the endpoints of each scheme's own piecewise
   * ramp, so a non-default `scheme x mode` pairing stays inside the palette
   * the scheme already draws. */
  alphaMin: number
  alphaMax: number
  /** `true` when the scheme splits below/above rather than running one hue. */
  diverging: boolean
  /** Alpha as a function of `|z|`, when the scheme reproduces a piecewise
   * ramp. Absent means the linear `alphaMin..alphaMax` ramp is used in both
   * population modes. Never consulted under `anchor`: a z-ramp is a z-score
   * shape and has no meaning on a linear deviation. */
  zRamp?: (absZ: number) => number
  /** `sign` is -1 below the midpoint and +1 at or above it; `u` is the
   * intensity in `[0, 1]`. */
  rgb: (sign: number, u: number) => [number, number, number]
}

/** `floor(x + 0.5)` — `Math.round`'s exact semantics, spelled out because the
 * Python fixture that owns the expected colours must round the same way, and
 * Python's built-in `round` is half-to-even. */
function halfUp(x: number): number {
  return Math.floor(x + 0.5)
}

export const SCHEMES: Record<RampSchemeName, Scheme> = {
  neutral: {
    name: "neutral",
    defaultMode: "zscore",
    defaultSkipNonPositive: true,
    alphaMin: 0.08,
    alphaMax: 0.55,
    diverging: false,
    // Discontinuous at |z| = 1 (0.14 -> 0.2) and at |z| = 3 (0.319 -> 0.55).
    // Reproduced as-is: smoothing it is a product decision, not this one.
    zRamp: (z) =>
      z < 1 ? 0.08 + 0.12 * (z - 0.5) : z < 3 ? 0.2 + 0.25 * Math.log10(z) : 0.55,
    rgb: () => [51, 120, 200],
  },
  positive: {
    name: "positive",
    defaultMode: "minmax",
    defaultSkipNonPositive: false,
    alphaMin: 0.06,
    alphaMax: 0.55,
    diverging: false,
    rgb: () => [29, 158, 117],
  },
  diverging: {
    name: "diverging",
    defaultMode: "zscore",
    defaultSkipNonPositive: true,
    alphaMin: 0.1,
    alphaMax: 0.7,
    diverging: true,
    zRamp: (z) => (z < 1 ? 0.1 + 0.2 * (z - 0.5) : z < 3 ? 0.2 + Math.log10(z) : 0.7),
    rgb: (sign, u) =>
      sign < 0 ? [halfUp(240 - 15 * u), 18, 15] : [35, halfUp(190 - 15 * u), 40],
  },
}

/** Whether a declaration's scheme name is one of the three ramps. An own-
 * property check, not `in`: `"toString" in SCHEMES` is true. */
export function isRampScheme(name: unknown): name is RampSchemeName {
  return typeof name === "string" && Object.prototype.hasOwnProperty.call(SCHEMES, name)
}

/** `rank`'s single highlight: the saturated end of `diverging`'s green at a
 * fixed alpha, plus the bold weight the styler it replaces used. Derived from
 * the scheme rather than typed, so the two cannot drift. */
export const RANK_ALPHA = 0.35
export const RANK_STYLE: Readonly<{ backgroundColor: string; fontWeight: number }> = (() => {
  const [r, g, b] = SCHEMES.diverging.rgb(1, 1)
  return Object.freeze({ backgroundColor: `rgba(${r}, ${g}, ${b}, ${RANK_ALPHA})`, fontWeight: 600 })
})()

/** The `rgba(...)` string for one normalised value.
 *
 * Alpha is rounded to three decimals so the same cell always serialises to the
 * same string — sub-perceptual, and it is what lets the e2e suite compare
 * against an exact number.
 */
export function colorFor(scheme: Scheme, n: Normalized): string {
  let u: number
  let sign: number

  if (n.mode === "minmax") {
    if (scheme.diverging) {
      const signed = 2 * n.raw - 1
      u = Math.abs(signed)
      sign = signed < 0 ? -1 : 1
    } else {
      u = n.raw
      sign = 1
    }
  } else {
    // zscore and anchor alike: intensity is precomputed, sign is raw's.
    u = n.intensity
    sign = n.raw < 0 ? -1 : 1
  }

  const alpha =
    n.mode === "zscore" && scheme.zRamp
      ? scheme.zRamp(Math.abs(n.raw))
      : scheme.alphaMin + u * (scheme.alphaMax - scheme.alphaMin)

  const [r, g, b] = scheme.rgb(sign, u)
  return `rgba(${r}, ${g}, ${b}, ${halfUp(alpha * 1000) / 1000})`
}
