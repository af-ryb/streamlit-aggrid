"""CCv2 component registration.

The frontend bundle is served from the directory declared as ``asset_dir`` in
``st_aggrid/pyproject.toml``, so it travels to the browser as a cacheable
static file rather than being inlined into every session's message stream.

Registration is lazy on purpose. ``st.components.v2.component`` resolves the
globs below against the component manifest, and manifests are only discovered
when a Streamlit ``Runtime`` exists (``Runtime.__init__`` calls
``discover_and_register_components``). Registering at import time would raise
``StreamlitAPIException`` for any plain-Python import of this package,
including the unit test suite.
"""

from __future__ import annotations

from typing import Any, Callable

import streamlit as st

# "<project name>.<component name>", both as declared in st_aggrid/pyproject.toml.
_COMPONENT_NAME = "st-aggrid.aggrid"

# Content-hashed filenames produced by vite.config.ts. Each glob must resolve
# to exactly one file; the frontend `build` script wipes the output directory
# first so a stale hash can never make this ambiguous.
_JS_GLOB = "index-*.js"
_CSS_GLOB = "index-*.css"

_component: Callable[..., Any] | None = None


def get_aggrid_component() -> Callable[..., Any]:
    """Return the CCv2 mounting command, registering it on first use."""
    global _component
    if _component is None:
        _component = st.components.v2.component(
            name=_COMPONENT_NAME,
            js=_JS_GLOB,
            css=_CSS_GLOB,
            html="<div></div>",
            isolate_styles=False,  # AG-Grid injects styles globally
        )
    return _component
