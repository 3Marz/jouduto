
import sqlite3
from typing import Tuple

from database import DatabaseManager
from constants import DB_PATH

import flet as ft
import flet_datatable2 as fdt
import pandas as pd

from datatypes import Inventory, Item, Distributor

@ft.control
class ItemsPage(ft.Container):
    def __init__(self):
        super().__init__()
        self.expand = True
        
        self.displayed_items = self.get_items_data()
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
        self.table: fdt.DataTable2 = fdt.DataTable2(
            expand=True,
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
                            self.table
                        ]
                    )
                ),
            ]
        )

    def build_columns(self) -> list[fdt.DataColumn2]:
        return [
            fdt.DataColumn2(label=ft.Text("Item Code"), on_sort=self.handle_sort),
            fdt.DataColumn2(label=ft.Text("Name"), on_sort=self.handle_sort),
            fdt.DataColumn2(label=ft.Text("Main Distributor"), on_sort=self.handle_sort),
            fdt.DataColumn2(label=ft.Text("Avilable Stock"), on_sort=self.handle_sort),
            fdt.DataColumn2(label=ft.Text("Sold Stock"), on_sort=self.handle_sort),
            # fdt.DataColumn2(label=ft.Text("Unit Price"), numeric=True, on_sort=self.handle_sort),
        ]

    def handle_sort(self, e: ft.DataColumnSortEvent):
        sorters = [
            lambda i: i.code,
            lambda i: i.name,
            lambda i: i.distributors[0].name,
            lambda i: i.inventory.quantity_available if i.inventory else 1,
            lambda i: i.inventory.quantity_sold if i.inventory else 1,
            # lambda i: i["unit_price"],
        ]
        self.displayed_items.sort(key=sorters[e.column_index], reverse = not e.ascending)
        self.table.sort_column_index = e.column_index
        self.table.sort_ascending = e.ascending
        self.refresh_table_rows()

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

    def build_rows(self) -> list[fdt.DataRow2]:
        return [ 
            fdt.DataRow2(
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
                    ft.DataCell(ft.Text(str(item.inventory.quantity_available) if item.inventory else "-")),
                    ft.DataCell(ft.Text(str(item.inventory.quantity_sold) if item.inventory else "-")),
                    # ft.DataCell(ft.Text(item["unit_price"])),
            ]) 
            for item in self.displayed_items
        ]

    def get_items_data(self):
        items: list[Item] = []
        with DatabaseManager(DB_PATH) as db:
            db_items = db.fetch_all("SELECT * FROM items")
            items = [Item(itm["item_id"], itm["item_code"], itm["item_name"]) for itm in db_items]
            for i in range(len(items)):
                db_inv = db.fetch_one("SELECT * FROM inventory WHERE inventory.item_id = ?", (items[i].id,))
                distros = db.fetch_all("""
                    SELECT d.distributor_id, d.distributor_name, itds.is_primary
                    FROM distributors d
                    JOIN item_distributors itds ON d.distributor_id = itds.distributor_id
                    JOIN items it ON itds.item_id = it.item_id
                    WHERE it.item_id = ?
                """, (items[i].id,))
                items[i].inventory = Inventory(db_inv["inventory_id"], db_inv["item_id"], db_inv["quantity_available"], db_inv["quantity_ordered"], db_inv["quantity_sold"]) if db_inv else None
                items[i].distributors = [Distributor(d["distributor_id"], d["distributor_name"], d["is_primary"]) for d in distros]
        return items

    def delete_all_items(self):
        # TODO Delete all related tables with items delete
        with DatabaseManager(DB_PATH) as db:
            db.execute_query("DELETE FROM items")
            db.execute_query("DELETE FROM item_distributors")
            db.execute_query("DELETE FROM inventory")
            print("Deleted All Items Data")
        self.displayed_items = self.get_items_data()
        self.refresh_table_rows()

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

        self.files = []
        self.pick_file_button.content = "Pick file"
        self.displayed_items = self.get_items_data()
        self.refresh_table_rows()
        self.page.pop_dialog()



