import { useEffect, useState } from "react"
import type { StreamlitThemeInfo } from "../types/AgGridTypes"

// Streamlit exposes its active theme as CSS custom properties (`--st-*`)
// on a wrapper element around each CCv2 component instance (per docs
// https://docs.streamlit.io/develop/concepts/custom-components/components-v2/theming).
// The variables inherit down the DOM, so we can read them from the
// component's own parentElement via getComputedStyle. The Python-side
// `st.get_option("theme.*")` can't see user-level Light/Dark toggles —
// those update the CSS vars in the browser without a server rerun.
const VAR_BACKGROUND = "--st-background-color"
const VAR_TEXT = "--st-text-color"
const VAR_PRIMARY = "--st-primary-color"
const VAR_SECONDARY_BG = "--st-secondary-background-color"
const VAR_FONT = "--st-font"

function parseHexLuminance(hex: string): number | null {
  const clean = hex.trim().replace(/^#/, "")
  if (clean.length !== 6) return null
  const r = parseInt(clean.slice(0, 2), 16)
  const g = parseInt(clean.slice(2, 4), 16)
  const b = parseInt(clean.slice(4, 6), 16)
  if (isNaN(r) || isNaN(g) || isNaN(b)) return null
  return (0.299 * r + 0.587 * g + 0.114 * b) / 255
}

function parseRgbLuminance(rgb: string): number | null {
  const m = rgb.match(/rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)/i)
  if (!m) return null
  const r = parseInt(m[1], 10)
  const g = parseInt(m[2], 10)
  const b = parseInt(m[3], 10)
  return (0.299 * r + 0.587 * g + 0.114 * b) / 255
}

function computeBase(bg: string): "light" | "dark" {
  const lum =
    bg.startsWith("#") ? parseHexLuminance(bg) : parseRgbLuminance(bg)
  if (lum === null) return "light"
  return lum < 0.5 ? "dark" : "light"
}

function readTheme(element: Element | null): StreamlitThemeInfo | null {
  if (typeof window === "undefined" || typeof document === "undefined") {
    return null
  }
  const target = element ?? document.documentElement
  const styles = getComputedStyle(target)
  const bg = styles.getPropertyValue(VAR_BACKGROUND).trim()
  if (!bg) return null

  const text = styles.getPropertyValue(VAR_TEXT).trim()
  const primary = styles.getPropertyValue(VAR_PRIMARY).trim()
  const secondaryBg = styles.getPropertyValue(VAR_SECONDARY_BG).trim()
  const font = styles.getPropertyValue(VAR_FONT).trim() || "Source Sans Pro"

  return {
    primaryColor: primary,
    textColor: text,
    backgroundColor: bg,
    secondaryBackgroundColor: secondaryBg,
    font,
    base: computeBase(bg),
  }
}

function themesEqual(
  a: StreamlitThemeInfo | null,
  b: StreamlitThemeInfo | null
): boolean {
  if (a === b) return true
  if (!a || !b) return false
  return (
    a.base === b.base &&
    a.backgroundColor === b.backgroundColor &&
    a.textColor === b.textColor &&
    a.primaryColor === b.primaryColor &&
    a.secondaryBackgroundColor === b.secondaryBackgroundColor &&
    a.font === b.font
  )
}

export function useStreamlitTheme(
  element: Element | null
): StreamlitThemeInfo | null {
  const [theme, setTheme] = useState<StreamlitThemeInfo | null>(() =>
    readTheme(element)
  )

  useEffect(() => {
    if (!element) return

    const recheck = () => {
      const next = readTheme(element)
      setTheme((prev) => (themesEqual(prev, next) ? prev : next))
    }

    // Initial re-read after mount in case variables weren't ready synchronously.
    recheck()

    // Streamlit doesn't document an explicit theme-change event. CSS variables
    // are updated somewhere up the DOM tree when the user toggles the theme.
    // Observe the whole document for attribute changes on style/class/data-theme
    // — the filter keeps this cheap even with subtree:true.
    const observer = new MutationObserver(recheck)
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["style", "class", "data-theme"],
      subtree: true,
    })

    // System color-scheme changes (Streamlit "Auto" mode follows OS).
    const mql = window.matchMedia?.("(prefers-color-scheme: dark)")
    const onMqChange = () => recheck()
    mql?.addEventListener?.("change", onMqChange)

    return () => {
      observer.disconnect()
      mql?.removeEventListener?.("change", onMqChange)
    }
  }, [element])

  return theme
}
