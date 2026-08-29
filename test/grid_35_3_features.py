"""Demo app exercising the AG-Grid 35.3 Enterprise features wired into the
component: Find (search & highlight), the native Quick Access Toolbar, and Cell
Notes (read-only + editable). Driven by a radio so one Streamlit server backs the
whole test module (see test_grid_35_3_features.py)."""

import pandas as pd
import streamlit as st

from st_aggrid import AgGrid


TESTS = st.radio(
    "Select Test",
    options=range(1, 6),
)

# "apple" appears in two cells ("apple", "pineapple") → Find should report 2 matches.
fruit_data = pd.DataFrame(
    {"fruit": ["apple", "banana", "grape", "pineapple", "cherry", "mango"]}
)

# Grouped data for the group-dimension notes probe.
group_data = pd.DataFrame(
    {
        "campaign": ["promo_a", "promo_a", "promo_b", "promo_b"],
        "country": ["US", "DE", "US", "DE"],
        "installs": [100, 50, 80, 40],
    }
)


def _cols():
    return [{"headerName": "Fruit", "field": "fruit"}]


def find_grid():
    """Find (35.3): findSearchValue passthrough highlights matches; the toolbar
    Find widget (show_find) renders alongside, with quick-search disabled so the
    two inputs don't both bind the grid."""
    go = {"columnDefs": _cols(), "findSearchValue": "apple"}
    AgGrid(
        fruit_data,
        go,
        enable_enterprise_modules=True,
        show_toolbar=True,
        show_find=True,
        show_search=False,
        key="find_grid",
    )


def toolbar_grid():
    """Native Quick Access Toolbar (35.3) via the `toolbar` convenience param."""
    AgGrid(
        fruit_data,
        {"columnDefs": _cols()},
        enable_enterprise_modules=True,
        toolbar={
            "items": [
                "agQuickFilterToolbarItem",
                "separator",
                "agFindToolbarItem",
            ]
        },
        key="toolbar_grid",
    )


def notes_readonly_grid():
    """Cell Notes (35.3), read-only display seeded from the host.

    Auto row ids are positional strings ("0", "1", …) for this static grid, so the
    note on row "0" / column "fruit" maps to the first cell."""
    AgGrid(
        fruit_data,
        {"columnDefs": _cols()},
        enable_enterprise_modules=True,
        notes={"0": {"fruit": "Read-only note on apple"}},
        notes_editable=False,
        key="notes_ro_grid",
    )


def notes_editable_grid():
    """Cell Notes (35.3), editable with sticky host write-back via result.notes."""
    r = AgGrid(
        fruit_data,
        {"columnDefs": _cols()},
        enable_enterprise_modules=True,
        notes={"0": {"fruit": "Editable note on apple"}},
        notes_editable=True,
        key="notes_edit_grid",
    )
    st.html(
        f"""
    <span>
    <h1> Notes Write-back </h1>
    <pre data-testid='notes-writeback'>{r.notes}</pre>
    </span>
    """
    )


def group_notes_probe_grid():
    """Diagnostic probe (debug_group_notes): renders a note on every row-group cell
    and logs each group's {field: key} dimension ancestry to the console.
    Foundation for the planned notes_groups feature."""
    go = {
        "columnDefs": [
            {"field": "campaign", "rowGroup": True, "hide": True},
            {"field": "country", "rowGroup": True, "hide": True},
            {"field": "installs", "aggFunc": "sum"},
        ],
        "groupDefaultExpanded": -1,
    }
    AgGrid(
        group_data,
        go,
        enable_enterprise_modules=True,
        debug=True,
        debug_group_notes=True,
        key="group_notes_probe",
    )


if TESTS == 1:
    find_grid()

if TESTS == 2:
    toolbar_grid()

if TESTS == 3:
    notes_readonly_grid()

if TESTS == 4:
    notes_editable_grid()

if TESTS == 5:
    group_notes_probe_grid()
