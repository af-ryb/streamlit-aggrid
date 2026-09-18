"""What lands in a CSV export for both `useValueFormatterForExport`
settings, across all three built-in aggregators — `grid_agg_export.py`'s
probe. This suite covers `getDataAsCsv()` only; see the module-level note
below on why clipboard copy is documented but not asserted here.

The measured mechanism, traced in the installed `ag-grid-community@36.0.0`
package rather than assumed (see the task report for the full trace):
`CsvCreator`'s row-cell writer is
``this.result += this.putInQuotes(rowCellValue.valueFormatted ?? rowCellValue.value)``,
and for a group cell ``rowCellValue.value`` is the raw `IAggFuncResult`
object straight out of `rowNode.aggData` — no unwrapping. `putInQuotes`
then does ``typeof value.toString === "function" ? value.toString() : ...``.
So when `useValueFormatterForExport=False` suppresses `valueFormatted`,
AG-Grid calls the value object's **`toString()`**, never `toNumber()`.

Clipboard copy (Ctrl+C — this is a read-only grid, so there is no paste) is
*not* the same code path measured above, only a related one: this fork
installs no `processCellForClipboard`, and `ag-grid-enterprise@36.0.0`'s
`ClipboardService.buildExportParams` does end by calling
``csvCreator.getDataAsCsv(exportParams, true)``, so clipboard reaches the
same `getValueForDisplay`/`useValueFormatterForExport` value resolution.
But the `exportParams` it passes set `suppressQuotes: true` (so
`putInQuotes` returns the value unmodified rather than calling
`.toString()` explicitly — stringification then happens implicitly via
`+=` string concatenation), a tab `columnSeparator` instead of a comma, and
a `processRowGroupCallback` plain CSV export never installs — a materially
different serialization path than the one traced above, even though the
same raw `IAggFuncResult` is exactly what a group cell's `value` still is.
The resulting cell text is very likely identical either way (`StAggValue`
defines no `valueOf`, so `ToPrimitive` falls through to `toString()`
regardless of which route triggers it), but that is reasoning about the
mechanism, not a measurement — this suite has no clipboard assertion, and
none of the claims in this file's docstring or in `README.md` extend past
`getDataAsCsv()`.

`foldSums.ts`'s `makeAggValue` defines ``toString: () => (value == null ? ""
: String(value))`` — so the raw CSV cell is JavaScript's own
`Number.prototype.toString()` of the exact float the aggregator computed:
full precision, not the four-decimal `toFixed(4)` string the retired
JavaScript aggregator's own value object used to produce. A leaf cell is a
plain number straight off the DataFrame (never an `IAggFuncResult`), so it is
never subject to `useValueFormatterForExport` degrading its *shape* — only a
`valueFormatter`, if one is configured, changes its text, exactly as for a
group cell.

`expected_csv` below reconstructs both grids' entire CSV text from
`ratio_fixture`'s evaluators plus `js_number` (a Python mirror of what
`putInQuotes`'s `toString()` call actually renders for a JS float) rather
than a hand-typed table — consistent with this plan's rule that anything
derived from the fixture goes through its evaluators. The `\\r\\n` line
separator, the `"stRatio(CPI)"`-style aggFunc header prefix, the
``" -> A"``/``" -> B"`` group-row marker and the trailing space in
``"Total "`` are AG-Grid's own CSV formatting, confirmed by running the
probe and reading the rendered page (`grid_agg_export.py`'s module
docstring), not assumed.
"""

from pathlib import Path

import pytest
from playwright.sync_api import Page

from e2e_utils import StreamlitRunner
from grid_dom import click_header
from ratio_fixture import (
    GROWTH_SPECS_BY_ID,
    RATIO_SPECS_BY_ID,
    RatioOfRatiosSpec,
    WEIGHTED_SPECS_BY_ID,
    as_text,
    evaluate,
    evaluate_ratio_of_ratios,
    evaluate_weighted_avg,
    rows_where,
)

ROOT_DIRECTORY = Path(__file__).parent.parent.absolute()
EXPORT_FILE = ROOT_DIRECTORY / "test" / "grid_agg_export.py"

FORMATTED_GRID = 0  # useValueFormatterForExport=True, + a valueFormatter
RAW_GRID = 1  # useValueFormatterForExport=False, no valueFormatter

