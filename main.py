from database import DatabaseManager
import constants
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
    with DatabaseManager(constants.DB_PATH) as db:
        db.execute_script(constants.INITIAL_DB_SCHEME)
        print("Database initialized")


def main(page: ft.Page):
    initialize_database()
    routes = initialize_pages()
    pages_by_route = {route.route: route for route in routes}

    page.theme = ft.Theme(
        color_scheme_seed=ft.Colors.PURPLE
    )
    page.theme_mode = ft.ThemeMode.SYSTEM
    page.title = "Jouduto"

    def make_app_bar(title: str) -> ft.AppBar:
        return ft.AppBar(
            title=ft.Text(title),
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
        )

    def make_nav_handler(route: str):
        def handler(e):
            page.navigate(route)
        return handler

    # Every route change rebuilds the views from scratch, so each page gets a
    # fresh instance (its state resets every time you enter it).
    def route_change(e: ft.RouteChangeEvent = None):
        page.views.clear()

        # Landing view with a button for every section.
        page.views.append(
            ft.View(
                route="/",
                controls=[
                    make_app_bar("Jouduto"),
                    ft.SafeArea(
                        expand=True,
                        content=ft.Column(
                            expand=True,
                            controls=[
                                HomePage(),
                                ft.Divider(),
                                ft.Text(
                                    "Navigate",
                                    theme_style=ft.TextThemeStyle.TITLE_MEDIUM,
                                ),
                                ft.Row(
                                    wrap=True,
                                    spacing=10,
                                    controls=[
                                        ft.Button(
                                            content=route_info.title,
                                            icon=ft.Icons.ARROW_FORWARD,
                                            on_click=make_nav_handler(route_info.route),
                                        )
                                        for route_info in routes
                                        if route_info.route != "/"
                                    ],
                                ),
                            ],
                        ),
                    ),
                ],
            )
        )

        current = pages_by_route.get(page.route.split("?", 1)[0])
        if current is not None and current.route != "/":
            content = current.page_type()
            if current.route == "/item-details":
                query = urllib.parse.parse_qs(page.route.split("?", 1)[1]) if "?" in page.route else {}
                item_param = query.get("item")
                if item_param:
                    try:
                        content.open_focused_item(int(item_param[0]))
                    except ValueError:
                        pass
            page.views.append(
                ft.View(
                    route=page.route,
                    controls=[
                        make_app_bar(current.title),
                        ft.SafeArea(expand=True, content=content),
                    ],
                )
            )

        page.update()

    async def view_pop(e: ft.ViewPopEvent):
        if e.view is not None:
            print("View pop:", e.view)
            page.views.remove(e.view)
            top_view = page.views[-1]
            await page.push_route(top_view.route)

    page.on_route_change = route_change
    page.on_view_pop = view_pop

    route_change()


if __name__ == "__main__":
    ft.run(main)
