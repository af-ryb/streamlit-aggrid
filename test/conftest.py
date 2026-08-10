"""Auto-mark the browser suite so the fast loop can select against it.

Everything under ``test/`` drives a real Streamlit app through Playwright
except ``test/unit/``, which is pure Python. Marking by location keeps
individual test files free of boilerplate and means a new e2e file is
correctly classified the moment it is created.
"""

import sys
from pathlib import Path

import pytest

TEST_DIR = Path(__file__).parent.resolve()
UNIT_DIR = (TEST_DIR / "unit").resolve()

# Shared helper modules live directly in ``test/`` (``e2e_utils``,
# ``ratio_fixture``). Browser tests get that directory on ``sys.path`` for free
# because pytest prepends the rootdir of each collected file; ``test/unit/``
# does not, and a Streamlit app launched as a subprocess only ever sees its own
# directory. Adding it here makes one import path work from all three.
if str(TEST_DIR) not in sys.path:
    sys.path.insert(0, str(TEST_DIR))


def pytest_collection_modifyitems(items):
    for item in items:
        path = item.path.resolve()
        if UNIT_DIR in path.parents:
            continue
        item.add_marker(pytest.mark.e2e)
