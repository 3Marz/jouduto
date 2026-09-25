#!/usr/bin/env python3
"""Headless smoke test for the import status logic (pages/items.py).

Feeds synthetic Excel frames through `ItemsPage.handle_import` for all three
import types, then asserts the modal status text reflects the real outcome:
added/updated/skipped/errors, and that the DB + inventory actually changed.

Examples:
    python scripts/smoke_import.py        # run all import-status assertions
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import appstate
import constants
import database
from database import DatabaseManager
import pages.items as items_module

from flet.controls.base_control import BaseControl


# ---------------------------------------------------------------------------
# FakePage: every flet control created during the smoke shares this instance.
# ---------------------------------------------------------------------------
class FakePage:
    def __init__(self):
        self.route = "/"
        self.views = []
        self.theme = None
        self.theme_mode = None
        self.navigations: list[str] = []

    def navigate(self, route: str):
        self.route = route
        self.navigations.append(route)

    def update(self, *args):
        pass

    def show_dialog(self, dialog):
        pass

    def pop_dialog(self):
        pass


SHARED_PAGE = FakePage()
BaseControl.page = property(lambda self: SHARED_PAGE)


# ---------------------------------------------------------------------------
# Temp DB setup.
# ---------------------------------------------------------------------------
TMPDIR = Path(tempfile.mkdtemp(prefix="jouduto_smoke_import_"))
appstate.DATA_DIR = str(TMPDIR)
appstate.set_active_year(2026)
with DatabaseManager(appstate.get_db_path()) as db:
    db.execute_script(constants.INITIAL_DB_SCHEME)
    database.migrate_po_statuses(db)


def fail(msg: str):
    print(f"FAIL: {msg}")
    sys.exit(1)


def check(name: str, cond: bool, detail=""):
    if not cond:
        fail(f"{name} {detail}")


def page_for_next_import(frame, import_type: str):
    """Return an ItemsPage primed to import the given synthetic frame."""
    items_module.pd.read_excel = lambda path: frame
    page = items_module.ItemsPage()
    page.files = [type("F", (), {"path": "/fake.xlsx", "name": "fake.xlsx"})()]
    page.selected_import_type = import_type
    return page


def main():
    pd = __import__("pandas")

    # --- items import: 2 rows with distributors, 1 duplicate code -----------
    frame = pd.DataFrame(
        {
            "code": ["I-1", "I-2", "I-1"],
            "name": ["One", "Two", "Dup"],
            "dist": ["Dist A", "", "Dist B"],
        }
    )  # itertuples: row[1]=code, row[2]=name, row[3]=dist
    page = page_for_next_import(frame, "items")
    page.handle_import(None)

    check("items status", page.import_status.value == "Items imported: 2, errors: 1",
          page.import_status.value)
    check("items status color", page.import_status.color == items_module.ft.Colors.ERROR,
          str(page.import_status.color))

    with DatabaseManager() as db:
        items = db.fetch_all("SELECT item_id, item_code FROM items ORDER BY item_code")
        codes = [r["item_code"] for r in items]
        check("items inserted", codes == ["I-1", "I-2"], str(codes))
        dist_a = db.fetch_one("SELECT distributor_id FROM distributors WHERE distributor_name = ?", ("Dist A",))
        check("distributor created", dist_a is not None)
        i1 = db.fetch_one("SELECT item_id FROM items WHERE item_code = 'I-1'")
        linked = db.fetch_all(
            "SELECT * FROM item_distributors WHERE item_id = ?", (i1["item_id"],)
        )
        check("distributor linked to I-1", len(linked) == 1 and linked[0]["is_primary"] == 1)

    # --- available stock: UPDATE both, skip a missing code ------------------
    frame = pd.DataFrame(
        {
            "code": ["I-1", "I-2", "MISSING"],
            "c2": [0] * 3, "c3": [0] * 3, "c4": [0] * 3,
            "c5": [0] * 3, "c6": [0] * 3,
            "available": [111, 222, 333],
        },
        index=[1, 2, 3],
    )  # row[1]=code, row[7]=available; row[0]!=0 so all rows processed
    page = page_for_next_import(frame, "avil_stock")
    page.handle_import(None)

    check("avail status", page.import_status.value == "Available stock updated: 2, skipped: 1",
          page.import_status.value)
    check("avail status color", page.import_status.color == items_module.ft.Colors.GREEN,
          str(page.import_status.color))

    with DatabaseManager() as db:
        rows = {r["item_code"]: r for r in db.fetch_all(
            "SELECT i.item_code, inv.quantity_available FROM inventory inv "
            "JOIN items i ON i.item_id = inv.item_id")}
        check("avail I-1", rows.get("I-1", {}).get("quantity_available") == 111, str(rows))
        check("avail I-2", rows.get("I-2", {}).get("quantity_available") == 222, str(rows))
        check("avail missing skipped", "MISSING" not in rows)

    # --- available stock again: exercises the UPDATE path -------------------
    frame = pd.DataFrame(
        {
            "code": ["I-1"],
            "c2": [0], "c3": [0], "c4": [0],
            "c5": [0], "c6": [0],
            "available": [999],
        },
        index=[1],
    )
    page = page_for_next_import(frame, "avil_stock")
    page.handle_import(None)
    with DatabaseManager() as db:
        val = db.fetch_one(
            "SELECT inv.quantity_available FROM inventory inv JOIN items i ON i.item_id = inv.item_id "
            "WHERE i.item_code = 'I-1'")
        check("avail UPDATE path", val["quantity_available"] == 999, str(val))

    # --- sold stock: UPDATE I-2's sold, skip a missing code -----------------
    frame = pd.DataFrame(
        {
            "code": ["I-2", "WHATEVER", "GONE"],
            **{f"c{n}": [0] * 3 for n in range(2, 11)},
            "sold": [77, 0, 0],
        },
        index=[1, 2, 3],
    )  # row[1]=code, row[11]=sold
    page = page_for_next_import(frame, "sold_stock")
    page.handle_import(None)

    check("sold status", page.import_status.value == "Sold stock updated: 1, skipped: 2",
          page.import_status.value)
    check("sold status color", page.import_status.color == items_module.ft.Colors.GREEN,
          str(page.import_status.color))

    with DatabaseManager() as db:
        val = db.fetch_one(
            "SELECT inv.quantity_sold FROM inventory inv JOIN items i ON i.item_id = inv.item_id "
            "WHERE i.item_code = 'I-2'")
        check("sold I-2", val["quantity_sold"] == 77, str(val))

    # --- page state refreshed after import ----------------------------------
    check("page reloaded", page.total_items == 2, str(page.total_items))

    print("All import-status smoke checks passed.")
    shutil.rmtree(TMPDIR, ignore_errors=True)


if __name__ == "__main__":
    main()