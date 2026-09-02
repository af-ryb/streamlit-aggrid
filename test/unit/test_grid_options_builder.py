"""GridOptionsBuilder derives colDefs from a DataFrame and merges overrides."""

import pandas as pd

from st_aggrid.grid_options_builder import GridOptionsBuilder
from st_aggrid.color_scale import COLOR_SCALE_CONTEXT_KEY


def _col(options, field):
    return {c["field"]: c for c in options["columnDefs"]}[field]


def test_from_dataframe_creates_one_col_def_per_column():
    df = pd.DataFrame({"names": ["a"], "ages": [1]})
    options = GridOptionsBuilder.from_dataframe(df).build()
    assert [c["field"] for c in options["columnDefs"]] == ["names", "ages"]
    assert [c["headerName"] for c in options["columnDefs"]] == ["names", "ages"]


def test_numeric_columns_get_numeric_types():
    df = pd.DataFrame({"ages": [1], "names": ["a"]})
    options = GridOptionsBuilder.from_dataframe(df).build()
    by_field = {c["field"]: c for c in options["columnDefs"]}
    assert by_field["ages"]["type"] == ["numericColumn", "numberColumnFilter"]
    assert by_field["names"]["type"] == []


def test_datetime_columns_get_date_types():
    df = pd.DataFrame({"when": pd.to_datetime(["2026-01-01"])})
    options = GridOptionsBuilder.from_dataframe(df).build()
    assert options["columnDefs"][0]["type"] == [
        "dateColumnFilter",
        "shortDateTimeFormat",
    ]


def test_from_dataframe_enables_fit_grid_width():
    df = pd.DataFrame({"a": [1]})
    options = GridOptionsBuilder.from_dataframe(df).build()
    assert options["autoSizeStrategy"] == {"type": "fitGridWidth"}


def test_dotted_column_names_suppress_field_dot_notation():
    df = pd.DataFrame({"a.b": [1]})
    options = GridOptionsBuilder.from_dataframe(df).build()
    assert options["suppressFieldDotNotation"] is True


def test_default_column_parameters_are_routed_to_default_col_def():
    df = pd.DataFrame({"a": [1]})
    options = GridOptionsBuilder.from_dataframe(df, filter=True).build()
    assert options["defaultColDef"]["filter"] is True


def test_configure_column_merges_into_an_existing_col_def():
    df = pd.DataFrame({"a": [1]})
    gb = GridOptionsBuilder.from_dataframe(df)
    gb.configure_column("a", header_name="Alpha", width=120)
    options = gb.build()
    assert options["columnDefs"][0]["headerName"] == "Alpha"
    assert options["columnDefs"][0]["width"] == 120


def test_configure_columns_batches_overrides():
    df = pd.DataFrame({"a": [1], "b": [2]})
    gb = GridOptionsBuilder.from_dataframe(df)
    gb.configure_columns(["a", "b"], resizable=False)
    options = gb.build()
    assert all(c["resizable"] is False for c in options["columnDefs"])


def test_configure_auto_height_sets_dom_layout():
    df = pd.DataFrame({"a": [1]})
    gb = GridOptionsBuilder.from_dataframe(df)
    gb.configure_auto_height(True)
    assert gb.build()["domLayout"] == "autoHeight"


def test_build_turns_col_defs_into_a_list():
    df = pd.DataFrame({"a": [1]})
    options = GridOptionsBuilder.from_dataframe(df).build()
    assert isinstance(options["columnDefs"], list)


def test_configure_color_scale_writes_grid_level_defaults():
    gb = GridOptionsBuilder()
    gb.configure_color_scale(scheme="positive")
    options = gb.build()
    assert options["context"][COLOR_SCALE_CONTEXT_KEY] == {"scheme": "positive"}


def test_configure_color_scale_omits_unset_keys():
    # An unset key must be absent, not None: the scheme's own default has to
    # survive, and a written null would override it.
    gb = GridOptionsBuilder()
    gb.configure_color_scale(scheme="neutral")
    declaration = gb.build()["context"][COLOR_SCALE_CONTEXT_KEY]
    assert "mode" not in declaration and "skip_non_positive" not in declaration


def test_configure_color_scale_writes_the_keys_it_is_given():
    gb = GridOptionsBuilder()
    gb.configure_color_scale(scheme="neutral", mode="minmax", skip_non_positive=False)
    assert gb.build()["context"][COLOR_SCALE_CONTEXT_KEY] == {
        "scheme": "neutral",
        "mode": "minmax",
        "skip_non_positive": False,
    }


