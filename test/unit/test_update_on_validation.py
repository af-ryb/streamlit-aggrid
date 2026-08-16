"""Unit tests for the ``update_on`` guard against structurally dead events.

Pure-Python (no browser, no Streamlit) — fast to run via
``pytest test/unit/test_update_on_validation.py``.

The guard exists because two AG-Grid event names cannot work through
``update_on`` and fail silently rather than loudly: see
:func:`st_aggrid.aggrid.validate_update_on` for why, and the README's
Auto-Collect section for the user-facing version.
"""

import pytest

from st_aggrid.aggrid import UNSUPPORTED_UPDATE_ON_EVENTS, validate_update_on


def test_ordinary_events_pass():
    validate_update_on(["selectionChanged", "filterChanged", "sortChanged"])


def test_debounced_tuple_form_passes():
    validate_update_on([("columnResized", 400), "columnPinned"])


def test_none_passes():
    """`AgGrid` validates before applying its default, and the default is
    itself a valid list — so `None` must simply be allowed through."""
    validate_update_on(None)


def test_empty_passes():
    validate_update_on([])


@pytest.mark.parametrize("event", sorted(UNSUPPORTED_UPDATE_ON_EVENTS))
def test_unsupported_event_is_rejected(event):
    with pytest.raises(ValueError) as excinfo:
        validate_update_on(["sortChanged", event])
    assert event in str(excinfo.value)


@pytest.mark.parametrize("event", sorted(UNSUPPORTED_UPDATE_ON_EVENTS))
def test_unsupported_event_is_rejected_in_tuple_form(event):
    """The debounced form has to be unwrapped before the name is checked, or
    `("gridReady", 400)` would slip past the guard it exists for."""
    with pytest.raises(ValueError):
        validate_update_on([(event, 400)])


def test_message_names_every_offender_and_points_somewhere():
    """One raise listing all offenders, not one per name — a caller who used
    both should not have to fix them one round-trip at a time."""
    with pytest.raises(ValueError) as excinfo:
        validate_update_on(list(UNSUPPORTED_UPDATE_ON_EVENTS))
    message = str(excinfo.value)
    for event in UNSUPPORTED_UPDATE_ON_EVENTS:
        assert event in message
    # The point of failing loudly is telling the caller what to do instead.
    assert "sortChanged" in message or "selectionChanged" in message


def test_unknown_names_are_not_rejected():
    """Deliberately a denylist, not an allowlist. AG-Grid's event set changes
    with every release and this package has no truthful copy of it, so an
    allowlist would reject valid new events. A name that is merely misspelled
    still fails silently — that is a known, separate gap."""
    validate_update_on(["thisIsNotAnAgGridEvent"])
