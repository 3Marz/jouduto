
import sqlite3

from database import DatabaseManager
from constants import DB_PATH

import flet as ft
import pandas as pd

from datatypes import Inventory, Item, Distributor

ITEMS_PAGE_SIZE = 70
SCROLL_LOAD_THRESHOLD = 400.0

@ft.control
class ItemsPage(ft.Container):
    def __init__(self):
        super().__init__()
        self.expand = True

        # Pagination / sorting state
        self.total_items: int = 0
        self.displayed_items: list[Item] = []
        self.has_more: bool = False
        self.is_loading: bool = False
        self.sort_column_index: int | None = None
        self.sort_ascending: bool = True
        self.load_first_page()

        self.files: None | list[ft.FilePickerFile] = None
        self.selected_import_type: str | None = "items"

        self.selected_item_ids: set[int] = set()
        self.focused_item_id: int | None = self.displayed_items[0].id if self.displayed_items else None

        self.status_text = ft.Text("No items selected")

        self.import_data_button = ft.Button(
            content="Import Data",
            icon=ft.Icons.INVENTORY_2_OUTLINED,
            on_click=lambda e: self.page.show_dialog(self.import_data_modal)
        )
        self.pick_file_button = ft.Button("Pick file", icon=ft.Icons.UPLOAD, on_click=self.handle_pick_files)
        self.import_data_modal = ft.AlertDialog(
            modal=True,
            title=ft.Row(controls=[ft.Icon(ft.Icons.INVENTORY_2_OUTLINED), ft.Text("Import Data")]),
            content=ft.Column(
                height=200,
                width=500,
                controls=[
                    ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        controls=[
                            ft.Text("Select File: "),
                            self.pick_file_button
                        ]
                    ),
                    ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        controls=[
                            ft.Text("Import Type:"),
                            ft.RadioGroup (
                                value=self.selected_import_type,
                                on_change=self.handle_import_type_change,
                                content=ft.Row(
                                    controls=[
                                        ft.Radio(label="Items Data", value="items"),
                                        ft.Radio(label="Avil Stock Data", value="avil_stock"),
                                        ft.Radio(label="Sold Stock Data", value="sold_stock"),
                                    ]
                                )
                            )
                        ]
                    ),
                ]
            ),
            actions = [
                ft.Button("Cancel", on_click=lambda e: self.page.pop_dialog()),
                ft.Button(
                    "Import", 
                    bgcolor=ft.Colors.PRIMARY, color=ft.Colors.INVERSE_PRIMARY,
                    on_click=self.handle_import
                )
            ]
        )

        self.prev_button = ft.Button(
            content="Previous",
            icon=ft.Icons.ARROW_BACK,
            data=-1,
            on_click=self.handle_prev_select,
            tooltip="Select previous item",
        )
        self.next_button = ft.Button(
            content="Next",
            icon=ft.Icons.ARROW_FORWARD,
            data=1,
            on_click=self.handle_next_select,
            tooltip="Select next item",
        )
        self.table: ft.DataTable = ft.DataTable(
            on_select_all=self.handle_select_all,
            heading_row_color=ft.Colors.with_opacity(1, ft.Colors.SURFACE_CONTAINER_HIGH),
            border=ft.Border.all(1, ft.Colors.SURFACE_CONTAINER_HIGHEST),
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
            data_row_color={
                ft.ControlState.HOVERED: ft.Colors.with_opacity(0.08, ft.Colors.PRIMARY),
                ft.ControlState.SELECTED: ft.Colors.with_opacity(0.14, ft.Colors.PRIMARY),
            },
            show_checkbox_column=True,
            divider_thickness=1,
            columns = self.build_columns(), 
            rows = self.build_rows()
        )

        # ScrollableControl so the table itself scrolls and on_scroll reports
        # real pixel offsets (DataTable2 scrolls in Dart and hides that info).
        self.table_container = ft.Column(
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            on_scroll=self.handle_table_scroll,
            controls=[self.table],
        )

        self.loaded_text = ft.Text(
            f"Loaded {len(self.displayed_items)} of {self.total_items} items"
        )
        self.load_more_button = ft.Button(
            content="Load more",
            icon=ft.Icons.ARROW_DOWNWARD,
            on_click=self.load_more,
            visible=self.has_more,
        )

        self.imageView = ft.Container(expand=True, content=ft.Text("images"))

        self.content = ft.Row(
            controls=[
                ft.SafeArea(
                    expand=True,
                    content=ft.Column(
                        expand=True,
                        controls=[
                            ft.Row(
                                controls=[
                                    ft.Row(
                                        expand=True,
                                        controls=[
                                            self.prev_button,
                                            self.next_button,
                                            ft.Button(
                                                content="Un/Select",
                                                icon=ft.Icons.CHECK,
                                                on_click=self.handle_select_item_button,
                                            )
                                        ]
                                    ),
                                    ft.Row(
                                        alignment=ft.MainAxisAlignment.END,
                                        expand=True,
                                        controls=[
                                            ft.Button(
                                                "Delete All",
                                                icon=ft.Icons.DELETE,
                                                on_click=self.delete_all_items
                                            ),
                                            self.import_data_button,
                                        ]
                                    ),
                                ]
                            ),
                            self.status_text,
                            self.table_container,
                            ft.Row(
                                controls=[self.loaded_text, self.load_more_button],
                                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                            ),
                        ]
                    )
                ),
            ]
        )

    def reload(self):
        self.selected_item_ids = set()
        self.load_first_page()
        self.focused_item_id = self.displayed_items[0].id if self.displayed_items else None
        self.refresh_table_rows()
        self.update_pagination_controls()

    def build_columns(self) -> list[ft.DataColumn]:
        return [
            ft.DataColumn(label=ft.Text("Item Code"), on_sort=self.handle_sort),
            ft.DataColumn(label=ft.Text("Name"), on_sort=self.handle_sort),
            ft.DataColumn(label=ft.Text("Main Distributor"), on_sort=self.handle_sort),
            ft.DataColumn(label=ft.Text("Ordered Stock"), on_sort=self.handle_sort),
            ft.DataColumn(label=ft.Text("Available Stock"), on_sort=self.handle_sort),
            ft.DataColumn(label=ft.Text("Sold Stock"), on_sort=self.handle_sort),
            # ft.DataColumn(label=ft.Text("Unit Price"), numeric=True, on_sort=self.handle_sort),
        ]

    def handle_sort(self, e: ft.DataColumnSortEvent):
        self.sort_column_index = e.column_index
        self.sort_ascending = e.ascending
        self.table.sort_column_index = e.column_index
        self.table.sort_ascending = e.ascending
        self.load_first_page()
        self.refresh_table_rows()
        self.update_pagination_controls()

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

    def handle_select_all(self, e: ft.Event[ft.DataTable]):
        if e.data:
            self.selected_item_ids.update(int(item.id) for item in self.displayed_items)
        else:
            self.selected_item_ids.clear()

        self.refresh_table_rows()

    def handle_select_item_button(self, e: ft.Event[ft.Button]):
        is_checked = self.focused_item_id in self.selected_item_ids

        if is_checked:
            self.selected_item_ids.discard(self.focused_item_id)
        else:
            self.selected_item_ids.add(self.focused_item_id) if self.focused_item_id else None

        self.refresh_table_rows()

    def refresh_table_rows(self):
        self.table.rows = self.build_rows() 
        self.table.update()

    def refresh_image_view(self):
        # urls = GoogleImageScraper.urls(query="Cats")
        # print(urls)
        # self.imageView.content = ft.Image(
        # )
        pass

    def handle_next_select(self, e: ft.Event[ft.Button]) -> None:
        if not self.displayed_items:
            return

        focused_index = next(
            (
                index
                for index, item in enumerate(self.displayed_items)
                if item.id == self.focused_item_id
            ),
            0,
        )
        direction = 1
        next_index = max(0, min(len(self.displayed_items) - 1, focused_index + direction))
        self.focused_item_id = self.displayed_items[next_index].id
        self.refresh_image_view()
        self.refresh_table_rows()

    def handle_prev_select(self, e: ft.Event[ft.Button]) -> None:
        if not self.displayed_items:
            return

        focused_index = next(
            (
                index
                for index, item in enumerate(self.displayed_items)
                if item.id == self.focused_item_id
            ),
            0,
        )
        direction = -1
        next_index = max(0, min(len(self.displayed_items) - 1, focused_index + direction))
        self.focused_item_id = self.displayed_items[next_index].id
        self.refresh_image_view()
        self.refresh_table_rows()

    def build_rows(self) -> list[ft.DataRow]:
        return [self.build_row(item) for item in self.displayed_items]

    def build_row(self, item: Item) -> ft.DataRow:
        return ft.DataRow(
            selected=item.id in self.selected_item_ids,
            data=item.id,
            on_select_change=self.handle_select_item,
            color=(
                {
                    ft.ControlState.DEFAULT: ft.Colors.with_opacity(0.20, ft.Colors.PRIMARY),
                    ft.ControlState.SELECTED: ft.Colors.with_opacity(0.30, ft.Colors.PRIMARY),
                } 
                if item.id == self.focused_item_id 
                else {
                    ft.ControlState.SELECTED: ft.Colors.with_opacity(0.14, ft.Colors.PRIMARY),
                } 
            ),
            cells=[
                ft.DataCell(ft.Text(item.code)),
                ft.DataCell(ft.Text(item.name)),
                ft.DataCell(ft.Row(
                    controls=[
                        ft.Text(dist.name)
                        for dist in item.distributors if dist.is_primary
                    ]
                )),
                ft.DataCell(ft.Text(str(item.inventory.quantity_ordered) if item.inventory else "-")),
                ft.DataCell(ft.Text(str(item.inventory.quantity_available) if item.inventory else "-")),
                ft.DataCell(ft.Text(str(item.inventory.quantity_sold) if item.inventory else "-")),
                # ft.DataCell(ft.Text(item["unit_price"])),
            ])

    def count_items(self) -> int:
        with DatabaseManager(DB_PATH) as db:
            row = db.fetch_one("SELECT COUNT(*) AS n FROM items")
        return row["n"] if row else 0

    def build_order_by(self) -> str:
        columns = {
            0: "it.item_code",
            1: "it.item_name",
            2: "COALESCE(d.distributor_name, '')",
            3: "COALESCE(inv.quantity_ordered, 0)",
            4: "COALESCE(inv.quantity_available, 0)",
            5: "COALESCE(inv.quantity_sold, 0)",
        }
        column = columns.get(self.sort_column_index) if self.sort_column_index is not None else None
        if column is None:
            return "it.item_id ASC"
        direction = "ASC" if self.sort_ascending else "DESC"
        return f"{column} {direction}, it.item_id ASC"

    def get_items_page(self, offset: int, limit: int) -> list[Item]:
        query = f"""
            SELECT it.item_id, it.item_code, it.item_name,
                   d.distributor_id AS main_distributor_id,
                   d.distributor_name AS main_distributor_name,
                   inv.inventory_id, inv.quantity_available,
                   inv.quantity_ordered, inv.quantity_sold
            FROM items it
            LEFT JOIN (
                SELECT item_id, distributor_id
                FROM item_distributors
                WHERE is_primary = TRUE
                GROUP BY item_id
            ) idp ON idp.item_id = it.item_id
            LEFT JOIN distributors d ON d.distributor_id = idp.distributor_id
            LEFT JOIN inventory inv ON inv.item_id = it.item_id
            ORDER BY {self.build_order_by()}
            LIMIT ? OFFSET ?
        """
        with DatabaseManager(DB_PATH) as db:
            rows = db.fetch_all(query, (limit, offset))
        return [self.row_to_item(row) for row in rows]

    def row_to_item(self, row: dict) -> Item:
        item = Item(row["item_id"], row["item_code"], row["item_name"])
        if row["inventory_id"] is not None:
            item.inventory = Inventory(
                row["inventory_id"], row["item_id"],
                row["quantity_available"], row["quantity_ordered"], row["quantity_sold"],
            )
        if row["main_distributor_id"] is not None:
            item.distributors = [
                Distributor(row["main_distributor_id"], row["main_distributor_name"], True)
            ]
        return item

    def load_first_page(self):
        self.total_items = self.count_items()
        self.displayed_items = self.get_items_page(0, ITEMS_PAGE_SIZE)
        self.has_more = len(self.displayed_items) < self.total_items

    def load_more(self, e: ft.Event[ft.Button] = None):
        if self.is_loading or not self.has_more:
            return

        self.is_loading = True
        self.update_pagination_controls()

        new_items = self.get_items_page(len(self.displayed_items), ITEMS_PAGE_SIZE)
        self.displayed_items.extend(new_items)
        self.table.rows.extend(self.build_row(item) for item in new_items)
        self.has_more = len(self.displayed_items) < self.total_items
        self.is_loading = False

        self.table.update()
        self.update_pagination_controls()

    def handle_table_scroll(self, e: ft.OnScrollEvent):
        if e.max_scroll_extent <= 0:
            return
        if e.pixels >= e.max_scroll_extent - SCROLL_LOAD_THRESHOLD:
            self.load_more()

    def update_pagination_controls(self):
        self.loaded_text.value = f"Loaded {len(self.displayed_items)} of {self.total_items} items"
        self.load_more_button.visible = self.has_more
        self.load_more_button.disabled = self.is_loading
        self.loaded_text.update()
        self.load_more_button.update()

    def delete_all_items(self, e: ft.Event[ft.Button] = None):
        # TODO Delete all related tables with items delete
        with DatabaseManager(DB_PATH) as db:
            db.execute_query("DELETE FROM items")
            db.execute_query("DELETE FROM item_distributors")
            db.execute_query("DELETE FROM inventory")
            print("Deleted All Items Data")
        self.load_first_page()
        self.refresh_table_rows()
        self.update_pagination_controls()

    async def handle_pick_files(self, e: ft.Event[ft.Button]):
        files = await ft.FilePicker().pick_files(
            with_data=True,
            allow_multiple=False,
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["xls", "xlsx"],
        )
        self.files = files
        self.pick_file_button.content = f"Files picked: {files[0].name}" if files else "No files selected"
        self.pick_file_button.update()

    def handle_import_type_change(self, e: ft.Event[ft.RadioGroup]):
        self.selected_import_type = e.control.value

    def handle_import(self, e: ft.Event[ft.Button]):
        if not self.files:
            return

        df = pd.read_excel(self.files[0].path)

        if self.selected_import_type == "items":

            for row in df.itertuples():
                try:
                    with DatabaseManager(DB_PATH) as db:
                        db.execute_query("INSERT INTO items (item_code, item_name) VALUES (?, ?)", (row[1], row[2]))
                        it = db.fetch_simple_one_item(row[1])
                        if row[3]:
                            distro = db.fetch_one("SELECT * FROM distributors WHERE distributor_name = ?", (row[3], ))
                            if distro and it:
                                db.execute_query(
                                    "INSERT INTO item_distributors (item_id, distributor_id, is_primary) VALUES (?, ?, TRUE)",
                                    (it.id, distro["distributor_id"])
                                )
                except sqlite3.Error as err:
                    print(f"Error : %{err}")

        elif self.selected_import_type == "avil_stock":
            for row in df.itertuples():
                if row[0] != 0:
                    try:
                        with DatabaseManager(DB_PATH) as db:
                            it = db.fetch_simple_one_item(row[1])
                            if it:
                                if it.inventory:
                                    db.execute_query("UPDATE inventory SET quantity_available = ? WHERE inventory_id = ?", (row[7], it.inventory.id))
                                else:
                                    db.execute_query("INSERT INTO inventory (item_id, quantity_available) VALUES (?, ?)", (it.id, row[7]))
                    except sqlite3.Error as err:
                        print(f"Error : %{err}")

        elif self.selected_import_type == "sold_stock":
            for row in df.itertuples():
                if row[0] != 0:
                    print(row[1], row[11])
                    try:
                        with DatabaseManager(DB_PATH) as db:
                            it = db.fetch_simple_one_item(row[1])
                            if it:
                                if it.inventory:
                                    db.execute_query("UPDATE inventory SET quantity_sold = ? WHERE inventory_id = ?", (row[11], it.inventory.id))
                                else:
                                    db.execute_query("INSERT INTO inventory (item_id, quantity_sold) VALUES (?, ?)", (it.id, row[11]))
                    except sqlite3.Error as err:
                        print(f"Error : %{err}")

        self.files = []
        self.pick_file_button.content = "Pick file"
        self.load_first_page()
        self.refresh_table_rows()
        self.update_pagination_controls()
        self.page.pop_dialog()
