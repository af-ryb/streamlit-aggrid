/** The three built-in palettes.
 *
 * Each scheme reproduces one of the hand-written stylers this feature
 * replaces, exactly: `neutral` the blue statistical wash from `funnel_saj`,
 * `positive` the green min/max ramp from `payers_intelligence`, `diverging`
 * the red/green split from the cohort report.
 *
 * Two invariants hold for all three. The fill is always `rgba(...)` over the
 * cell's own background and never an opaque colour — an opaque ramp paints a
 * light cell under the dark theme's light text and the number disappears,
 * which is a bug that already shipped once. And `diverging` reaches alpha 0.7,
 * above the 0.55 the other two stop at; that is what the cohort report draws
 * today, and it stays a named endpoint here so changing it later is one edit.
 *
 * Imports nothing, so `__checks__/schemes.check.ts` can run it under `node`.
 */

export type SchemeName = "neutral" | "positive" | "diverging"
export type ColorScaleMode = "minmax" | "zscore"

/** Must stay in step with `st_aggrid/color_scale.py`'s COLOR_SCALE_SCHEMES /
 * COLOR_SCALE_MODES, which `test/unit/test_public_exports.py` pins. */
export const SCHEME_NAMES: readonly SchemeName[] = ["neutral", "positive", "diverging"]
export const MODE_NAMES: readonly ColorScaleMode[] = ["minmax", "zscore"]

export interface Normalized {
  mode: ColorScaleMode
  /** `minmax`: `t` in `[0, 1]`. `zscore`: the signed z. */
  raw: number
  /** `zscore` only: `zIntensity(z)`. Ignored under `minmax`, where the
   * intensity depends on whether the scheme is diverging and so is derived
   * from `raw` here. */
  intensity: number
}

export interface Scheme {
  name: SchemeName
  defaultMode: ColorScaleMode
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
   * modes. */
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

export const SCHEMES: Record<SchemeName, Scheme> = {
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