def test_configure_color_scale_preserves_an_existing_grid_context():
    gb = GridOptionsBuilder()
    gb.configure_grid_options(context={"myAppState": 1})
    gb.configure_color_scale(scheme="positive")
    context = gb.build()["context"]
    assert context["myAppState"] == 1
    assert context[COLOR_SCALE_CONTEXT_KEY] == {"scheme": "positive"}


def test_configure_column_writes_the_column_declaration():
    gb = GridOptionsBuilder()
    gb.configure_column("cpi", color_scale=True)
    assert _col(gb.build(), "cpi")["context"] == {COLOR_SCALE_CONTEXT_KEY: True}


def test_configure_column_accepts_false_and_a_dict():
    gb = GridOptionsBuilder()
    gb.configure_column("installs", color_scale=False)
    gb.configure_column("arppu", color_scale={"scheme": "diverging"})
    options = gb.build()
    assert _col(options, "installs")["context"][COLOR_SCALE_CONTEXT_KEY] is False
    assert _col(options, "arppu")["context"][COLOR_SCALE_CONTEXT_KEY] == {
        "scheme": "diverging"
    }


def test_color_scale_does_not_clobber_a_ratio_declaration_from_an_earlier_call():
    # The exact collision this merge exists for: the consumer's metric columns
    # carry both declarations, and a replaced `context` would delete the
    # aggregation the column depends on.
    gb = GridOptionsBuilder()
    gb.configure_column("cpi", context={"stRatio": {"num": ["cost"], "den": ["installs"]}})
    gb.configure_column("cpi", color_scale=True)
    context = _col(gb.build(), "cpi")["context"]
    assert context["stRatio"] == {"num": ["cost"], "den": ["installs"]}
    assert context[COLOR_SCALE_CONTEXT_KEY] is True


def test_color_scale_does_not_clobber_a_context_passed_in_the_same_call():
    gb = GridOptionsBuilder()
    gb.configure_column(
        "cpi",
        color_scale=True,
        context={"stRatio": {"num": ["cost"], "den": ["installs"]}},
    )
    context = _col(gb.build(), "cpi")["context"]
    assert context["stRatio"] == {"num": ["cost"], "den": ["installs"]}
    assert context[COLOR_SCALE_CONTEXT_KEY] is True


def test_configure_column_without_color_scale_writes_no_context():
    gb = GridOptionsBuilder()
    gb.configure_column("cpi", width=120)
    assert "context" not in _col(gb.build(), "cpi")


def test_configure_color_scale_writes_every_phase_two_key():
    gb = GridOptionsBuilder()
    gb.configure_color_scale(
        scheme="diverging", mode="anchor", skip_non_positive=False,
        scope="parent", reverse=True, anchor=1.0, span=0.5, color="rgb(1, 2, 3)",
    )
    assert gb.build()["context"][COLOR_SCALE_CONTEXT_KEY] == {
        "scheme": "diverging",
        "mode": "anchor",
        "skip_non_positive": False,
        "scope": "parent",
        "reverse": True,
        "anchor": 1.0,
        "span": 0.5,
        "color": "rgb(1, 2, 3)",
    }


def test_configure_color_scale_omits_unset_phase_two_keys():
    gb = GridOptionsBuilder()
    gb.configure_color_scale(scheme="neutral", reverse=False)
    declaration = gb.build()["context"][COLOR_SCALE_CONTEXT_KEY]
    assert declaration == {"scheme": "neutral", "reverse": False}
    for absent in ("scope", "anchor", "span", "color"):
        assert absent not in declaration


def test_configure_color_scale_scheme_is_optional():
    # `mode="anchor"` with no scheme is a complete default set — the
    # validator resolves it to `diverging`.
    gb = GridOptionsBuilder()
    gb.configure_color_scale(mode="anchor", anchor=1.0, span=1.0)
    assert gb.build()["context"][COLOR_SCALE_CONTEXT_KEY] == {
        "mode": "anchor",
        "anchor": 1.0,
        "span": 1.0,
    }


def test_configure_color_scale_with_no_arguments_writes_an_empty_default():
    gb = GridOptionsBuilder()
    gb.configure_color_scale()
    assert gb.build()["context"][COLOR_SCALE_CONTEXT_KEY] == {}


def test_configure_color_scale_keeps_scheme_positional():
    gb = GridOptionsBuilder()
    gb.configure_color_scale("positive", "minmax", False)
    assert gb.build()["context"][COLOR_SCALE_CONTEXT_KEY] == {
        "scheme": "positive",
        "mode": "minmax",
        "skip_non_positive": False,
    }
