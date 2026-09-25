
import sqlite3
import asyncio

from database import DatabaseManager, get_item_history_by_code

import flet as ft
import flet_datatable2 as fdt
import pandas as pd

from datatypes import Inventory, Item, Distributor

ITEMS_PAGE_SIZE = 70
SCROLL_LOAD_THRESHOLD = 600.0
SEARCH_DEBOUNCE_SECONDS = 0.3

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
        self.search_query: str = ""
        self._search_generation: int = 0
        self.scroll_accumulator: float = 0.0
        self.load_first_page()

        self.files: None | list[ft.FilePickerFile] = None
        self.selected_import_type: str | None = "items"

        self.selected_item_ids: set[int] = set()
        self.focused_item_id: int | None = self.displayed_items[0].id if self.displayed_items else None

        self.status_text = ft.Text("No items selected")
        self.mouse_pos = ft.Offset()

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

        # Loads the next page when the user scrolls the mouse wheel over the table.
        self.table_wrapper = ft.ContextMenu(
            items=[
                ft.PopupMenuItem(
                    content="View Item Details",
                    icon=ft.Icons.REMOVE_RED_EYE,
                    on_click=self.handle_view_item_details,
                ),
                ft.PopupMenuItem(
                    content="Previous Years Inventory",
                    icon=ft.Icons.HISTORY,
                    on_click=self.handle_view_history,
                ),
            ],
            secondary_trigger=None,
            expand=True,
            content=ft.GestureDetector(
                on_secondary_tap_down=lambda e: self.handle_mouse_update(e),
                expand=True,
                content=self.table,
            ),
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

        # --- Previous Years Inventory modal ---
        self.history_title = ft.Text("")
        self.history_no_match = ft.Text("", italic=True, color=ft.Colors.OUTLINE)
        self.history_table = fdt.DataTable2(
            expand=True,
            heading_row_color=ft.Colors.with_opacity(1, ft.Colors.SURFACE_CONTAINER_HIGH),
            border=ft.Border.all(1, ft.Colors.SURFACE_CONTAINER_HIGHEST),
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
            columns=[
                fdt.DataColumn2(label=ft.Text("Year")),
                fdt.DataColumn2(label=ft.Text("Ordered"), numeric=True),
                fdt.DataColumn2(label=ft.Text("Available"), numeric=True),
                fdt.DataColumn2(label=ft.Text("Sold"), numeric=True),
                fdt.DataColumn2(label=ft.Text("Status")),
            ],
            rows=[],
        )
        self.history_modal = ft.AlertDialog(
            modal=True,
            title=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.HISTORY),
                    ft.Text("Previous Years Inventory"),
                ]
            ),
            content=ft.Column(
                width=700,
                height=400,
                tight=True,
                scroll=ft.ScrollMode.AUTO,
                controls=[
                    self.history_title,
                    self.history_no_match,
                    self.history_table,
                ],
            ),
            actions=[
                ft.Button("Close", on_click=lambda e: self.page.pop_dialog()),
            ],
        )

        self.imageView = ft.Container(expand=True, content=ft.Text("images"))

        self.search_field = ft.TextField(
            border_radius=ft.BorderRadius.all(30),
            border_color=ft.Colors.SURFACE_BRIGHT,
            hint_text="Search by code or name...",
            icon=ft.Icons.SEARCH,
            on_change=self.handle_search_change,
            on_submit=self.handle_search_submit,
        )

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
                                            ),
                                            ft.Button(
                                                content="History",
                                                icon=ft.Icons.HISTORY,
                                                on_click=self.handle_view_history,
                                                tooltip="Previous years inventory of the focused item",
                                            ),
                                            self.search_field,
                                        ]
                                    ),
                                    ft.Row(
                                        alignment=ft.MainAxisAlignment.END,
                                        expand=True,
                                        controls=[
                                            # ft.Button(
                                            #     "Delete All",
                                            #     icon=ft.Icons.DELETE,
                                            #     on_click=self.delete_all_items
                                            # ),
                                            self.import_data_button,
                                        ]
                                    ),
                                ]
                            ),
                            self.status_text,
                            self.table_wrapper,
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

    def search_pattern(self) -> str | None:
        """LIKE pattern (escaped) for the active search, or None when empty."""
        query = (self.search_query or "").strip()
        if not query:
            return None
        escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        return f"%{escaped}%"

    async def handle_search_change(self, e: ft.Event[ft.TextField]):
        self.search_query = e.control.value or ""
        self._search_generation += 1
        generation = self._search_generation
        await asyncio.sleep(SEARCH_DEBOUNCE_SECONDS)
        if generation != self._search_generation:
            return  # a newer keystroke superseded this one
        try:
            self.apply_search()
        except RuntimeError:
            pass  # page was left during the debounce window

    def handle_search_submit(self, e: ft.Event[ft.TextField]):
        self.search_query = e.control.value or ""
        self._search_generation += 1  # cancel any pending debounce
        self.apply_search()

    def apply_search(self):
        self.selected_item_ids = set()
        self.load_first_page()
        self.focused_item_id = self.displayed_items[0].id if self.displayed_items else None
        self.refresh_table_rows()
        self.update_pagination_controls()

    def build_columns(self) -> list[fdt.DataColumn2]:
        return [
            fdt.DataColumn2(label=ft.Text("Item Code"), on_sort=self.handle_sort),
            fdt.DataColumn2(label=ft.Text("Name"), on_sort=self.handle_sort),
            fdt.DataColumn2(label=ft.Text("Main Distributor"), on_sort=self.handle_sort),
            fdt.DataColumn2(label=ft.Text("Ordered Stock"), on_sort=self.handle_sort),
            fdt.DataColumn2(label=ft.Text("Available Stock"), on_sort=self.handle_sort),
            fdt.DataColumn2(label=ft.Text("Sold Stock"), on_sort=self.handle_sort),
            # fdt.DataColumn2(label=ft.Text("Unit Price"), numeric=True, on_sort=self.handle_sort),
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

    async def handle_right_click(self, e: ft.Event[ft.DataRow]):
        row = e.control
        item_id = row.data
        self.focused_item_id = item_id

        await self.table_wrapper.open(
            global_position=self.mouse_pos
        )

        self.refresh_table_rows()

    def handle_view_item_details(self, e: ft.Event[ft.PopupMenuItem]):
        if self.focused_item_id is None:
            return
        self.page.navigate(f"/item-details?item={self.focused_item_id}")

    def handle_view_history(self, e: ft.Event[ft.Control] = None):
        if self.focused_item_id is None:
            return
        item = next(
            (i for i in self.displayed_items if i.id == self.focused_item_id),
            None,
        )
        if item is None:
            return

        history = get_item_history_by_code(item.code)

        self.history_title.value = f"{item.code} — {item.name}"
        self.history_no_match.value = (
            "" if history else f"No previous-year data found for '{item.code}'."
        )
        self.history_no_match.visible = not history

        self.history_table.rows = [
            fdt.DataRow2(
                cells=[
                    ft.DataCell(ft.Text(str(h["year"]))),
                    ft.DataCell(ft.Text(f"{h['ordered']:,}")),
                    ft.DataCell(ft.Text(f"{h['available']:,}")),
                    ft.DataCell(ft.Text(f"{h['sold']:,}")),
                    ft.DataCell(ft.Text(
                        "Not found this year" if not h["found"] else "Found",
                        italic=not h["found"],
                    )),
                ]
            )
            for h in history
        ]

        self.page.show_dialog(self.history_modal)
        self.history_table.update()
        self.history_title.update()
        self.history_no_match.update()

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
        return [self.build_row(item) for item in self.displayed_items]

    def build_row(self, item: Item) -> fdt.DataRow2:
        return fdt.DataRow2(
            selected=item.id in self.selected_item_ids,
            data=item.id,
            on_secondary_tap=self.handle_right_click,
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
        pattern = self.search_pattern()
        with DatabaseManager() as db:
            if pattern is not None:
                row = db.fetch_one(
                    "SELECT COUNT(*) AS n FROM items "
                    "WHERE item_code LIKE ? ESCAPE '\\' "
                    "OR item_name LIKE ? ESCAPE '\\'",
                    (pattern, pattern),
                )
            else:
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
        where = ""
        params: list = []
        pattern = self.search_pattern()
        if pattern is not None:
            where = (
                "WHERE it.item_code LIKE ? ESCAPE '\\' "
                "OR it.item_name LIKE ? ESCAPE '\\'"
            )
            params = [pattern, pattern]

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
            {where}
            ORDER BY {self.build_order_by()}
            LIMIT ? OFFSET ?
        """
        with DatabaseManager() as db:
            rows = db.fetch_all(query, (*params, limit, offset))
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
        self.scroll_accumulator = 0.0

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

    def handle_mouse_update(self, e: ft.TapEvent):
        self.mouse_pos = e.global_position

    def update_pagination_controls(self):
        self.loaded_text.value = f"Loaded {len(self.displayed_items)} of {self.total_items} items"
        self.load_more_button.visible = self.has_more
        self.load_more_button.disabled = self.is_loading
        self.loaded_text.update()
        self.load_more_button.update()

    def delete_all_items(self, e: ft.Event[ft.Button] = None):
        # TODO Delete all related tables with items delete
        with DatabaseManager() as db:
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
                    with DatabaseManager() as db:
                        db.execute_query("INSERT INTO items (item_code, item_name) VALUES (?, ?)", (row[1], row[2]))
                        it = db.fetch_simple_one_item(row[1])
                        if row[3]:
                            distro = db.fetch_one("SELECT * FROM distributors WHERE distributor_name = ?", (row[3], ))
                            if not distro:
                                db.execute_query("INSERT INTO distributors (distributor_name) VALUES (?)", (row[3], ))
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
                        with DatabaseManager() as db:
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
                        with DatabaseManager() as db:
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
