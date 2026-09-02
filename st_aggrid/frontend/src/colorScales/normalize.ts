/** Statistics and gates for the built-in colour scales.
 *
 * Deliberately imports nothing — not AG-Grid, not a sibling module. That keeps
 * every number in the design reviewable on its own and lets
 * `__checks__/normalize.check.ts` run it directly under `node`.
 */

/** Below this coefficient of variation the column is treated as uniform and
 * nothing is painted. */
export const CV_FLOOR = 0.001

/** Values within this many standard deviations of the mean are left
 * unpainted — the dead zone around the average. */
export const Z_DEAD = 0.5

/** |z| at and beyond which a scale is fully saturated. */
export const Z_CAP = 3

export interface Stats {
  count: number
  min: number
  max: number
  mean: number
  /** The **population** standard deviation (divisor `count`, not `count - 1`).
   * That is what all three stylers this replaces compute, and using the sample
   * one instead would shift every z-score. */
  sd: number
}

/** Summary of one column's population. `values` must be non-empty — the caller
 * (`population.ts`) returns `null` for an empty population rather than calling
 * this with one. */
export function popStats(values: number[]): Stats {
  let min = Infinity
  let max = -Infinity
  let total = 0
  for (const value of values) {
    if (value < min) min = value
    if (value > max) max = value
    total += value
  }
  const mean = total / values.length
  let squares = 0
  for (const value of values) squares += (value - mean) * (value - mean)
  return { count: values.length, min, max, mean, sd: Math.sqrt(squares / values.length) }
}

/** Position in `[0, 1]` between the population's extremes, or `null` when the
 * column has no spread to show. */
export function minmaxT(stats: Stats, value: number): number | null {
  if (!(stats.max > stats.min)) return null
  return (value - stats.min) / (stats.max - stats.min)
}

/** Signed standard scores, or `null` when the column is uniform or the value
 * sits inside the dead zone.
 *
 * The uniformity floor divides by `|mean|`. The JavaScript this replaces
 * divides by the signed mean, which makes the coefficient negative for a
 * negative-mean column — always below the floor, so such a column would never
 * paint. Unreachable while every z-score scheme skips non-positive values, and
 * reachable the moment `skip_non_positive: false` is paired with `zscore`.
 */
export function zScore(stats: Stats, value: number): number | null {
  if (stats.sd === 0) return null
  if (stats.mean !== 0 && stats.sd / Math.abs(stats.mean) < CV_FLOOR) return null
  const z = (value - stats.mean) / stats.sd
  return Math.abs(z) < Z_DEAD ? null : z
}

/** How far out of the ordinary a z-score is, capped into `[0, 1]`. */
export function zIntensity(z: number): number {
  return Math.min(Math.abs(z) / Z_CAP, 1)
}

/** Signed deviation from a fixed anchor, in units of `span`, clamped into
 * `[-1, 1]`. The `anchor` mode's whole reference frame: no population, no
 * statistics. The exact anchor is `0`, and `index.ts` leaves it unpainted —
 * "no deviation" must not read as a faint colour in either direction. */
export function anchorD(anchor: number, span: number, value: number): number {
  const d = (value - anchor) / span
  return d < -1 ? -1 : d > 1 ? 1 : d
}
