"""The number predicate shared by the built-in validators.

`bool` is an `int` subclass, so a plain `isinstance(x, int)` accepts `True`
as a multiplier or an anchor. Both validators need the strict rule; the
colour-scale one additionally needs finiteness, because NaN and infinity
would pass JSON serialisation and then paint nothing in the browser.
"""

from st_aggrid._numbers import is_finite_number, is_number


def test_ints_and_floats_are_numbers():
    assert is_number(1)
    assert is_number(1.5)
    assert is_number(-0.0)


def test_bools_and_strings_are_not_numbers():
    assert not is_number(True)
    assert not is_number(False)
    assert not is_number("1")
    assert not is_number(None)


def test_nan_and_infinity_are_numbers_but_not_finite():
    assert is_number(float("nan"))
    assert is_number(float("inf"))
    assert not is_finite_number(float("nan"))
    assert not is_finite_number(float("inf"))
    assert not is_finite_number(float("-inf"))


def test_finite_numbers_pass_both():
    assert is_finite_number(0)
    assert is_finite_number(-1.25)
    assert not is_finite_number(True)
