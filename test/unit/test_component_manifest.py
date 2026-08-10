"""The Components v2 manifest must be discoverable at runtime.

Without it, ``st.components.v2.component(js="index-*.js")`` cannot resolve the
glob and the frontend bundle falls back to being inlined into every session.

Pure Python — no browser, no Streamlit runtime.
"""

from pathlib import Path

from streamlit.components.v2.manifest_scanner import scan_component_manifests

PACKAGE_ROOT = (Path(__file__).resolve().parents[2] / "st_aggrid").resolve()
BUILD_DIR = PACKAGE_ROOT / "frontend" / "build"

DISTRIBUTION_NAME = "st-aggrid"
COMPONENT_NAME = "aggrid"


def _find_manifest():
    for manifest, package_root in scan_component_manifests():
        if manifest.name == DISTRIBUTION_NAME:
            return manifest, Path(package_root).resolve()
    return None, None


def test_manifest_is_discovered():
    manifest, package_root = _find_manifest()
    assert manifest is not None, (
        f"No manifest named {DISTRIBUTION_NAME!r}. If the distribution was just "
        "renamed, run `uv lock && uv sync` so the installed metadata matches."
    )
    assert package_root == PACKAGE_ROOT


def test_manifest_declares_the_aggrid_component():
    manifest, _ = _find_manifest()
    assert [c.name for c in manifest.components] == [COMPONENT_NAME]
    assert manifest.components[0].asset_dir == "frontend/build"


def test_asset_dir_resolves_to_the_build_output():
    manifest, package_root = _find_manifest()
    resolved = manifest.components[0].resolve_asset_root(package_root)
    assert Path(resolved).resolve() == BUILD_DIR


def test_each_asset_glob_resolves_to_exactly_one_file():
    # st.components.v2.component() raises unless a glob matches exactly one
    # file, so a stale bundle left behind by a previous build is a hard error.
    assert len(list(BUILD_DIR.glob("index-*.js"))) == 1
    assert len(list(BUILD_DIR.glob("index-*.css"))) == 1
