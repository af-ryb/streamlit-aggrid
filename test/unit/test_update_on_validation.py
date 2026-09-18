"""Unit tests for the ``update_on`` guard on lifecycle events.

Pure-Python (no browser, no Streamlit) — fast to run via
``pytest test/unit/test_update_on_validation.py``.

``gridReady`` and ``firstDataRendered`` are served as grid-creation callbacks
rather than as subscriptions, so they work as zero-interaction triggers but
cannot be debounced: see :func:`st_aggrid.aggrid.validate_update_on` for why,
and the README's Auto-Collect section for the user-facing version.
"""

import pytest

from st_aggrid.aggrid import LIFECYCLE_UPDATE_ON_EVENTS, validate_update_on


def test_ordinary_events_pass():
    validate_update_on(["selectionChanged", "filterChanged", "sortChanged"])


def test_debounced_tuple_form_passes_for_ordinary_events():
    validate_update_on([("columnResized", 400), "columnPinned"])


def test_none_passes():
    """`AgGrid` validates before applying its default, and the default is
    itself a valid list — so `None` must simply be allowed through."""
    validate_update_on(None)


def test_empty_passes():
    validate_update_on([])


@pytest.mark.parametrize("event", sorted(LIFECYCLE_UPDATE_ON_EVENTS))
def test_lifecycle_event_passes_as_a_bare_name(event):
    """The feature itself: both names are zero-interaction triggers now, not
    rejected entries."""
    validate_update_on(["sortChanged", event])


@pytest.mark.parametrize("event", sorted(LIFECYCLE_UPDATE_ON_EVENTS))
def test_lifecycle_event_is_rejected_in_tuple_form(event):
    """A debounce coalesces a burst of firings; an event emitted at most once
    per grid creation has no burst, so the request cannot be honoured."""
    with pytest.raises(ValueError) as excinfo:
        validate_update_on([(event, 400)])
    assert event in str(excinfo.value)


def test_list_form_of_the_debounced_entry_is_rejected_too():
    """A JSON round-trip turns the tuple into a list; the guard must not care
    which of the two it is looking at."""
    with pytest.raises(ValueError):
        validate_update_on([["gridReady", 400]])


def test_message_names_every_offender_and_points_somewhere():
    """One raise listing all offenders, not one per name — a caller who
    debounced both should not have to fix them one round-trip at a time."""
    debounced = [(event, 400) for event in sorted(LIFECYCLE_UPDATE_ON_EVENTS)]
    with pytest.raises(ValueError) as excinfo:
        validate_update_on(debounced)
    message = str(excinfo.value)
    for event in LIFECYCLE_UPDATE_ON_EVENTS:
        assert event in message
    # The point of failing loudly is telling the caller what to do instead.
    assert "bare event name" in message


def test_unknown_names_are_not_rejected():
    """Deliberately narrow. AG-Grid's event set changes with every release and
    this package has no truthful copy of it, so a name that is merely
    misspelled still fails silently — a known, separate gap."""
    validate_update_on(["thisIsNotAnAgGridEvent", ("alsoNotAnEvent", 200)])
