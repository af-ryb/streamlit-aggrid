"""``get_aggrid_component()`` must not register the component at import time.

``st.components.v2.component(...)`` only resolves against a manifest when a
Streamlit ``Runtime`` exists; outside one it raises ``StreamlitAPIException``
for a path-like ``js`` argument. ``st_aggrid/component.py`` works around this
by deferring registration to first call (``get_aggrid_component()``), caching
the result in the module-level ``_component``. If a future edit hoists the
``st.components.v2.component(...)`` call back to module scope — exactly what
this file's own history replaced — every plain-Python import of ``st_aggrid``
breaks, including this test suite itself.

This is a subprocess test, not an in-process one: by the time any test in
this process runs, ``st_aggrid`` has already been imported (and cached in
``sys.modules``) by pytest's collection or an earlier test module, so an
in-process import can't exercise a cold import. A cold interpreter is the
only way to observe either half of the property: whether the import raises,
and whether it left the registration cache unset. Both checks run inside the
same subprocess so the cache check can't be fooled by some other test in the
*subprocess* having already called ``get_aggrid_component()`` first — there
is no other test in that process.
"""

import subprocess
import sys


def test_import_does_not_register_the_component():
    program = (
        "import st_aggrid\n"
        "assert st_aggrid.component._component is None, ("
        "'st_aggrid.component._component was set by a plain import — "
        "the component is being registered eagerly instead of lazily'"
        ")\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", program],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "`import st_aggrid` failed (or the lazy-registration check failed) "
        "in a cold interpreter outside a Streamlit runtime:\n"
        f"--- stdout ---\n{result.stdout}\n"
        f"--- stderr ---\n{result.stderr}"
    )
