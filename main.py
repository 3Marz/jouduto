
from typing import cast

from database import DatabaseManager
import constants
import flet as ft

from pages.home import HomePage 
from pages.items import ItemsPage
from pages.distributors import DistributorsPage
from pages.purchase_orders import POPage

class TabedPage:
    def __init__(self, title: str, content: ft.Control):
        self.title = title
        self.content = content

pages: list[TabedPage] = []

def initialize_pages():
     return [
        TabedPage(title="Home", content=HomePage()),
        TabedPage(title="Items", content=ItemsPage()),
        TabedPage(title="Distributors", content=DistributorsPage()),
        TabedPage(title="Purchase Orders", content=POPage()),
    ]

def initialize_database():
    with DatabaseManager(constants.DB_PATH) as db:
        db.execute_script(constants.INITIAL_DB_SCHEME)
        print("Database initialized")

def main(page: ft.Page):

    initialize_database()
    pages = initialize_pages()

    def handle_tab_change(e: ft.Event[ft.Tabs]):
        index = int(e.data)
        reload_page = getattr(pages[index].content, "reload", None)
        if reload_page:
            try:
                reload_page()
            except RuntimeError:
                pass

    page.title = "Jouduto"
    page.vertical_alignment = ft.MainAxisAlignment.CENTER

    page.add(
        ft.SafeArea(
            expand=True,
            content=ft.Tabs(
                expand=True,
                length=len(pages),
                selected_index=1,
                on_change=handle_tab_change,
                content=ft.Column(
                    expand=True,
                    controls=[
                        ft.TabBar(
                            tabs=[ft.Tab(page.title) for page in pages],
                        ),
                        ft.TabBarView(
                            expand=True,
                            controls=[page.content for page in pages],
                        )
                    ]
                )
            )
        )
    )

if __name__ == "__main__":
    ft.run(main)

