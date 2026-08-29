"""JsCode, walk_grid_options and StAggridTheme."""

from st_aggrid.shared import (
    AgGridTheme,
    JsCode,
    StAggridTheme,
    walk_grid_options,
)


def test_jscode_is_wrapped_in_placeholders_and_flattened():
    code = JsCode(
        """
        function(params) {
            return params.value
        }
        """
    ).js_code
    assert code.startswith("::JSCODE::")
    assert code.endswith("::JSCODE::")
    assert "\n" not in code
    assert "return params.value" in code


def test_jscode_strips_comments():
    code = JsCode(
        """
        function(params) {
            // never send this to the browser
            return 1
        }
        """
    ).js_code
    assert "//" not in code
    assert "never send this" not in code


def test_jscode_strips_block_comments():
    code = JsCode("function(){ /* gone */ return 1 }").js_code
    assert "gone" not in code


def test_walk_grid_options_applies_func_to_every_leaf():
    options = {
        "a": 1,
        "nested": {"b": 2},
        "list": [{"c": 3}],
    }
    walk_grid_options(options, lambda v: v * 10 if isinstance(v, int) else v)
    assert options["a"] == 10
    assert options["nested"]["b"] == 20
    assert options["list"][0]["c"] == 30


def test_theme_enum_membership():
    assert "streamlit" in AgGridTheme
    assert "not-a-theme" not in AgGridTheme


def test_custom_theme_builds_a_serializable_dict():
    theme = (
        StAggridTheme(base="balham")
        .with_params(accentColor="#ff0000", rowHeight=30)
        .with_parts("colorSchemeDark", "iconSetMaterial")
    )
    assert theme["themeName"] == "custom"
    assert theme["base"] == "balham"
    assert theme["params"] == {"accentColor": "#ff0000", "rowHeight": 30}
    assert theme["parts"] == ["colorSchemeDark", "iconSetMaterial"]


def test_theme_parts_are_deduplicated_in_order():
    theme = StAggridTheme(base="alpine").with_parts("a", "b").with_parts("b", "c")
    assert theme["parts"] == ["a", "b", "c"]


def test_theme_without_a_base_has_no_theme_name():
    theme = StAggridTheme()
    assert "themeName" not in theme
    assert theme["params"] == {}
    assert theme["parts"] == []
