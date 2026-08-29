## Packaged CCv2 components (template-only, mandatory)

For packaged CCv2 components, agents **MUST** use Streamlit's official template as the starting point for every new component project.

- [Streamlit component-template](https://github.com/streamlit/component-template)

Never hand-scaffold the package/manifest/build layout and never copy/paste a packaged component scaffold from blog posts, gists, docs, or other internet sources.

If a request starts from a non-template scaffold, stop and regenerate from the template first, then port logic into the generated project.

Follow your generated project's README. **Only keep reading if you need to debug template wiring or customize behavior after template generation.**

## Contents

- Agent policy: template-only (mandatory)
- Prerequisites (packaged components)
- Start inline, then graduate to packaged
- Frontend framework note (React is optional)
- TypeScript support (recommended)
- Generate a new CCv2 component project
  - Non-interactive generation (cookiecutter keys)
  - Offline/airgapped
- Dev loop (template default)
- Verify the build output (prevents most load failures)
- Template invariants (don’t break these)
- Rename checklist (avoid placeholder-name drift)
- If you intentionally deviate from the template
- Verification recommendation

### Agent policy: template-only (for new projects)

If the request is for a **new** packaged CCv2 component:

- Start from the official template first (no exceptions).
- Never manually scaffold a custom package/manifest/build layout before template generation.
- Never copy a packaged component scaffold from the internet, even as a "starting point."
- If given existing non-template scaffolding, regenerate from the template and migrate code into it.
- Customize only after generation so you retain known-good packaging defaults.

**Exception — migrating existing v1 components:** When converting an existing v1 component to v2, you don't need to regenerate from the template. Instead, update the existing project structure in place: replace `setup.py` with `pyproject.toml`, add the `[tool.streamlit.component]` manifest, migrate the frontend to Vite, and rewrite the Python/TypeScript code to use v2 APIs. See the "Migrating existing v1 components to v2" section in the main SKILL.md.

### Prerequisites (packaged components)

- **Python build tooling**: `uv` (recommended) + `cookiecutter`.
- **Frontend build tooling**: Node.js + npm.

### Start inline, then graduate to packaged

Inline components are great for getting started quickly. Move to a packaged component when you hit any of these:

- You need **multiple frontend files** (components/modules) instead of one big string.
- You want to pull in **frontend libraries** (npm deps) and run a bundler.
- You need **tests**, CI, versioning, or distribution (PyPI/private index).

### Frontend framework note (React is optional)

The official Streamlit `component-template` v2 supports both **React + TypeScript (Vite)** and **Pure TypeScript (Vite)** (no React). CCv2 also works with **any frontend framework that compiles to JavaScript** (Svelte, Vue, Angular, vanilla TS/JS, etc.).

The only requirement is that you produce JS/CSS assets into your component’s `asset_dir`, then register them from Python via `html=...`, `js="..."`, and `css="..."` using **asset-dir-relative** paths/globs.

### TypeScript support (recommended)

For end-to-end type safety while authoring the frontend, install `@streamlit/component-v2-lib`:

- [npm package](https://www.npmjs.com/package/@streamlit/component-v2-lib)
- [docs](https://docs.streamlit.io/develop/api-reference/custom-components/component-v2-lib)

It provides TypeScript types like `FrontendRenderer` / `FrontendRendererArgs` so your `export default` renderer gets a **typed** `data` payload and typed state/trigger keys via generics.

### Generate a new CCv2 component project

This command is the required starting point for every packaged CCv2 component:

```bash
uvx --from cookiecutter cookiecutter gh:streamlit/component-template --directory cookiecutter/v2
```

If you run this non-interactively, pass explicit cookiecutter values (do not rely on defaults):

Template keys:

- `author_name`
- `author_email`
- `project_name`
- `package_name`
- `import_name`
- `description`
- `open_source_license`
- `framework`

Recommended non-interactive invocation:

This sample uses a **hypothetical breadcrumb component** name so the values are concrete and meaningful:

```bash
uvx --from cookiecutter cookiecutter gh:streamlit/component-template \
  --directory cookiecutter/v2 \
  --no-input \
  author_name="Your Name" \
  author_email="you@example.com" \
  project_name="Streamlit Breadcrumbs" \
  package_name="streamlit-breadcrumbs" \
  import_name="streamlit_breadcrumbs" \
  description="Packaged Streamlit CCv2 breadcrumb component" \
  open_source_license="Apache-2.0" \
  framework="React + Typescript"
```

Notes:

- Choice values must match template options exactly (`framework` is `"React + Typescript"` or `"Pure Typescript"`).
- Passing all keys avoids template placeholder names and post-generation rename churn.

Offline/airgapped:

```bash
uvx --from cookiecutter cookiecutter /path/to/component-template --directory cookiecutter/v2
```

### Dev loop (template default)

From the generated project:

1. Activate the target project environment before Python/uv commands:

   ```bash
   source /path/to/project/.venv/bin/activate
   ```

2. Build the frontend assets (from `<import_name>/frontend`):

   ```bash
   npm i
   npm run build
   ```

3. Editable install (project root containing `pyproject.toml`):

   ```bash
   uv pip install -e . --force-reinstall
   ```

4. Run the example app with Streamlit:

   ```bash
   streamlit run example.py
   ```

Why this order:

- Building first ensures `asset_dir` contains the expected files before install/use.
- Reinstalling editable after key renames keeps metadata and import paths in sync.

### Packaged component workflow (copy/paste checklist)

Use this when debugging or customizing after generation; it's designed to prevent the common "built assets exist but Streamlit can't load them" failure modes.

```
Packaged CCv2 checklist
- [ ] Generate project from `component-template` v2
- [ ] Confirm this is template-generated (not hand-scaffolded, not copied from internet snippets)
- [ ] Activate the target project environment before Python/uv commands
- [ ] Rename template defaults (`streamlit-component-x`, `streamlit_component_x`, etc.) if needed
- [ ] Build frontend assets into the manifest’s `asset_dir` (template: `frontend/build/`)
- [ ] Editable install the Python package (`uv pip install -e . --force-reinstall`)
- [ ] Verify `js=`/`css=` globs match exactly one file each under `asset_dir`
- [ ] Run via `streamlit run ...` and confirm the component renders/events work
- [ ] If something breaks: read `references/troubleshooting.md`, fix, rebuild, re-verify glob uniqueness
```

### Choosing how to deliver built assets

**Use asset-dir globs. This is the template default and the right answer for any packaged component.**

```python
import streamlit as st

_component = None


def get_my_component():
    """Return the mount callable, registering it on first use."""
    global _component
    if _component is None:
        _component = st.components.v2.component(
            "my_package.my_component",
            js="index-*.js",     # asset-dir-relative glob
            css="index-*.css",
        )
    return _component
```

Streamlit serves the matched files as static assets under
`/_stcore/bidi-components/<component>/<file>`, so the browser fetches and caches
them like any other asset. Two requirements come with this:

- Globs must match **exactly one** file. Clean the build output before rebuilding
  so stale hashed files can't accumulate.
- Registration must be **lazy** (the `get_my_component()` shape above). Manifests
  are only discovered once a Streamlit `Runtime` exists, so registering at module
  import time raises `StreamlitAPIException` on any plain-Python import.

#### When inline strings are acceptable instead

Passing raw content to `js=`/`css=` — including via `Path(...).read_text()` — makes
the asset part of the component definition rather than a served file. That means:

- it travels inside the session payload on **every** session, and is never
  HTTP-cached, so users re-download it each time;
- it is held in server memory for the process lifetime;
- the built files must exist at **import** time, so importing the package fails
  before your code can give a useful error.

That trade is fine for a handful of kilobytes you would have been content to type
into the Python file by hand. It is the wrong choice for a real bundle. If you do
go inline, file names must be deterministic (`assetFileNames: "[name][extname]"`),
and single-line minified CSS can be misread as a path — see the `cssMinify` table
in SKILL.md.

**Do not choose inline to dodge a registration error.** If a plain
`import my_package` raises *"must be declared in pyproject.toml with asset_dir"*,
the fix is lazy registration, not inlining the bundle.

### Verify the build output (prevents most load failures)

- Ensure the manifest’s `asset_dir` exists and contains the built assets.
- Ensure each glob you register from Python matches **exactly one** file under `asset_dir`:
  - Typical: `js="index-*.js"` and `css="index-*.css"`
  - If multiple matches: clean the build output (template: `npm run clean`) and rebuild.

### Template invariants (don’t break these)

You typically shouldn’t need to touch these, but they explain most “why won’t this load?” failures:

- **Component key**: the Python registration key must match the manifest: `"<project.name>.<component.name>"`.
- **Manifest must ship inside the Python package**: the template places a minimal CCv2 manifest at `<import_name>/pyproject.toml` with `asset_dir = "frontend/build"`. It has to live *inside* the package, not only at the repo root: the scanner finds it via the import spec for editable installs and by walking the distribution's file list for wheels, and the root file is not shipped in the wheel at all.
- **Distribution name must normalize to the import package name.** The scanner derives the package to look for from the *distribution* name by swapping hyphens for underscores, then resolves it with `find_spec`. So `[project].name = "my-widget"` requires the import package to be `my_widget`. Pick a mismatched pair — `name = "streamlit-widget"` over a `widget/` directory — and discovery silently finds nothing, which surfaces later as the `asset_dir` registration error. The template keeps these aligned; keep them aligned through any rename.
- **Asset paths are asset-dir-relative strings**: `js="index-*.js"` (template default output) or `js="assets/index-*.js"` (if you configured an `assets/` subdir).
- **Globs must match exactly one file**: if `index-*.js` matches multiple hashed builds, clean the build output (`npm run clean`) and rebuild.

### Rename checklist (avoid placeholder-name drift)

Template defaults like `streamlit-component-x` / `streamlit_component_x` should be replaced everywhere early.

Rename all of these together:

- Root folder name (optional but recommended for clarity).
- Distribution name (`[project].name`) in root `pyproject.toml`.
- Import package directory (`streamlit_<real_name>`).
- In-package manifest file and contents (`<import_name>/pyproject.toml`).
- Wrapper registration key:
  - `st.components.v2.component("<project.name>.<component.name>", ...)`
- `MANIFEST.in` and `[tool.setuptools.*]` references.
- README/example imports and frontend package name.

### Allowed customizations (after template generation only)

Keep the blast radius small:

- If you change output layout, update only the `js=`/`css=` asset-dir-relative globs in the Python wrapper.
- For Vite, keep `base: "./"` so relative URLs work when served from Streamlit’s component URLs.

### Verification recommendation

Validate that a packaged component **renders and round-trips events** with
`streamlit run ...`. A plain `python -c "import ..."` cannot tell you that — it
never mounts anything.

What a plain import *does* tell you: whether your registration is import-safe. It
must succeed. If it raises *"must be declared in pyproject.toml with asset_dir"*,
that is a real defect in your package, not an artifact of the check: you are
registering eagerly at import time, and manifest discovery only happens inside
`Runtime.__init__`. Move registration behind a `get_*_component()` accessor and the
import passes. Don't route around it by switching to inline assets.

Worth locking in with a test, since the regression is easy to reintroduce and only
shows up outside a running server:

```python
import subprocess
import sys


def test_import_does_not_register_the_component():
    """Registration must stay lazy, or importing the package outside a
    Streamlit runtime raises and takes the whole unit suite with it.
    """
    program = (
        "import my_package;"
        " assert my_package.component._component is None"
    )
    result = subprocess.run(
        [sys.executable, "-c", program], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
```

A subprocess is required: by the time any in-process test runs, the package is
already in `sys.modules`, so only a cold interpreter observes a first import.
