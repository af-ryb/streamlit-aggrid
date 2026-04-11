import json
import pathlib
import re
from collections.abc import Mapping
from enum import Enum, EnumMeta
from typing import List, Literal, Optional, TypedDict


def _get_all_grid_options():
    json_root = pathlib.Path(__file__).parent / "json"
    with open(json_root / "gridOptions.json") as f:
        return json.load(f)


def _get_all_column_props():
    json_root = pathlib.Path(__file__).parent / "json"
    with open(json_root / "columnProps.json") as f:
        return json.load(f)


class MetaEnum(EnumMeta):
    def __contains__(cls, item):
        try:
            cls(item)
        except ValueError:
            return False
        return True


class BaseEnum(Enum, metaclass=MetaEnum):
    pass


class JsCode:
    def __init__(self, js_code: str):
        """Wrapper around a js function to be injected on gridOptions.
        Code is not checked at all.
        Set allow_unsafe_jscode=True on AgGrid call to use it.
        Code is rebuilt on client using new Function Syntax.

        Args:
            js_code (str): javascript function code as str
        """
        match_js_comment_expression = r"\/\*[\s\S]*?\*\/|([^\\:]|^)\/\/.*$"
        js_code = re.sub(
            re.compile(match_js_comment_expression, re.MULTILINE), r"\1", js_code
        )

        js_placeholder = "::JSCODE::"
        one_line_jscode = re.sub(r"\s+|\r\s*|\n+", " ", js_code, flags=re.MULTILINE)

        self.js_code = f"{js_placeholder}{one_line_jscode}{js_placeholder}"


def walk_grid_options(go, func):
    """Recursively walk grid options applying func at each leaf node.

    Args:
        go (dict): gridOptions dictionary
        func (callable): a function to apply at leaf nodes
    """
    if isinstance(go, (Mapping, list)):
        for i, k in enumerate(go):
            if isinstance(go[k], Mapping):
                walk_grid_options(go[k], func)
            elif isinstance(go[k], list):
                for j in go[k]:
                    walk_grid_options(j, func)
            else:
                go[k] = func(go[k])


class AgGridTheme(BaseEnum):
    STREAMLIT = "streamlit"
    ALPINE = "alpine"
    BALHAM = "balham"
    MATERIAL = "material"


class StAggridThemeType(TypedDict):
    themeName: str
    base: Literal["alpine", "balham", "quartz"]
    params: Optional[Mapping[str, str | int]]
    parts: Optional[List[str]]


class StAggridTheme(dict):
    def __init__(self, base: Optional[Literal["alpine", "balham", "quartz"]] = None):
        super().__init__()

        self["params"] = {}
        self["parts"] = list()
        if base:
            self["themeName"] = "custom"
            self.base(base)

    def base(self, base: Literal["alpine", "balham", "quartz"]):
        self["base"] = base

    def with_params(self, **params: Mapping[str, str | int]):
        self["params"].update(params)
        return self

    def with_parts(self, *parts: str):
        self["parts"] = list(dict.fromkeys([*self["parts"], *parts]))
        return self
