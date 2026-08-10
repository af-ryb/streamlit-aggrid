"""Callback arity detection and wrapping.

Callbacks used to be invoked with no arguments. They may now take the
AgGridResult, and both shapes must keep working — so the wrapper inspects the
signature rather than changing the contract for everyone.

Pure Python — no browser, no Streamlit runtime.
"""

import functools

import pytest

from st_aggrid.aggrid import _callback_wants_result, _wrap_callback


# --- _callback_wants_result ------------------------------------------------


def test_zero_arg_function_does_not_want_the_result():
    def cb():
        pass

    assert _callback_wants_result(cb) is False


def test_one_positional_arg_wants_the_result():
    def cb(result):
        pass

    assert _callback_wants_result(cb) is True


def test_var_positional_wants_the_result():
    def cb(*args):
        pass

    assert _callback_wants_result(cb) is True


def test_defaulted_positional_arg_wants_the_result():
    def cb(result=None):
        pass

    assert _callback_wants_result(cb) is True


def test_keyword_only_arg_does_not_want_the_result():
    def cb(*, result=None):
        pass

    assert _callback_wants_result(cb) is False


def test_lambda_arity_is_detected():
    assert _callback_wants_result(lambda: None) is False
    assert _callback_wants_result(lambda r: None) is True


def test_partial_with_the_arg_already_bound_does_not_want_the_result():
    def cb(a, b):
        pass

    assert _callback_wants_result(functools.partial(cb, 1, 2)) is False


def test_callable_object_is_inspected_without_counting_self():
    class Handler:
        def __call__(self, result):
            pass

    assert _callback_wants_result(Handler()) is True


def test_unreadable_signature_is_treated_as_zero_arity():
    # Some C callables have no introspectable signature. Guessing "takes an
    # argument" would raise TypeError at callback time, so fail the safe way.
    class Weird:
        __call__ = None

    assert _callback_wants_result(Weird()) is False


# --- _wrap_callback --------------------------------------------------------


def test_none_becomes_a_no_op():
    wrapped = _wrap_callback(None, key="g", original_data=None)
    assert wrapped() is None


def test_zero_arg_callback_is_passed_through_unchanged():
    def cb():
        pass

    assert _wrap_callback(cb, key="g", original_data=None) is cb


def test_result_callback_without_a_key_is_rejected():
    def cb(result):
        pass

    with pytest.raises(ValueError, match="key"):
        _wrap_callback(cb, key=None, original_data=None)


def test_result_callback_receives_an_aggrid_result(monkeypatch):
    import types

    import st_aggrid.aggrid as aggrid_module
    from st_aggrid.result import AgGridResult

    component_result = types.SimpleNamespace(
        grid_state={"eventName": "selectionChanged"},
        api_response=None,
        notes=None,
    )
    monkeypatch.setattr(
        aggrid_module.st, "session_state", {"my_grid": component_result}
    )

    seen = []

    def cb(result):
        seen.append(result)

    _wrap_callback(cb, key="my_grid", original_data=None)()

    assert len(seen) == 1
    assert isinstance(seen[0], AgGridResult)
    assert seen[0].event_name == "selectionChanged"
