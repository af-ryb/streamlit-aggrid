"""Reading rendered AG-Grid cells from a Playwright page.

Row addressing goes through ``row-index``, never DOM order: AG-Grid positions
rows absolutely, so the order elements appear in the document does not track
the order they appear on screen. A probe written against DOM order produced a
false "sorting is broken" result once already.

Shared by every ratio e2e suite so the two never drift apart on what "the
grand-total row" or "row 4" means.
"""

import pytest
from playwright.sync_api import Page

_READ_ROWS = """
(gridIndex) => {
  const grid = document.querySelectorAll('.ag-root-wrapper')[gridIndex];
  const rows = {};
  for (const row of grid.querySelectorAll('.ag-row')) {
    const section = row.closest('.ag-floating-bottom') ? 'bottom'
                  : row.closest('.ag-floating-top') ? 'top' : 'body';
    const key = section + ':' + row.getAttribute('row-index');
    // A row is split across pinned/centre containers; merge the fragments.
    const cells = rows[key] || (rows[key] = {});
    for (const cell of row.querySelectorAll('.ag-cell')) {
      cells[cell.getAttribute('col-id')] = cell.textContent.trim();
    }
  }
  return rows;
}
"""


def read_rows(page: Page, grid_index: int) -> dict[str, dict[str, str]]:
    """Every rendered cell of one grid, keyed ``"<section>:<row-index>"`` then
    col-id. The ratio apps suppress virtualisation, so this returns the whole
    grid rather than the visible window."""
    return page.evaluate(_READ_ROWS, grid_index)


_READ_CELL_BOXES = """
(gridIndex) => {
  const grid = document.querySelectorAll('.ag-root-wrapper')[gridIndex];
  // v36 renamed the row containers (`.ag-sticky-top` ->
  // `.ag-grid-sticky-top-rows-container`); both spellings are matched so this
  // probe keeps working either side of an AG-Grid bump.
  const sectionOf = (row) =>
      row.closest('.ag-grid-sticky-top-rows-container, .ag-sticky-top') ? 'sticky-top'
    : row.closest('.ag-grid-sticky-bottom-rows-container, .ag-sticky-bottom') ? 'sticky-bottom'
    : row.closest('.ag-floating-top') ? 'top'
    : row.closest('.ag-floating-bottom') ? 'bottom'
    : 'body';
  const levelOf = (row) => {
    const match = /(?:^| )ag-row-level-(\\d+)(?: |$)/.exec(row.className);
    return match ? Number(match[1]) : null;
  };
  const out = [];
  for (const row of grid.querySelectorAll('.ag-row')) {
    const section = sectionOf(row);
    const rowIndex = row.getAttribute('row-index');
    const rowId = row.getAttribute('row-id');
    const rowLevel = levelOf(row);
    for (const cell of row.querySelectorAll('.ag-cell')) {
      const box = cell.getBoundingClientRect();
      out.push({
        section: section,
        rowIndex: rowIndex,
        rowId: rowId,
        rowLevel: rowLevel,
        colId: cell.getAttribute('col-id'),
        text: cell.textContent.trim(),
        left: box.left,
        right: box.right,
        top: box.top,
        bottom: box.bottom,
        cellBackground: getComputedStyle(cell).backgroundColor,
        rowBackground: getComputedStyle(row).backgroundColor,
      });
    }
  }
  return out;
}
"""


def read_cell_boxes(page: Page, grid_index: int) -> list[dict]:
    """Every rendered cell of one grid with its on-screen rectangle.

    Where `read_rows` answers "what does this cell say", this answers "where is
    it drawn" — the only way to see a cell painted on top of another one, which
    `read_rows` hides by keying on col-id and keeping the last writer.
    """
    return page.evaluate(_READ_CELL_BOXES, grid_index)