CPI_SPEC = RATIO_SPECS_BY_ID["cpi"]
ARPP_BLANK_SPEC = RATIO_SPECS_BY_ID["arpp_blank"]
GROWTH_SPEC = GROWTH_SPECS_BY_ID["growth"]
WAVG_SPEC = WEIGHTED_SPECS_BY_ID["wavg"]
WAVG_BLANK_SPEC = WEIGHTED_SPECS_BY_ID["wavg_blank"]

# Mirrors `grid_agg_export.GROWTH_BLANK_SPEC` exactly — same reason
# `test_grid_agg_builtin.py` redeclares `MIXED_DEN_SPEC`/`GROWTH_BLANK_SPEC`
# locally rather than importing an app module: apps in this repo run via
# `streamlit run`, never as an imported module (importing one would execute
# its top-level `AgGrid()` calls outside a Streamlit run context).
GROWTH_BLANK_SPEC = RatioOfRatiosSpec(
    col_id="growth_blank",
    header="Growth (blank)",
    from_leg={"num": ("ads_d0",), "den": ("inst_d0",)},
    to_leg={"num": ("revenue",), "den": ("payers",)},
)

#: `(field col_id, header, aggFunc name, evaluator)` for the six columns
#: `grid_agg_export.py` declares, grid order. The evaluator takes the rows
#: folded into one node (a campaign's rows, or a single leaf row) and returns
#: the same `Optional[float]` the aggregator itself computes.
COLUMNS = (
    ("cpi", "CPI", "stRatio", lambda rows: evaluate(CPI_SPEC, rows)),
    ("arpp_blank", "ARPP (blank)", "stRatio", lambda rows: evaluate(ARPP_BLANK_SPEC, rows)),
    ("growth", "Growth", "stRatioOfRatios", lambda rows: evaluate_ratio_of_ratios(rows, GROWTH_SPEC)),
    (
        "growth_blank",
        "Growth (blank)",
        "stRatioOfRatios",
        lambda rows: evaluate_ratio_of_ratios(rows, GROWTH_BLANK_SPEC),
    ),
    ("wavg", "Weighted avg", "stWeightedAvg", lambda rows: evaluate_weighted_avg(rows, WAVG_SPEC)),
    (
        "wavg_blank",
        "Weighted avg (blank)",
        "stWeightedAvg",
        lambda rows: evaluate_weighted_avg(rows, WAVG_BLANK_SPEC),
    ),
)


def js_number(value: float | None) -> str:
    """Python mirror of `Number.prototype.toString()` — what `putInQuotes`
    actually renders for a raw (unformatted) cell, per the module docstring's
    trace. JS drops the trailing `.0` an integral float carries in Python's
    `repr`/`str` (`String(10.0)` is `"10"`, not `"10.0"`); every other float
    in this fixture round-trips identically between Python's `repr` (a
    shortest-round-trip algorithm since Python 3.1) and JS's own default
    stringification (also shortest-round-trip) — confirmed cell-by-cell
    against the actual measured CSV while building this test, not assumed.
    `None` — `fill_null`'s default — renders as the empty string, matching
    `StAggValue.toString()` in `foldSums.ts`.
    """
    if value is None:
        return ""
    if value == int(value):
        return str(int(value))
    return repr(value)


#: Grid 0 only (`useValueFormatterForExport=True` context) carries a seventh
#: column, `cpi_no_formatter`: `useValueFormatterForExport: True` but no
#: `valueFormatter` configured. Its evaluator is the same as `cpi`'s; only
#: its text function differs, and it is *always* `js_number` regardless of
#: the grid's own `formatted` flag — proving the README's "True with no
#: formatter behaves like False" claim empirically (see
#: `test_true_without_a_value_formatter_behaves_like_false`) rather than only
#: by reading AG-Grid's `formatValue` source.
NO_FORMATTER_COLUMN = ("stRatio", "CPI (true, no formatter)", lambda rows: evaluate(CPI_SPEC, rows))


def csv_row(group_label: str, rows: list[dict], *, formatted: bool, with_no_formatter_column: bool = False) -> str:
    """One quoted, comma-joined CSV row: the group-column label, then each of
    `COLUMNS`' evaluators over `rows` — `ratio_fixture.as_text` (four
    decimals, `""` for `None`) under the formatted setting, `js_number` (full
    JS float precision) under the raw one — plus, on grid 0 only,
    `NO_FORMATTER_COLUMN`'s own value rendered with `js_number` unconditionally.
    """
    cells = [group_label]
    for _, _, _, evaluator in COLUMNS:
        value = evaluator(rows)
        cells.append(as_text(value) if formatted else js_number(value))
    if with_no_formatter_column:
        _, _, evaluator = NO_FORMATTER_COLUMN
        cells.append(js_number(evaluator(rows)))
    return ",".join(f'"{cell}"' for cell in cells)


