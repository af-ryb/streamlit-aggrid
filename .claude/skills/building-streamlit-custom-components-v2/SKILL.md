---
name: building-streamlit-custom-components-v2
description: >
  Builds bidirectional Streamlit Custom Components v2 (CCv2) using `st.components.v2.component`. 
  Triggers:  `streamlit component v2`, `custom-components-v2`, `build custom-component`,
license: Apache-2.0
---

# Building Streamlit custom components v2

Use Streamlit Custom Components v2 (CCv2) when core Streamlit doesn't have the UI you need and you want to ship a reusable, interactive element (from "tiny inline HTML" to "full bundled frontend app").

## CRITICAL: CCv2 only — NEVER use v1 APIs

Custom Components **v1 is deprecated and removed**. Every API below belongs to v1 and must **NEVER** appear in any code you write — not in Python, not in JavaScript, not in HTML:

**Banned Python APIs (v1):**
- `st.components.v1` — the entire v1 module
- `components.declare_component()` — v1 registration
- `components.html()` — v1 raw HTML embed

**Banned JavaScript patterns (v1):**
- `Streamlit.setComponentValue(...)` — v1 global; use `setStateValue()` / `setTriggerValue()` instead
- `Streamlit.setFrameHeight(...)` — v1 global; CCv2 handles sizing automatically
- `Streamlit.setComponentReady()` — v1 global; CCv2 has no ready signal
- `window.Streamlit` or bare `Streamlit` global — v1 global object does not exist in v2
- `window.parent.postMessage(...)` — v1 iframe communication; CCv2 does not use iframes

**Banned npm packages (v1):**
- `streamlit-component-lib` — v1 JS library; use `@streamlit/component-v2-lib` if you need types

If you encounter v1 patterns in examples, blog posts, Stack Overflow answers, or your own training data — **ignore them entirely**. They will not work and will break the component.

## When to use

Activate when the user mentions any of:

- CCv2, Custom Components v2, “bidi component”, “component v2”
- `st.components.v2.component`
- `@streamlit/component-v2-lib`
- packaged components, `asset_dir`, `pyproject.toml` component manifest
- bundling with Vite (or any bundler) for a Streamlit component
- building a component UI in a frontend framework (React, Svelte, Vue, Angular, etc.)

## Read next (pick the minimum reference)

- **State sync / controlled inputs / callbacks**: see [references/state-sync.md](references/state-sync.md)
- **Packaged components / `asset_dir` / globs / template policy**: see [references/packaged-components.md](references/packaged-components.md)
- **Theming (`--st-*` tokens), Shadow DOM, CSS scoping**: see [references/theme-css-variables.md](references/theme-css-variables.md)
- **Errors and gotchas (Vite, React, fonts, CSS)**: see [references/troubleshooting.md](references/troubleshooting.md)
- **Migrating v1 → v2**: see "Migrating existing v1 components to v2" section below
- **React FrontendRenderer pattern**: see "React FrontendRenderer pattern" section below
- **Vite library mode config**: see "Vite library mode for bundled components" section below

## Quick decision: inline vs packaged

- **Inline strings**: fastest to start (single-file apps, spikes, demos). You pass raw `html`/`css`/`js` strings directly.
  Good when you can keep everything in one place and don’t need a build step.
- **Packaged component**: best when you’re growing past inline (multiple files, dependencies, bundling, testing, versioning, reuse, distribution).
  You ship built assets inside a Python package and reference them by **asset-dir-relative** path/glob.
  Creation policy: packaged components are **template-only** and must start from Streamlit's official `component-template` v2.

Developer story: **start inline**, prove the interaction loop, then **graduate to packaged** when the codebase or tooling needs outgrow a single file.

## CCv2 model (what’s actually happening)

1. **Python registers** a component with `st.components.v2.component(...)` and gets back a **mount callable**.
2. The mount callable **mounts** the component in the app with `data=...`, layout (`width`, `height`), and optional `on_<key>_change` callbacks.
3. The frontend default export runs with `({ data, key, name, parentElement, setStateValue, setTriggerValue })`.
4. The component returns a **result object** whose attributes correspond to **state keys** and **trigger keys**.

