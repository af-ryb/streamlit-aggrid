"""Reading rendered AG-Grid cells from a Playwright page.

Row addressing goes through ``row-index``, never DOM order: AG-Grid positions
rows absolutely, so the order elements appear in the document does not track
the order they appear on screen. A probe written against DOM order produced a
false "sorting is broken" result once already.

Shared by every ratio e2e suite so the two never drift apart on what "the
grand-total row" or "row 4" means.
"""

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
