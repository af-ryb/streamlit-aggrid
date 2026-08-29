"""The Components v2 manifest must be discoverable at runtime.

Without it, ``st.components.v2.component(js="index-*.js")`` cannot resolve the
glob and registration raises ``StreamlitAPIException`` ("must be declared in
pyproject.toml with asset_dir") — there is no inlined-bundle fallback.

Pure Python — no browser, no Streamlit runtime.
"""

from pathlib import Path

from streamlit.components.v2.manifest_scanner import scan_component_manifests

try:
    import tomllib  # Python 3.11+ standard library.

    _TOML_MODE = "rb"
except ModuleNotFoundError:
    import toml as tomllib  # 3.10 fallback; already a Streamlit dependency.

    _TOML_MODE = "r"

import st_aggrid.component as component_module

PACKAGE_ROOT = (Path(__file__).resolve().parents[2] / "st_aggrid").resolve()
BUILD_DIR = PACKAGE_ROOT / "frontend" / "build"
REPO_ROOT = PACKAGE_ROOT.parent

DISTRIBUTION_NAME = "st-aggrid"
COMPONENT_NAME = "aggrid"


def _load_toml(path: Path) -> dict:
    with open(path, _TOML_MODE) as f:
        return tomllib.load(f)


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


def test_component_name_matches_the_manifest():
    """``_COMPONENT_NAME`` and the manifest can drift independently — each
    edits a different file and both look plausible in isolation. If they
    disagree, ``st.components.v2.component()`` mounts under a name the
    manifest never declared and the component is dead on first render.
    """
    manifest, _ = _find_manifest()
    expected = f"{manifest.name}.{manifest.components[0].name}"
    assert component_module._COMPONENT_NAME == expected


def test_nested_pyproject_version_matches_root_pyproject_version():
    """The manifest's ``version`` is copy-pasted from the root
    ``pyproject.toml`` by hand on every release. If a version bump only
    touches one of the two files, the installed manifest silently reports a
    stale version with no error anywhere in the install or render path.
    """
    root = _load_toml(REPO_ROOT / "pyproject.toml")
    nested = _load_toml(PACKAGE_ROOT / "pyproject.toml")
    assert nested["project"]["version"] == root["project"]["version"]


def test_nested_pyproject_name_matches_root_pyproject_name():
    """The nested manifest's ``[project] name`` must equal the root
    distribution name — the manifest scanner matches manifests to the
    installed distribution by this name. If they diverge, the manifest is
    never found and registration raises instead of rendering a grid.
    """
    root = _load_toml(REPO_ROOT / "pyproject.toml")
    nested = _load_toml(PACKAGE_ROOT / "pyproject.toml")
    assert nested["project"]["name"] == root["project"]["name"]
