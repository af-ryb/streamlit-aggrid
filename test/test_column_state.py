"""Unit tests for st_aggrid.column_state visibility helpers.

Pure-Python (no browser, no Streamlit) — fast to run via
``pytest test/test_column_state.py``.
"""

import pytest

from st_aggrid.column_state import (
    derive_overlay,
    derive_user_hidden,
    set_visibility,
    visibility_state,
)


# --- set_visibility --------------------------------------------------------


def test_set_visibility_normal_mode():
    state = set_visibility(visible_col_ids=["b", "a"], hidden_col_ids=["c"])
    # Sorted by colId; visible -> hide False, hidden -> hide True.
    assert state == [
        {"colId": "a", "hide": False},
        {"colId": "b", "hide": False},
        {"colId": "c", "hide": True},
    ]


def test_set_visibility_omits_unlisted_columns():
    state = set_visibility(visible_col_ids=["a"], hidden_col_ids=["b"])
    assert {e["colId"] for e in state} == {"a", "b"}  # "c" never mentioned


def test_set_visibility_hidden_wins_on_overlap():
    state = set_visibility(visible_col_ids=["a"], hidden_col_ids=["a"])
    assert state == [{"colId": "a", "hide": True}]


def test_set_visibility_pivot_uniform_aggfunc():
    state = set_visibility(
        visible_col_ids=["a"],
        hidden_col_ids=["b"],
        pivot_mode=True,
        value_agg_func="sum",
    )
    assert state == [
        {"colId": "a", "aggFunc": "sum"},
        {"colId": "b", "aggFunc": None},  # explicit None clears the aggregation
    ]


def test_set_visibility_pivot_per_column_aggfunc():
    state = set_visibility(
        visible_col_ids=["a", "b"],
        hidden_col_ids=[],
        pivot_mode=True,
        value_agg_func={"a": "ratioSum", "b": "growthRatio"},
    )
    assert state == [
        {"colId": "a", "aggFunc": "ratioSum"},
        {"colId": "b", "aggFunc": "growthRatio"},
    ]


def test_set_visibility_pivot_requires_aggfunc_for_visible():
    with pytest.raises((ValueError, TypeError)):
        set_visibility(visible_col_ids=["a"], hidden_col_ids=[], pivot_mode=True)


def test_set_visibility_pivot_mapping_missing_entry_raises():
    with pytest.raises(ValueError):
        set_visibility(
            visible_col_ids=["a", "b"],
            hidden_col_ids=[],
            pivot_mode=True,
            value_agg_func={"a": "sum"},  # missing "b"
        )


def test_set_visibility_pivot_hide_only_needs_no_aggfunc():
    # Hiding-only delta: no visible columns, so value_agg_func is unnecessary.
    state = set_visibility(
        visible_col_ids=[], hidden_col_ids=["a", "b"], pivot_mode=True
    )
    assert state == [
        {"colId": "a", "aggFunc": None},
        {"colId": "b", "aggFunc": None},
    ]


# --- visibility_state (union rule) -----------------------------------------


def test_visibility_state_union_rule_normal():
    governed = ["a", "b", "c", "d"]
    state = visibility_state(
        governed_col_ids=governed,
        included_col_ids=["a", "b", "c"],
        user_hidden_col_ids=["b"],
    )
    by_id = {e["colId"]: e for e in state}
    # visible = included - user_hidden = {a, c}; hidden = governed - visible = {b, d}
    assert by_id["a"]["hide"] is False
    assert by_id["c"]["hide"] is False
    assert by_id["b"]["hide"] is True  # user-hidden though control-included
    assert by_id["d"]["hide"] is True  # control-excluded
    assert set(by_id) == set(governed)  # every governed column gets an entry


def test_visibility_state_only_touches_governed():
    state = visibility_state(
        governed_col_ids=["a", "b"],
        included_col_ids=["a", "z"],  # z is not governed
        user_hidden_col_ids=["y"],  # y is not governed
    )
    assert {e["colId"] for e in state} == {"a", "b"}


def test_visibility_state_pivot():
    state = visibility_state(
        governed_col_ids=["a", "b", "c"],
        included_col_ids=["a", "b"],
        user_hidden_col_ids=["b"],
        pivot_mode=True,
        value_agg_func="ratioSum",
    )
    by_id = {e["colId"]: e for e in state}
    assert by_id["a"]["aggFunc"] == "ratioSum"  # visible
    assert by_id["b"]["aggFunc"] is None  # user-hidden
    assert by_id["c"]["aggFunc"] is None  # control-excluded


# --- derive_user_hidden ----------------------------------------------------


def test_derive_user_hidden_none_state():
    assert (
        derive_user_hidden(
            None, governed_col_ids=["a"], control_included_at_capture=["a"]
        )
        == []
    )


