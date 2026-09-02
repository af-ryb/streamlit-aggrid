"""Number predicates shared by the built-in validators.

``ratio.py`` and ``color_scale.py`` both need "an int or a float that is not
a bool": ``bool`` is an ``int`` subclass, so ``isinstance(x, int)`` would let
a ``True`` multiplier or anchor through as ``1``. ``color_scale.py`` also
needs finiteness — ``float("nan")`` serialises to JSON and then paints
nothing in the browser, which is the silent failure that validator exists
to prevent.
"""

from __future__ import annotations

from math import isfinite
from typing import Any


def is_number(value: Any) -> bool:
    """An ``int`` or ``float`` that is not a ``bool``."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def is_finite_number(value: Any) -> bool:
    """``is_number`` and neither NaN nor infinite."""
    return is_number(value) and isfinite(value)
