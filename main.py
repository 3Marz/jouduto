
from database import DatabaseManager
import constants
import flet as ft


class TabedPage:
    def __init__(self, title: str, content: ft.Control):
        self.title = title
        self.content = content

pages: list[TabedPage] = [
    TabedPage(title="Home", content=ft.Text("Home")),
    TabedPage(title="Items", content=ft.Text("Items")),
    TabedPage(title="Extras", content=ft.Text("Extras"))
]

def initialize_database():
    with DatabaseManager(constants.DB_PATH) as db:
        db.execute_script(constants.INITIAL_DB_SCHEME)
        print("Database initialized")

def main(page: ft.Page):
    page.title = "Jouduto"
    page.vertical_alignment = ft.MainAxisAlignment.CENTER

    page.add(
        ft.SafeArea(
            expand=True,
            content=ft.Tabs(
                expand=True,
                length=3,
                selected_index=1,
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