def test_derive_user_hidden_normal_separates_manual_from_control():
    governed = ["a", "b", "c", "d"]
    # Control included a, b, c (not d). Captured: b hidden, d hidden.
    captured = [
        {"colId": "a", "hide": False},
        {"colId": "b", "hide": True},  # included + hidden -> user hid it
        {"colId": "c", "hide": False},
        {"colId": "d", "hide": True},  # excluded + hidden -> control's doing
    ]
    user_hidden = derive_user_hidden(
        captured,
        governed_col_ids=governed,
        control_included_at_capture=["a", "b", "c"],
    )
    assert user_hidden == ["b"]  # d filtered out (not control-included)


def test_derive_user_hidden_pivot_uses_aggfunc():
    captured = [
        {"colId": "a", "aggFunc": "sum"},  # visible
        {"colId": "b"},  # included but no aggFunc -> user hid it
    ]
    user_hidden = derive_user_hidden(
        captured,
        governed_col_ids=["a", "b"],
        control_included_at_capture=["a", "b"],
        pivot_mode=True,
    )
    assert user_hidden == ["b"]


def test_derive_user_hidden_drops_on_unhide():
    # User previously hid b and c; now un-hides c via the Columns panel.
    captured = [
        {"colId": "a", "hide": False},
        {"colId": "b", "hide": True},
        {"colId": "c", "hide": False},  # un-hidden
    ]
    user_hidden = derive_user_hidden(
        captured,
        governed_col_ids=["a", "b", "c"],
        control_included_at_capture=["a", "b", "c"],
    )
    assert user_hidden == ["b"]  # c dropped out


# --- round-trip: union rule survives a control change ----------------------


def test_round_trip_manual_hide_survives_control_toggle():
    governed = ["a", "b", "c", "d"]
    included = ["a", "b", "c"]

    # 1) Initial render, no manual hides yet.
    delta1 = visibility_state(
        governed_col_ids=governed,
        included_col_ids=included,
        user_hidden_col_ids=[],
    )
    assert {e["colId"]: e["hide"] for e in delta1} == {
        "a": False,
        "b": False,
        "c": False,
        "d": True,
    }

    # 2) User manually hides b -> grid captures this live state.
    captured = [
        {"colId": "a", "hide": False},
        {"colId": "b", "hide": True},
        {"colId": "c", "hide": False},
        {"colId": "d", "hide": True},
    ]
    user_hidden = derive_user_hidden(
        captured,
        governed_col_ids=governed,
        control_included_at_capture=included,
    )
    assert user_hidden == ["b"]

    # 3) Control selection changes (now includes d too). b stays hidden.
    delta2 = visibility_state(
        governed_col_ids=governed,
        included_col_ids=["a", "b", "c", "d"],
        user_hidden_col_ids=user_hidden,
    )
    assert {e["colId"]: e["hide"] for e in delta2} == {
        "a": False,
        "b": True,  # manual hide survived the control change
        "c": False,
        "d": False,
    }


# --- visibility_state: user_shown (signed overlay) -------------------------


def test_visibility_state_user_shown_default_is_backcompat():
    # Omitting user_shown must reproduce the old behaviour exactly.
    governed = ["a", "b", "c", "d"]
    without = visibility_state(
        governed_col_ids=governed,
        included_col_ids=["a", "b", "c"],
        user_hidden_col_ids=["b"],
    )
    with_empty = visibility_state(
        governed_col_ids=governed,
        included_col_ids=["a", "b", "c"],
        user_hidden_col_ids=["b"],
        user_shown_col_ids=[],
    )
    assert without == with_empty


def test_visibility_state_user_shown_normal_revives_excluded():
    governed = ["a", "b", "c", "d"]
    state = visibility_state(
        governed_col_ids=governed,
        included_col_ids=["a", "b"],
        user_hidden_col_ids=[],
        user_shown_col_ids=["d"],  # d is control-excluded but user showed it
    )
    by_id = {e["colId"]: e["hide"] for e in state}
    # visible = (included - user_hidden) ∪ (user_shown ∩ excluded) = {a, b, d}
    assert by_id == {"a": False, "b": False, "c": True, "d": False}


def test_visibility_state_user_shown_pivot_revives_excluded():
    state = visibility_state(
        governed_col_ids=["a", "b", "c"],
        included_col_ids=["a"],
        user_shown_col_ids=["c"],
        pivot_mode=True,
        value_agg_func="ratioSum",
    )
    by_id = {e["colId"]: e.get("aggFunc") for e in state}
    assert by_id["a"] == "ratioSum"  # included
    assert by_id["b"] is None  # excluded, not shown
    assert by_id["c"] == "ratioSum"  # excluded but user-shown -> visible