def expected_csv(*, formatted: bool, with_no_formatter_column: bool = False) -> str:
    """The whole CSV `grid_agg_export.py` should produce for one grid,
    reconstructed from `ratio_fixture`'s evaluators rather than hand-typed:
    a header row (AG-Grid's own `"aggFunc(headerName)"` convention for a
    grouped grid's value columns), each campaign's group row followed by its
    four leaves in fixture order, then the `"Total "` grand-total row
    (AG-Grid's own trailing space, measured — see the module docstring).
    `\\r\\n` is AG-Grid's own CSV line separator.
    """
    header_cells = ['"Group"'] + [f'"{agg}({header_name})"' for _, header_name, agg, _ in COLUMNS]
    if with_no_formatter_column:
        agg, header_name, _ = NO_FORMATTER_COLUMN
        header_cells.append(f'"{agg}({header_name})"')
    header = ",".join(header_cells)
    lines = [header]
    for campaign in ("A", "B"):
        campaign_rows = rows_where(campaign=campaign)
        lines.append(
            csv_row(f" -> {campaign}", campaign_rows, formatted=formatted, with_no_formatter_column=with_no_formatter_column)
        )
        for row in campaign_rows:
            lines.append(csv_row("", [row], formatted=formatted, with_no_formatter_column=with_no_formatter_column))
    lines.append(
        csv_row("Total ", rows_where(), formatted=formatted, with_no_formatter_column=with_no_formatter_column)
    )
    return "\r\n".join(lines)


@pytest.fixture(autouse=True, scope="module")
def streamlit_app():
    with StreamlitRunner(EXPORT_FILE) as runner:
        yield runner


@pytest.fixture(autouse=True, scope="function")
def go_to_app(page: Page, streamlit_app: StreamlitRunner):
    page.goto(streamlit_app.server_url)
    page.get_by_role("img", name="Running...").is_hidden()
    page.wait_for_selector(".ag-root-wrapper", timeout=60000)
    page.wait_for_function(
        "() => document.querySelectorAll('.ag-root-wrapper').length >= 2",
        timeout=60000,
    )
    page.wait_for_selector('[row-index="9"]', timeout=60000)

    # `collect=["getDataAsCsv"]` only fires on an `update_on` event, so this
    # suite drives a real `sortChanged` rather than naming `gridReady` (which
    # does work now, per `grid_agg_export.py`'s module docstring): the point
    # here is what a settled, user-sorted grid exports, so click each grid's
    # row-group header once. Ascending reproduces the fixture's own campaign
    # order (A before B), so this does not disturb the row order
    # `expected_csv` above assumes.
    click_header(page, FORMATTED_GRID, "ag-Grid-AutoColumn", "ascending")
    click_header(page, RAW_GRID, "ag-Grid-AutoColumn", "ascending")

    page.wait_for_function(
        """() => {
             const a = document.querySelector('.st-key-export_formatted_csv');
             const b = document.querySelector('.st-key-export_raw_csv');
             return !!a && !!b && a.textContent.trim().length > 0 && b.textContent.trim().length > 0;
           }""",
        timeout=30000,
    )


def csv_text(page: Page, key: str) -> str:
    return page.locator(f".st-key-{key}").inner_text()


def test_formatted_csv_matches_the_fixture_exactly(page: Page):
    """`useValueFormatterForExport=True` + the probe's `valueFormatter`
    (four decimals, empty for `None`): every cell — group, leaf, and
    `fill_null` blank, across all three aggregators — matches
    `ratio_fixture`'s evaluators exactly, pinned as an exact string per the
    task brief, not a shape. Grid 0 also carries `cpi_no_formatter` (the
    seventh, always-`js_number` column — see
    `test_true_without_a_value_formatter_behaves_like_false`)."""
    assert csv_text(page, "export_formatted_csv") == expected_csv(
        formatted=True, with_no_formatter_column=True
    )


def test_raw_csv_matches_the_fixture_exactly(page: Page):
    """`useValueFormatterForExport=False`, no `valueFormatter`: every cell —
    group, leaf, and `fill_null` blank, across all three aggregators —
    matches `ratio_fixture`'s evaluators exactly, formatted the way
    `putInQuotes`'s `toString()` call actually renders a JS float
    (`js_number`), pinned as an exact string."""
    assert csv_text(page, "export_raw_csv") == expected_csv(formatted=False)


