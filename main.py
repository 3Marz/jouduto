
from typing import cast

from database import DatabaseManager
import constants
import flet as ft
from pages.item_images import ItemsImagesViewPage
from pages.distributors import DistributorsPage

class TabedPage:
    def __init__(self, title: str, content: ft.Control):
        self.title = title
        self.content = content

@ft.control
class ImportPage(ft.Container):
    def __init__(self):
        super().__init__()
        self.expand = True

        self.files: None | list[ft.FilePickerFile] = None 

        self.render()
    
    def render(self):
        controls = cast(list[ft.Control], [ 
            ft.Text("Import sample data"),
            ft.Button("Pick files", on_click=self.handle_pick_files),
            ft.Text(self.files[0].path) if self.files else ft.Text("No files selected"),
        ] )

        self.content = ft.Column(controls=controls)

    async def handle_pick_files(self, e: ft.Event[ft.Button]):
        files = await ft.FilePicker().pick_files(
            with_data=True,
            allow_multiple=False,
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["xls", "xlsx"],
        )
        self.files = files
        self.render()

pages: list[TabedPage] = [
    TabedPage(title="Home", content=ft.Text("Home")),
    TabedPage(title="Items", content=ft.Text("Items")),
    TabedPage(title="Import", content=ImportPage()),
    TabedPage(title="Distributors", content=DistributorsPage()),
    TabedPage(title="Item Images", content=ItemsImagesViewPage()),
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
                length=len(pages),
                selected_index=2,
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