def test_visibility_state_user_shown_only_applies_to_excluded():
    # A colId both included and (spuriously) in user_shown stays governed by
    # included/user_hidden — user_shown never overrides a user_hidden.
    governed = ["a", "b"]
    state = visibility_state(
        governed_col_ids=governed,
        included_col_ids=["a", "b"],
        user_hidden_col_ids=["a"],
        user_shown_col_ids=["a"],  # a is included, so the shown-set is a no-op
    )
    by_id = {e["colId"]: e["hide"] for e in state}
    assert by_id == {"a": True, "b": False}  # user_hidden wins over a stray shown


def test_visibility_state_user_shown_ignores_ungoverned():
    state = visibility_state(
        governed_col_ids=["a", "b"],
        included_col_ids=["a"],
        user_shown_col_ids=["z"],  # not governed
    )
    assert {e["colId"] for e in state} == {"a", "b"}


# --- derive_overlay (dual derive, one snapshot) ----------------------------


def test_derive_overlay_none_state():
    assert derive_overlay(
        None, governed_col_ids=["a", "b"], control_included_at_capture=["a"]
    ) == ([], [])


def test_derive_overlay_normal_returns_pair():
    governed = ["a", "b", "c", "d"]
    # Control included a, b (not c, d). Captured: b hidden, d shown.
    captured = [
        {"colId": "a", "hide": False},
        {"colId": "b", "hide": True},  # included + hidden -> user hid it
        {"colId": "c", "hide": True},  # excluded + hidden -> control's doing
        {"colId": "d", "hide": False},  # excluded + visible -> user showed it
    ]
    hidden, shown = derive_overlay(
        captured,
        governed_col_ids=governed,
        control_included_at_capture=["a", "b"],
    )
    assert hidden == ["b"]
    assert shown == ["d"]


def test_derive_overlay_pivot_returns_pair():
    captured = [
        {"colId": "a", "aggFunc": "sum"},  # included + visible
        {"colId": "b"},  # included + no aggFunc -> user hid it
        {"colId": "c", "aggFunc": None},  # excluded + hidden -> control's doing
        {"colId": "d", "aggFunc": "sum"},  # excluded + visible -> user showed it
    ]
    hidden, shown = derive_overlay(
        captured,
        governed_col_ids=["a", "b", "c", "d"],
        control_included_at_capture=["a", "b"],
        pivot_mode=True,
    )
    assert hidden == ["b"]
    assert shown == ["d"]


def test_derive_overlay_sets_are_disjoint():
    # No governed column can land in both sets (disjoint candidate domains).
    captured = [
        {"colId": "a", "hide": True},
        {"colId": "b", "hide": False},
        {"colId": "c", "hide": True},
        {"colId": "d", "hide": False},
    ]
    hidden, shown = derive_overlay(
        captured,
        governed_col_ids=["a", "b", "c", "d"],
        control_included_at_capture=["a", "b"],
    )
    assert set(hidden).isdisjoint(set(shown))


def test_derive_overlay_user_hidden_matches_legacy():
    # The hidden half must equal the legacy single-set derive.
    governed = ["a", "b", "c", "d"]
    included = ["a", "b", "c"]
    captured = [
        {"colId": "a", "hide": False},
        {"colId": "b", "hide": True},
        {"colId": "c", "hide": False},
        {"colId": "d", "hide": True},
    ]
    hidden, _shown = derive_overlay(
        captured,
        governed_col_ids=governed,
        control_included_at_capture=included,
    )
    assert hidden == derive_user_hidden(
        captured,
        governed_col_ids=governed,
        control_included_at_capture=included,
    )


def test_round_trip_user_shown_survives_control_save_load():
    # Contract scenario 4: exclude a family, user manually shows one excluded
    # column; that show survives into the next delta.
    governed = ["cpi", "ctr", "arpu7"]
    included = ["arpu7"]  # performance family (cpi/ctr) excluded

    # User manually re-adds cpi via the Columns panel -> captured visible.
    captured = [
        {"colId": "cpi", "aggFunc": "ratioSum"},  # excluded but shown
        {"colId": "ctr", "aggFunc": None},  # excluded, untouched
        {"colId": "arpu7", "aggFunc": "ratioSum"},  # included
    ]
    hidden, shown = derive_overlay(
        captured,
        governed_col_ids=governed,
        control_included_at_capture=included,
        pivot_mode=True,
    )
    assert hidden == []
    assert shown == ["cpi"]

    # Rebuilt delta (e.g. after save->load) keeps cpi visible.
    delta = visibility_state(
        governed_col_ids=governed,
        included_col_ids=included,
        user_hidden_col_ids=hidden,
        user_shown_col_ids=shown,
        pivot_mode=True,
        value_agg_func="ratioSum",
    )
    by_id = {e["colId"]: e.get("aggFunc") for e in delta}
    assert by_id["cpi"] == "ratioSum"  # user_shown survived
    assert by_id["ctr"] is None
    assert by_id["arpu7"] == "ratioSum"
