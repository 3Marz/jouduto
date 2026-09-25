from database import DatabaseManager
import database
import constants
import appstate
import flet as ft

from pages.home import HomePage
from pages.items import ItemsPage
from pages.item_details import ItemDetailsPage
from pages.distributors import DistributorsPage
from pages.purchase_orders import POPage
from pages.order_report import OrderReportPage

from components.tabs import AppShell


class PageRoute:
    def __init__(self, route: str, title: str, page_type: type):
        self.route = route
        self.title = title
        self.page_type = page_type


def initialize_pages() -> list[PageRoute]:
    return [
        PageRoute("/", "Home", HomePage),
        PageRoute("/items", "Items", ItemsPage),
        PageRoute("/item-details", "Item Details", ItemDetailsPage),
        PageRoute("/distributors", "Distributors", DistributorsPage),
        PageRoute("/pos", "Purchase Orders", POPage),
        PageRoute("/order-report", "Order Report", OrderReportPage),
    ]


def initialize_database():
    for year in appstate.get_years():
        with DatabaseManager(appstate.get_db_path(year)) as db:
            db.execute_script(constants.INITIAL_DB_SCHEME)
            database.migrate_po_statuses(db)
    print("Databases initialized for years:", ", ".join(str(y) for y in appstate.get_years()))


def main(page: ft.Page):
    initialize_database()
    routes = initialize_pages()
    pages_by_route = {route.route: route for route in routes}

    def apply_year_theme() -> None:
        # Re-seed the whole color scheme from the year the ACTIVE tab is
        # working in, so the app visibly reflects the focused tab's fiscal year.
        page.theme = ft.Theme(
            color_scheme_seed=appstate.get_year_color()
        )
        page.theme_mode = ft.ThemeMode.SYSTEM
        page.update()

    def handle_year_change(year: int):
        # The active tab's Home fires this; re-point only that tab at the year.
        shell.change_year_for_active_tab(year)

    def make_home() -> HomePage:
        return HomePage(
            on_year_change=handle_year_change,
            on_navigate=page.navigate,
        )

    shell = AppShell(
        page=page,
        pages_by_route=pages_by_route,
        make_home=make_home,
        on_active_tab_changed=lambda tab: apply_year_theme(),
    )

    apply_year_theme()
    page.title = "Jouduto"

    page.views = [shell.root_view]
    page.on_route_change = lambda e: shell.navigate(page.route)
    page.on_view_pop = lambda e: shell.back()
    page.update()


if __name__ == "__main__":
    ft.run(main)