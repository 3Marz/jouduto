#!/usr/bin/env python3
"""Headless smoke test for the browser-style tabs (components/tabs.py).

Runs without a real Flet client: every control shares one FakePage that
absorbs update()/navigate()/dialog calls. The year DBs live in a temp
directory with a freshly initialized schema, and are seeded with DIFFERENT
item counts per year so the smoke can prove each tab reads its own year's DB.

Examples:
    python scripts/smoke_tabs.py        # run all tab-shell assertions
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
from components.tabs import AppShell, Tab
from pages.home import HomePage
from pages.items import ItemsPage
from pages.item_details import ItemDetailsPage
from pages.order_report import OrderReportPage
from pages.purchase_orders import POPage
from pages.distributors import DistributorsPage

from flet.controls.base_control import BaseControl
import flet as ft


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

    def update(self):
        pass

    def show_dialog(self, dialog):
        pass

    def pop_dialog(self):
        pass


SHARED_PAGE = FakePage()
BaseControl.page = property(lambda self: SHARED_PAGE)


# ---------------------------------------------------------------------------
# Temp DBs: distinct item counts per year to prove per-tab DB context.
# ---------------------------------------------------------------------------
TMPDIR = Path(tempfile.mkdtemp(prefix="jouduto_smoke_tabs_"))
appstate.DATA_DIR = str(TMPDIR)
appstate.set_active_year(2026)
for year in appstate.get_years():
    with DatabaseManager(appstate.get_db_path(year)) as db:
        db.execute_script(constants.INITIAL_DB_SCHEME)
        database.migrate_po_statuses(db)

# 2026 -> 2 items, 2025 -> 3 items
for code, name in [("A-1", "Alpha"), ("A-2", "Bravo")]:
    with DatabaseManager(appstate.get_db_path(2026)) as db:
        db.execute_query("INSERT INTO items (item_code, item_name) VALUES (?, ?)", (code, name))
for code, name in [("B-1", "Charlie"), ("B-2", "Delta"), ("B-3", "Echo")]:
    with DatabaseManager(appstate.get_db_path(2025)) as db:
        db.execute_query("INSERT INTO items (item_code, item_name) VALUES (?, ?)", (code, name))


def route_table():
    return {
        "/": ("Home", HomePage),
        "/items": ("Items", ItemsPage),
        "/item-details": ("Item Details", ItemDetailsPage),
        "/distributors": ("Distributors", DistributorsPage),
        "/pos": ("Purchase Orders", POPage),
        "/order-report": ("Order Report", OrderReportPage),
    }


class FakeRoute:
    def __init__(self, title: str, page_type):
        self.title = title
        self.page_type = page_type


def build_shell():
    pages_by_route = {r: FakeRoute(*info) for r, info in route_table().items()}

    shell = None

    def make_home():
        # AppShell has already pointed appstate at the target tab's year.
        return HomePage(
            on_year_change=lambda year: shell.change_year_for_active_tab(year),
            on_navigate=lambda route: shell.navigate(route),
        )

    shell = AppShell(
        page=SHARED_PAGE,
        pages_by_route=pages_by_route,
        make_home=make_home,
    )
    return shell


def fail(msg: str):
    print(f"FAIL: {msg}")
    sys.exit(1)


def check(name: str, cond: bool, detail=""):
    if not cond:
        fail(f"{name} {detail}")


def top(shell, tab_id=None) -> Tab:
    tab = shell._tab(tab_id)
    assert tab is not None
    return tab


def chip_labels(shell):
    return [
        chip.content.controls[0].value
        for chip in shell.strip_chips.controls
    ]


def main():
    shell = build_shell()

    # 1. Starts with exactly one Home tab, active, in the default year.
    check("initial tab count", len(shell.tabs) == 1, str(len(shell.tabs)))
    t1 = shell.tabs[0]
    check("initial active", shell.active_tab_id == t1.id)
    check("initial year", t1.year == 2026, str(t1.year))
    check("initial chip label", chip_labels(shell) == ["Home · 2026"], str(chip_labels(shell)))

    # 2. Navigate active tab to /items -> [Home, Items]; reads 2026 DB.
    shell.navigate("/items")
    check("items stack depth", len(t1.stack) == 2, [r for r, _, _ in t1.stack])
    items1 = t1.stack[-1][2]
    check("items content type", isinstance(items1, ItemsPage))
    check("2026 db count", items1.total_items == 2, str(items1.total_items))
    check("chip label tracks page + year", chip_labels(shell) == ["Items · 2026"], str(chip_labels(shell)))

    # 3. Second tab inherits the active tab's year, own Home + own ItemsPage.
    t2 = shell.add_tab()
    check("two tabs", len(shell.tabs) == 2)
    check("new tab active", shell.active_tab_id == t2.id)
    check("new tab inherits year", t2.year == 2026, str(t2.year))
    check("tabs have distinct homes", t2.home is not t1.home)
    check("t1 still 2026", t1.year == 2026, str(t1.year))

    # 4. Change ONLY tab2's year to 2025 -> tab1 is untouched.
    shell.change_year_for_active_tab(2025)  # tab2 is active
    check("tab2 year 2025", t2.year == 2025, str(t2.year))
    check("tab1 year untouched", t1.year == 2026, str(t1.year))
    check("tab2 chip year", chip_labels(shell) == ["Items · 2026", "Home · 2025"], str(chip_labels(shell)))
    check("tab2 home rebuilt", isinstance(t2.home, HomePage) and len(t2.stack) == 1)
    check("tab1 stack untouched", [b for b, _, _ in t1.stack] == ["/", "/items"])

    # 5. Tab2's pages read the 2025 DB (3 items), tab1's read 2026 (2 items).
    shell.navigate("/items")
    items2 = top(shell, t2.id).stack[-1][2]
    check("per-tab items independent", items2 is not items1)
    check("2025 db count", items2.total_items == 3, str(items2.total_items))

    shell.switch_tab(t1.id)
    check("switch active", shell.active_tab_id == t1.id)
    check("tab1 items preserved", top(shell, t1.id).stack[-1][2] is items1)

    # 6. Header year badge follows the active tab.
    badge = shell.content_area.content.controls[0].controls[-1].content
    check("badge tab1 year", badge.value == "2026", badge.value)
    shell.switch_tab(t2.id)
    badge = shell.content_area.content.controls[0].controls[-1].content
    check("badge tab2 year", badge.value == "2025", badge.value)

    # 7. global appstate year tracks the ACTIVE tab (DB context).
    check("appstate follows tab2", appstate.get_active_year() == 2025, str(appstate.get_active_year()))
    shell.switch_tab(t1.id)
    check("appstate follows tab1", appstate.get_active_year() == 2026, str(appstate.get_active_year()))

    # 8. Details pushed on top of Items; back pops; '/' resets.
    shell.navigate("/item-details?item=1")
    check("item-details depth", len(t1.stack) == 3, [r for r, _, _ in t1.stack])
    check("item-details type", isinstance(t1.stack[-1][2], ItemDetailsPage))
    shell.back()
    check("back to items", len(t1.stack) == 2 and t1.stack[-1][2] is items1)
    shell.back()
    check("back to home", len(t1.stack) == 1 and isinstance(t1.stack[-1][2], HomePage))
    shell.navigate("/")
    check("route '/' resets to home", len(t1.stack) == 1 and t1.stack[-1][2] is t1.home)

    # 9. Closing a non-active tab keeps the active one.
    shell.switch_tab(t2.id)
    shell.close_tab(t1.id)
    check("close non-active", len(shell.tabs) == 1 and shell.active_tab_id == t2.id)

    # 10. Closing the last tab spawns a fresh Home tab inheriting its year.
    old_id = shell.active_tab_id
    shell.close_tab(shell.active_tab_id)
    check("close-last spawns home", len(shell.tabs) == 1)
    fresh = shell.tabs[0]
    check("close-last fresh id", fresh.id != old_id)
    check("close-last inherits year", fresh.year == 2025, str(fresh.year))
    check("close-last to home depth", len(fresh.stack) == 1)

    # 11. All 6 routes boot headless through the shell in one tab.
    for route, (_, page_type) in route_table().items():
        shell.navigate(route)
        active = shell._tab()
        check(f"boot {route}", isinstance(active.stack[-1][2], page_type), [r for r, _, _ in active.stack])

    print("All tab-shell smoke checks passed.")
    shutil.rmtree(TMPDIR, ignore_errors=True)


if __name__ == "__main__":
    main()