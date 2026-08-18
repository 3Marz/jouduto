
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

        self.displayed_items = list(items)
        self.selected_item_ids: set[int] = set()
        self.focused_item_id: int | None = self.displayed_items[0]["id"] if self.displayed_items else None

        self.table: ft.DataTable = ft.DataTable(
            expand=True,
            bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
            border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
            border_radius=10,
            vertical_lines=ft.border.BorderSide(1, ft.Colors.OUTLINE_VARIANT),
            horizontal_lines=ft.border.BorderSide(1, ft.Colors.OUTLINE_VARIANT),
            sort_column_index=0,
            sort_ascending=True,
            heading_row_color=ft.Colors.SURFACE_CONTAINER_HIGHEST,
            heading_row_height=100,
            data_row_color={
                ft.ControlState.HOVERED: ft.Colors.with_opacity(0.08, ft.Colors.PRIMARY),
                ft.ControlState.SELECTED: ft.Colors.with_opacity(0.14, ft.Colors.PRIMARY),
            },
            show_checkbox_column=True,
            divider_thickness=1,
            column_spacing=200,
            columns=[
                ft.DataColumn(label=ft.Text("Code")),
                ft.DataColumn(label=ft.Text("Name")),
                ft.DataColumn(label=ft.Text("Unit Price"), numeric=True),
            ],
            rows=self.build_rows()
        )

        self.imageView = ft.Container(expand=True, content=ft.Text("images"))

        self.content = ft.Row(
            controls=[
                ft.SafeArea(
                    expand=True,
                    content=self.table
                ),
                ft.VerticalDivider(),
                self.imageView
            ]
        )

    def handle_select_item(self, e: ft.Event[ft.DataRow]):
        row = e.control
        item_id = row.data
        is_selected = e.data
        self.focused_item_id = item_id

        if is_selected:
            self.selected_item_ids.add(item_id)
        else:
            self.selected_item_ids.discard(item_id)

        self.refresh_table_rows()

    def refresh_table_rows(self):
        self.table.rows = self.build_rows()
        self.table.update()

    def handle_keyboard(self, e: ft.KeyboardEvent) -> None:

        key = e.key.lower()
        if key not in {"arrow up", "arrow down"}:
            return

        focused_index = next(
            (
                index
                for index, item in enumerate(self.displayed_items)
                if item["id"] == self.focused_item_id
            ),
            0,
        )
        direction = -1 if key == "arrow up" else 1
        next_index = max(0, min(len(self.displayed_items) - 1, focused_index + direction))
        self.focused_item_id = self.displayed_items[next_index]["id"]
        self.refresh_table_rows()

    def build_rows(self):
        return [ 
            ft.DataRow(
                selected=item["id"] in self.selected_item_ids,
                data=item["id"],
                on_select_change=self.handle_select_item,
                cells=[
                    ft.DataCell(ft.Text(item["code"])),
                    ft.DataCell(ft.Text(item["name"])),
                    ft.DataCell(ft.Text(item["unit_price"])),
            ]) 
            for item in self.displayed_items
        ]


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

