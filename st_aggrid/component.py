import streamlit as st
from pathlib import Path

_BUILD_DIR = Path(__file__).parent / "frontend" / "build"

_aggrid_component = st.components.v2.component(
    name="streamlit_aggrid.aggrid",
    js=(_BUILD_DIR / "index.js").read_text(),
    css=(_BUILD_DIR / "style.css").read_text(),
    html="<div></div>",
    isolate_styles=False,  # AG-Grid injects styles globally
)