def stacked_cells(boxes: list[dict], tolerance: float = 1.0) -> list[tuple[dict, dict]]:
    """Pairs of cells that occupy the same screen space within one rendered row.

    Rendered cells of a row must tile, never stack: AG-Grid positions them
    absolutely from the column model, so two cells sharing a rectangle means
    the column model and the painted DOM disagree. Compared per
    ``(section, row-index)`` because a sticky or pinned row legitimately covers
    a body row — that is the feature, not the defect.

    ``tolerance`` absorbs sub-pixel layout rounding; only a real span of shared
    pixels counts.
    """
    grouped: dict[tuple[str, str], list[dict]] = {}
    for box in boxes:
        grouped.setdefault((box["section"], box["rowIndex"]), []).append(box)

    stacked = []
    for row_boxes in grouped.values():
        for i, a in enumerate(row_boxes):
            for b in row_boxes[i + 1 :]:
                horizontal = min(a["right"], b["right"]) - max(a["left"], b["left"])
                vertical = min(a["bottom"], b["bottom"]) - max(a["top"], b["top"])
                if horizontal > tolerance and vertical > tolerance:
                    stacked.append((a, b))
    return stacked


def grand_total_row(
    rows: dict[str, dict[str, str]], group_col_id: str = "ag-Grid-AutoColumn-campaign"
) -> dict[str, str]:
    """The ``grandTotalRow: "bottom"`` row.

    AG-Grid renders it either in the pinned-bottom container or as the last
    body row depending on whether the grid is scrolled, so locate it by its
    group label rather than by a fixed key.
    """
    for cells in rows.values():
        if cells.get(group_col_id) == "Total":
            return cells
    raise AssertionError(f"no grand-total row among {sorted(rows)}")


def assert_number(text: str, reference: float | None, where: str) -> None:
    """Compare an unformatted cell's raw text — a value object's own
    `toString()`, no valueFormatter — against a reference number. `None`
    means an empty cell.

    Shared for the same reason `read_rows`/`grand_total_row` are: every
    unformatted-grid suite in this repo reads cells this way, and a
    second copy of the tolerance/formatting logic is exactly the kind of
    thing that drifts silently once only one of the two is still editable.
    """
    if reference is None:
        assert text == "", f"{where}: expected an empty cell, got {text!r}"
    else:
        assert text != "", f"{where}: expected {reference}, got an empty cell"
        assert float(text) == pytest.approx(reference), where


def click_header(page: Page, grid_index: int, col_id: str, expect_sort: str) -> None:
    """Click a header and wait for AG-Grid to report the new direction.

    Waiting on `aria-sort` rather than on a timeout matters here: several of
    these assertions expect an order that is also the *unsorted* order, so a
    click that silently failed to register would let the test pass without
    sorting anything.
    """
    grid = page.locator(".ag-root-wrapper").nth(grid_index)
    header = grid.locator(f'.ag-header-cell[col-id="{col_id}"]')
    header.click()
    page.wait_for_function(
        """([gridIndex, colId, direction]) => {
             const grid = document.querySelectorAll('.ag-root-wrapper')[gridIndex];
             const cell = grid.querySelector(`.ag-header-cell[col-id="${colId}"]`);
             return cell && cell.getAttribute('aria-sort') === direction;
           }""",
        arg=[grid_index, col_id, expect_sort],
        timeout=10000,
    )


def campaign_order(page: Page, grid_index: int) -> list[str]:
    """Group labels top to bottom, read by row-index. The grand-total row is
    dropped — it stays put regardless of sort.

    Matched by first character rather than equality: AG-Grid renders a
    group's row count into its label when `autoGroupColumnDef` does not set
    `cellRendererParams.suppressCount` (`"A(4)"`, `"B(4)"`) and renders the
    plain `"A"`/`"B"` when it does — `label[:1]` reads the same either way,
    so one function serves both a suite that suppresses the count and one
    that doesn't.
    """
    rows = read_rows(page, grid_index)
    ordered = sorted(
        ((key, cells) for key, cells in rows.items() if key.startswith("body:")),
        key=lambda item: int(item[0].split(":")[1]),
    )
    labels = [cells.get("ag-Grid-AutoColumn-campaign", "") for _, cells in ordered]
    return [label[:1] for label in labels if label[:1] in ("A", "B")]