## Best practice: wrap the mount callable in your own Python API

Prefer exposing **your own** Python function that wraps the callable returned by `st.components.v2.component(...)`.

This gives you a clean, stable API surface for end users (typed parameters, validation, friendly defaults) and keeps `data=...`, `default=...`, and callback wiring as an internal detail.

Important — **when** you register depends on how assets are delivered:

- **Inline components** (raw `html`/`css`/`js` strings): register at **module import time**. Nothing is resolved against the filesystem, so importing the module is always safe.
- **Packaged components** (asset-dir paths/globs): register **lazily, on first use**. `st.components.v2.component()` resolves a path-like `js=`/`css=` against the component manifest, and manifests are only discovered once a Streamlit `Runtime` exists (`Runtime.__init__` calls `discover_and_register_components`). Registering at import time therefore raises `StreamlitAPIException` for **any** plain-Python import of your package — including your unit test suite.

Either way, register **once**: never call `st.components.v2.component(...)` inside a function that runs on every rerun, or you re-register the same name repeatedly.

The lazy pattern for packaged components — a module-global cache keeps registration to exactly once while keeping import side-effect-free:

```python
import streamlit as st

_component = None


def get_my_component():
    """Return the mount callable, registering it on first use."""
    global _component
    if _component is None:
        _component = st.components.v2.component(
            "my-package.my-component",
            js="index-*.js",
            css="index-*.css",
        )
    return _component
```

Call `get_my_component()(...)` from inside your public wrapper function — never at module scope.

References:

