
from typing import cast

from database import DatabaseManager
import constants
import flet as ft


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

@ft.control
class DistributorsPage(ft.Container):
    def __init__(self):
        super().__init__()
        self.expand = True

        self.viewContainer = ft.Container(expand=True, content=ft.Text("View"))
        self.createContainer = ft.Container(expand=True, content=ft.Text("Create"))

        self.content = ft.Row(
            controls=[
                self.viewContainer,
                ft.VerticalDivider(),
                self.createContainer
            ]
        )

items = [
    {
        "id": 1,
        "code": "item-1",
        "name": "Item 1",
        "unit_price": 100
    },
    {
        "id": 2,
        "code": "item-2",
        "name": "Item 2",
        "unit_price": 200
    },
    {
        "id": 3,
        "code": "item-3",
        "name": "Item 3",
        "unit_price": 2100
    },
    {
        "id": 4,
        "code": "item-4",
        "name": "Item 4",
        "unit_price": 300
    }
]

@ft.control
class ItemsImagesViewPage(ft.Container):
    def __init__(self):
        super().__init__()
        self.expand = True

        self.itemsView = ft.SafeArea(
            expand=True,
            content=ft.DataTable(
                expand=True,
                columns=[
                    ft.DataColumn(label=ft.Text("Code")),
                    ft.DataColumn(label=ft.Text("Name")),
                    ft.DataColumn(label=ft.Text("Unit Price"), numeric=True),
                ],
                rows=[
                    ft.DataRow(cells=[
                        ft.DataCell(ft.TextField(read_only=True, value=item["code"], margin=3, width=200)),
                        ft.DataCell(ft.Text(item["name"])),
                        ft.DataCell(ft.Text(item["unit_price"])),
                    ]) for item in items
                ]
            )
        )
        self.imageView = ft.Container(expand=True, content=ft.Text("images"))

        self.content = ft.Row(
            controls=[
                self.itemsView,
                ft.VerticalDivider(),
                self.imageView
            ]
        )


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