def test_group_cell_precision_diverges_between_the_two_settings(page: Page):
    """The headline finding, pinned independently of the full-CSV strings
    above so it reads on its own: a group row's aggregated cell is a
    four-decimal string under `useValueFormatterForExport=True` and a
    full-precision JS float string under `False` — the `toFixed(4)` ->
    full-precision change the task exists to document — and all three
    aggregators behave alike (same divergence, same shape).
    """
    formatted = csv_text(page, "export_formatted_csv").split("\r\n")
    raw = csv_text(page, "export_raw_csv").split("\r\n")
    # Row 1 (0-indexed) is campaign A's group row in both grids.
    campaign_a_formatted = formatted[1].split(",")
    campaign_a_raw = raw[1].split(",")

    # cpi (stRatio): a whole number, so the divergence is "10.0000" vs "10".
    assert campaign_a_formatted[1] == '"10.0000"'
    assert campaign_a_raw[1] == '"10"'

    # growth (stRatioOfRatios): a repeating decimal, so the divergence is
    # stark — four decimals vs seventeen significant digits.
    assert campaign_a_formatted[3] == '"1.1818"'
    assert campaign_a_raw[3] == '"1.1818181818181819"'

    # wavg (stWeightedAvg): both terminate, so the divergence is only the
    # trailing zeros a fixed-decimals formatter adds.
    assert campaign_a_formatted[5] == '"2.0800"'
    assert campaign_a_raw[5] == '"2.08"'


def test_fill_null_cell_is_empty_in_both_settings(page: Page):
    """A `fill_null` blank (campaign B's zero-`payers` denominator collapse,
    the same fact `arpp_blank`/`growth_blank`/`wavg_blank` share) renders as
    an empty CSV field either way — `useValueFormatterForExport` only affects
    a *present* value's text, never whether a `None` renders blank. All three
    aggregators agree.
    """
    formatted = csv_text(page, "export_formatted_csv").split("\r\n")
    raw = csv_text(page, "export_raw_csv").split("\r\n")
    # Row 6 (0-indexed) is campaign B's group row in both grids.
    campaign_b_formatted = formatted[6].split(",")
    campaign_b_raw = raw[6].split(",")

    for col_index in (2, 4, 6):  # arpp_blank, growth_blank, wavg_blank
        assert campaign_b_formatted[col_index] == '""'
        assert campaign_b_raw[col_index] == '""'


def test_true_without_a_value_formatter_behaves_like_false(page: Page):
    """The README's second table row, confirmed empirically rather than only
    by reading AG-Grid's `formatValue` source: `cpi_no_formatter`
    (`useValueFormatterForExport=True`, no `valueFormatter`, grid 0 only)
    renders every cell identically to the `false` grid's own `cpi` column —
    with nothing configured to format, `valueFormatted` stays `null` and
    AG-Grid falls back to the raw value's own `toString()`, same as `false`.
    """
    formatted_rows = csv_text(page, "export_formatted_csv").split("\r\n")
    raw_rows = csv_text(page, "export_raw_csv").split("\r\n")
    assert len(formatted_rows) == len(raw_rows) == 12  # header + 2 groups + 8 leaves + total

    # `cpi_no_formatter` is the last (8th) column on grid 0; `cpi` is the 2nd
    # column on both grids (index 1 after the group column at index 0).
    for formatted_line, raw_line in zip(formatted_rows[1:], raw_rows[1:]):
        no_formatter_cell = formatted_line.split(",")[-1]
        raw_cpi_cell = raw_line.split(",")[1]
        assert no_formatter_cell == raw_cpi_cell


def test_leaf_cell_holds_a_plain_number_not_an_object(page: Page):
    """A leaf row's cell is a plain number straight off the DataFrame, never
    an `IAggFuncResult` — but `useValueFormatterForExport` still applies to
    it exactly the same way it applies to a group cell, because the setting
    (and any `valueFormatter`) is a column property, not something keyed off
    the value's shape. Row 2 (0-indexed) is campaign A's first leaf.
    """
    formatted = csv_text(page, "export_formatted_csv").split("\r\n")
    raw = csv_text(page, "export_raw_csv").split("\r\n")
    leaf_formatted = formatted[2].split(",")
    leaf_raw = raw[2].split(",")

    assert leaf_formatted[0] == '""'  # the group column is blank on a leaf
    assert leaf_formatted[1] == '"400.0000"'  # cpi, formatted
    assert leaf_raw[1] == '"400"'  # cpi, raw — same divergence as a group cell
