from database import DatabaseManager
import database
import constants
import appstate
import urllib.parse
import flet as ft

from pages.home import HomePage
from pages.items import ItemsPage
from pages.item_details import ItemDetailsPage
from pages.distributors import DistributorsPage
from pages.purchase_orders import POPage


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
        # Re-seed the whole color scheme from the active year's color so the
        # app visibly reflects which fiscal year is selected.
        page.theme = ft.Theme(
            color_scheme_seed=appstate.get_year_color()
        )
        page.theme_mode = ft.ThemeMode.SYSTEM
        page.update()

    apply_year_theme()
    page.title = "Jouduto"

    def make_app_bar(title: str) -> ft.AppBar:
        year = appstate.get_active_year()
        return ft.AppBar(
            title=ft.Text(
                title,
                italic=True,
                weight=ft.FontWeight.W_900,
                theme_style=ft.TextThemeStyle.TITLE_LARGE
            ),
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
            actions=[
                ft.Container(
                    content=ft.Text(
                        str(year),
                        weight=ft.FontWeight.BOLD,
                        size=20
                    ),
                    padding=ft.Padding.symmetric(horizontal=20),
                    tooltip=f"Active fiscal year: {year}",
                )
            ],
        )

    def make_nav_handler(route: str):
        def handler(e):
            page.navigate(route)
        return handler

    def handle_year_change(year: int):
        nonlocal home_view
        appstate.set_active_year(year)
        # Re-seed the color scheme from the newly active year's color so the
        # whole app visibly recolors when you switch years.
        apply_year_theme()
        # Rebuild home immediately so dashboard stats reflect the new year's DB.
        home_view = make_home_view()
        page.views.clear()
        page.views.append(home_view)
        page.update()

    # Stack shapes: [Home] -> [Home, Section] -> [Home, Section, ItemDetails].
    # Views are reconciled (never wiped blindly) so item-details opens ON TOP
    # of the Items page, and backing out returns to the same Items instance
    # with its state (scroll, selection, search, sort) intact.
    home_view = None  # built once, reused as the stable root of the stack

    def make_view(route: str, title: str, content: ft.Control) -> ft.View:
        return ft.View(
            route=route,
            controls=[
                make_app_bar(title),
                ft.SafeArea(expand=True, content=content),
            ],
        )

    def make_home_view() -> ft.View:
        return ft.View(
            route="/",
            controls=[
                make_app_bar("Jouduto"),
                ft.SafeArea(
                    expand=True,
                    content=HomePage(
                        on_year_change=handle_year_change,
                        on_navigate=page.navigate,
                    ),
                ),
            ],
        )

    def base_route(route: str) -> str:
        return route.split("?", 1)[0]

    def route_change(e: ft.RouteChangeEvent = None):
        nonlocal home_view
        if home_view is None:
            home_view = make_home_view()

        route = page.route
        base = base_route(route)
        old = list(page.views)

        if base == "/":
            page.views.clear()
            page.views.append(home_view)
            page.update()
            return

        current = pages_by_route.get(base)
        if current is None:
            return

        if base == "/item-details":
            # Keep the layers beneath (e.g. Items) so backing out restores them.
            prefix = [v for v in old if base_route(v.route) != "/item-details"]
            if not prefix or all(base_route(v.route) == "/" for v in prefix):
                prefix = [home_view]

            content = current.page_type()
            query = urllib.parse.parse_qs(page.route.split("?", 1)[1]) if "?" in page.route else {}
            item_param = query.get("item")
            if item_param:
                try:
                    content.open_focused_item(int(item_param[0]))
                except ValueError:
                    pass

            page.views.clear()
            page.views.extend(prefix)
            page.views.append(make_view(route, current.title, content))
            page.update()
            return

        # Regular section page: [Home, Section]. Reuse a section view already
        # in the stack so its state survives (items page during a round-trip).
        section_view = next(
            (v for v in old if base_route(v.route) == base),
            None,
        )
        if section_view is None:
            section_view = make_view(base, current.title, current.page_type())

        page.views.clear()
        page.views.append(home_view)
        page.views.append(section_view)
        page.update()

    def view_pop(e: ft.ViewPopEvent):
        if len(page.views) > 1:
            page.views.pop()
            top_view = page.views[-1]
            page.navigate(top_view.route)

    page.on_route_change = route_change
    page.on_view_pop = view_pop

    route_change()


if __name__ == "__main__":
    ft.run(main)
