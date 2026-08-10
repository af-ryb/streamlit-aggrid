"""Auto-mark the browser suite so the fast loop can select against it.

Everything under ``test/`` drives a real Streamlit app through Playwright
except ``test/unit/``, which is pure Python. Marking by location keeps
individual test files free of boilerplate and means a new e2e file is
correctly classified the moment it is created.
"""

from pathlib import Path

import pytest

UNIT_DIR = (Path(__file__).parent / "unit").resolve()


def pytest_collection_modifyitems(items):
    for item in items:
        path = Path(str(item.fspath)).resolve()
        if UNIT_DIR in path.parents:
            continue
        item.add_marker(pytest.mark.e2e)