- [`st.components.v2.component`](https://docs.streamlit.io/develop/api-reference/custom-components/st.components.v2.component)
- [`ComponentRenderer` (mount callable type)](https://docs.streamlit.io/develop/api-reference/custom-components/st.components.v2.types.componentrenderer)

Example pattern:

```python
import streamlit as st
from collections.abc import Callable

_MY_COMPONENT = st.components.v2.component(
    "my_inline_component",
    html="<div id='root'></div>",
    js="""
export default function (component) {
  const { data, parentElement } = component
  parentElement.querySelector("#root").textContent = data?.label ?? ""
}
""",
)


def my_component(
    label: str,
    *,
    key: str | None = None,
    on_value_change: Callable[[], None] | None = None,
    on_submitted_change: Callable[[], None] | None = None,
):
    # Callbacks are optional, but if you want result attributes to always exist,
    # provide (even empty) callbacks.
    if on_value_change is None:
        on_value_change = lambda: None
    if on_submitted_change is None:
        on_submitted_change = lambda: None

    return _MY_COMPONENT(
        data={"label": label},
        key=key,
        on_value_change=on_value_change,
        on_submitted_change=on_submitted_change,
    )
```

## Inline quickstart (state + trigger)

**Reminder: use ONLY v2 APIs.** Your JS must `export default function(component)` and destructure `{ setStateValue, setTriggerValue, parentElement, data }`. NEVER use `Streamlit.setComponentValue()`, `window.Streamlit`, or any v1 pattern.

This is the minimum "bidi loop":

- **JS → Python**: emit updates via `setStateValue(...)` (persistent) and `setTriggerValue(...)` (event)
- **Python → JS**: re-hydrate UI via `data=...` on every run

```python
import streamlit as st

HTML = """<input id="txt" /><button id="btn" type="button">Submit</button>"""

JS = """\
export default function (component) {
  const { data, parentElement, setStateValue, setTriggerValue } = component

  const input = parentElement.querySelector("#txt")
  const btn = parentElement.querySelector("#btn")
  if (!input || !btn) return

  const nextValue = (data && data.value) ?? ""
  if (input.value !== nextValue) input.value = nextValue

  input.oninput = (e) => {
    setStateValue("value", e.target.value)
  }

  btn.onclick = () => {
    setTriggerValue("submitted", input.value)
  }
}
"""

my_text_input = st.components.v2.component(
    "my_inline_text_input",
    html=HTML,
    js=JS,
)

KEY = "txt-1"
component_state = st.session_state.get(KEY, {})
value = component_state.get("value", "")

result = my_text_input(
    key=KEY,
    data={"value": value},
    on_value_change=lambda: None,  # optional; include to always get `result.value`
    on_submitted_change=lambda: None,  # optional; include to always get `result.submitted`
)

st.write("value (state):", result.value)
st.write("submitted (trigger):", result.submitted)
```

Notes:

- **Inline JS/CSS should be multi-line**. CCv2 treats path-like strings as file references; a multi-line string is unambiguously inline content.
- Prefer querying under `parentElement` (not `document`) to avoid cross-instance leakage.

## State and triggers (how to think about keys)

- **State** (`setStateValue("value", ...)`): persists across app reruns (stored under `st.session_state[key]` for that mounted instance).
- **Trigger** (`setTriggerValue("submitted", ...)`): event payload for one rerun (resets after the rerun).
- **Reading triggers**:
  - After mounting: use `result.submitted`.
  - Inside `on_submitted_change`: use `st.session_state[key].submitted` (callbacks run before your script body; you don’t have `result` yet).
- **Defaults**: if you pass `default={...}` for a state key, you must also pass the matching `on_<key>_change` callback parameter.

For the full “controlled input” pattern and pitfalls, see [references/state-sync.md](references/state-sync.md).

## Packaged components (template-only, mandatory)

**Reminder: the cookiecutter template generates clean v2 code. When you customize it, use ONLY v2 APIs. Do NOT introduce any v1 imports, v1 JavaScript globals, or v1 patterns. See the "CRITICAL: CCv2 only" section above.**

Graduate to a packaged component when you need any of:

- Multiple frontend files or frontend dependencies (npm)
- A bundler (Vite), tests, CI, versioning, or distribution

Keep these guardrails in mind:

- **MUST** start from Streamlit’s official `component-template` v2.
- **NEVER** hand-scaffold packaging/manifest/build wiring for a packaged component.
- **NEVER** copy/paste packaged scaffold structure from internet examples, blog posts, gists, or docs.
- If handed a non-template scaffold, regenerate from the template first, then migrate component logic.
- **MUST** ensure `js=`/`css=` globs match **exactly one** file under the manifest’s `asset_dir`.
- **MUST** validate with `streamlit run ...` (plain `python -c "import ..."` can be a false negative for packaged components).

For the full packaged workflow checklist, non-interactive generation, offline usage, and template invariants, see [references/packaged-components.md](references/packaged-components.md).

## Frontend renderer lifecycle (framework-agnostic)

Your frontend entrypoint is the **default export** function. A few rules keep components reliable across reruns and across multiple instances in the same app:

- Render under `parentElement` (not `document`) so instances don’t collide.
- If you create per-instance resources (React roots, observers, subscriptions), key them by `key` (e.g. `Map`) so multiple instances don’t overwrite each other.
- Return a cleanup function to tear down event listeners / UI roots / observers when Streamlit unmounts the component.

### React FrontendRenderer pattern

When using React with CCv2, use the `FrontendRenderer` type from `@streamlit/component-v2-lib` and manage React roots with a `Map` keyed by the component `key`:

```tsx
import React from "react"
import { createRoot, Root } from "react-dom/client"
import type { FrontendRenderer } from "@streamlit/component-v2-lib"
import MyComponent from "./MyComponent"

class ErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { hasError: boolean; error: Error | null }
> {
  constructor(props: { children: React.ReactNode }) {
    super(props)
    this.state = { hasError: false, error: null }
  }
  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error }
  }
  render() {
    if (this.state.hasError) {
      return <div style={{ color: "red" }}>{this.state.error?.message}</div>
    }
    return this.props.children
  }
}

const rootMap = new Map<string, { root: Root; container: HTMLElement }>()

const render: FrontendRenderer = ({ data, key, setStateValue, parentElement }) => {
  let entry = rootMap.get(key)
  if (!entry) {
    const container = document.createElement("div")
    container.className = "my-component-scope" // CSS scoping class
    parentElement.appendChild(container)
    const root = createRoot(container)
    entry = { root, container }
    rootMap.set(key, entry)
  } else if (!parentElement.contains(entry.container)) {
    parentElement.appendChild(entry.container)
  }

  entry.root.render(
    <ErrorBoundary>
      <MyComponent data={data} setStateValue={setStateValue} />
    </ErrorBoundary>,
  )

  return () => {
    entry!.root.unmount()
    entry!.container.remove()
    rootMap.delete(key)
  }
}

export default render
```

Key points:
- **`rootMap`** prevents creating multiple React roots for the same component instance across reruns.
- **`ErrorBoundary`** catches render errors gracefully instead of breaking the entire app.
- **Container element** with a scoping class allows CSS to be scoped without Shadow DOM.
- **Cleanup function** unmounts the React root and removes the container from DOM.
- The component receives `data` and `setStateValue` as props — **not** via Streamlit globals.

## Styling and theming

- Prefer **`isolate_styles=True`** (default). Your component runs in a shadow root and won’t leak styles into the app.
- Set `isolate_styles=False` when:
  - Your component wraps a third-party library that injects styles globally (e.g. Ant Design, react-checkbox-tree).
  - You need to inherit page-level CSS variables without shadow DOM barriers.
  - You need global font injection or Tailwind utilities.
- When using `isolate_styles=False`, **manually scope your CSS** by wrapping all selectors under a unique class (e.g. `.my-component .rct-text { ... }`). Set this class on the container element in your `FrontendRenderer`. This prevents your styles from leaking into the Streamlit app.
- Streamlit injects `--st-*` theme CSS variables (colors, typography, chart palettes, radii, borders, etc.). **Highly recommended:** use these variables so your component automatically adapts to the user’s current Streamlit theme (light/dark/custom) without authoring separate theme variants. Start with the common ones (`--st-text-color`, `--st-primary-color`, `--st-secondary-background-color`) and refer to the full list when you need it:
  - [references/theme-css-variables.md](references/theme-css-variables.md)

## Migrating existing v1 components to v2

If you have an existing v1 component and need to migrate, here’s the approach:

### Python side
1. Replace `streamlit.components.v1` with `st.components.v2.component(...)`.
2. Replace `declare_component(name, path=build_dir)` or `declare_component(name, url=...)` with a **manifest-declared asset dir plus lazy registration**. A v1 component served its build directory over HTTP; the v2 equivalent is `asset_dir`, not inlining the bundle into Python.

   Add a manifest inside the package (`<import_name>/pyproject.toml`):

   ```toml
   [project]
   name = "my-package"
   version = "0.1.0"

   [[tool.streamlit.component.components]]
   name = "my-component"
   asset_dir = "frontend/build"
   ```

   Then register lazily against it — the component key is `"<project name>.<component name>"`:

   ```python
   import streamlit as st

   _component = None


   def get_my_component():
       """Return the mount callable, registering it on first use."""
       global _component
       if _component is None:
           _component = st.components.v2.component(
               "my-package.my-component",
               js="index-*.js",
               css="index-*.css",
               html="<div></div>",
               isolate_styles=False,  # usually False for migrated components
           )
       return _component
   ```

   **Do not** port a real build output with `js=(BUILD_DIR / "index.js").read_text()`. That inlines the whole bundle into every session's payload — it is never HTTP-cached, so users re-download it on every fresh session, and the string is pinned in server memory for the process lifetime. Reserve inline strings for assets small enough that you would have been happy typing them into the Python file by hand. See "Choosing how to deliver built assets" in [references/packaged-components.md](references/packaged-components.md).
3. Replace direct kwargs with `data=dict(...)`.
4. Replace `default={...}` and add `on_<key>_change=lambda: None` for each state key.
5. Remove the `_RELEASE` flag and dev/prod branching — v2 doesn’t use iframe URLs.

### Frontend side
1. Replace `react-scripts` with **Vite** (library mode). See “Vite library mode” section below.
2. Replace `streamlit-component-lib` with `@streamlit/component-v2-lib`.
3. Replace `ReactDOM.render(...)` entry point with a `FrontendRenderer` default export (see React pattern above).
4. Replace class component extending `StreamlitComponentBase` with a functional component.
5. Replace `this.props.args[...]` with destructured `data` prop.
6. Replace `Streamlit.setComponentValue({...})` with individual `setStateValue(“key”, value)` calls.
7. Replace Font Awesome / external icon fonts with inline SVG (font files can’t be bundled in v2’s inline CSS model).
8. Move CSS from `public/` into `src/` so Vite can bundle it inline.

### CSS migration
- v1 loaded CSS via `<link>` tags in the iframe HTML. v2 bundles CSS inline.
- Font files (woff2, ttf, etc.) **cannot** be referenced from inline CSS. Replace icon fonts with inline SVG components.
- External CSS frameworks (Bootstrap, etc.) should be removed unless actually used by the component.
- Scope all CSS selectors under a wrapper class to prevent style leakage.

## Vite library mode for bundled components

When building a React-based CCv2 component with Vite, use **library mode** to produce a single JS + CSS bundle:

```ts
// vite.config.ts
import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"

export default defineConfig({
  plugins: [react()],
  base: "./",
  define: {
    "process.env.NODE_ENV": JSON.stringify("production"),
  },
  build: {
    outDir: "build",
    lib: {
      entry: "src/index.tsx",
      formats: ["es"],
      // Content-hashed so the browser cache invalidates on a real change.
      // Python globs these as index-*.js / index-*.css.
      fileName: "index-[hash]",
    },
    rollupOptions: {
      output: {
        assetFileNames: "index-[hash][extname]",
        inlineDynamicImports: true, // single JS bundle
      },
    },
  },
  server: { port: 3001 },
})
```

Critical configuration notes:
- **`fileName: "index-[hash]"` + `assetFileNames: "index-[hash][extname]"`** — content-hashed names let the browser cache the bundle and re-fetch it only when it actually changes. Because each glob must match **exactly one** file, your `build` script must wipe the output directory first (`rm -rf build && tsc && vite build`), or yesterday's hash makes the glob ambiguous and registration fails.
- **`inlineDynamicImports: true`** — ensures everything is in one JS file.
- **`base: "./"`** — required for relative URL resolution.
- **`define: { "process.env.NODE_ENV": ... }`** — prevents "process is not defined" errors from libraries that check `process.env`.
- **`cssMinify`** — leave it at the default (enabled). See below for the one case where you must disable it.

### `cssMinify: false` — only for inline CSS

You will see `cssMinify: false` in older CCv2 configs. It is **not** a general requirement, and on the packaged path it just costs you a bigger stylesheet.

It matters only when you pass CSS **content** to `css=`. CCv2 decides whether a string is content or a file reference by shape (`looks_like_inline_content`): a string containing a newline is always content, but a single-line string is treated as a **path** if it contains glob characters (`*`, `?`, `[`, `]`), a path separator, or ends in `.css`/`.js`. Minified CSS routinely contains `[` (attribute selectors) and `*` (the universal selector), so a one-line minified stylesheet gets misread as a glob and registration fails with *"must be declared in pyproject.toml with asset_dir"*.

| How you deliver CSS | `cssMinify` |
|---|---|
| `css="index-*.css"` (asset-dir glob) | leave enabled — the heuristic never sees your CSS, only the glob |
| `css=<raw CSS string>` (inline) | set `false`, or otherwise guarantee a newline in the output |

Typical `package.json` for a Vite-based CCv2 frontend:

```json
{
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "rm -rf build && tsc && vite build",
    "clean": "rm -rf build"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1"
  },
  "devDependencies": {
    "@streamlit/component-v2-lib": "^0.2.0",
    "@types/react": "^18.3.12",
    "@types/react-dom": "^18.3.1",
    "@vitejs/plugin-react": "^4.3.4",
    "typescript": "^5.7.2",
    "vite": "^5.4.11"
  }
}
```

`build` wipes the output directory first. With content-hashed filenames that is not housekeeping — it is what keeps each `index-*` glob matching exactly one file.

And `tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",
    "strict": true,
    "skipLibCheck": true,
    "esModuleInterop": true,
    "isolatedModules": true,
    "noEmit": true
  },
  "include": ["src"]
}
```

## Troubleshooting and gotchas

Start here when something “should work” but doesn’t:

- [references/troubleshooting.md](references/troubleshooting.md)
