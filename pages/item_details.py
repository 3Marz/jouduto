
import sqlite3

from constants import DB_PATH
from database import DatabaseManager
from datatypes import Item

import flet as ft
import flet_datatable2 as fdt


SEARCH_SUGGESTION_LIMIT = 50


@ft.control
class ItemDetailsPage(ft.Container):
    def __init__(self):
        super().__init__()
        self.expand = True

        # State
        self.items: list[Item] = self.get_items()
        self.selected_item_id: int | None = None

        # --- Item Search ---
        self.search_bar = ft.SearchBar(
            bar_hint_text="Search item by code or name...",
            view_hint_text="Type an item code or name...",
            expand=True,
            on_change=self.handle_search_change,
            on_submit=self.handle_search_submit,
            on_tap=self.handle_search_tap,
            controls=self.build_suggestion_tiles(
                self.items[:SEARCH_SUGGESTION_LIMIT]
            ),
        )

        # --- Item Details / Editing ---
        self.code_text = ft.Text("-", size=20, weight=ft.FontWeight.BOLD)
        self.name_field = ft.TextField(label="Name", expand=True)
        self.distributor_dropdown = ft.Dropdown(
            label="Main Distributor",
            expand=True,
            options=self.build_distributor_options(),
        )
        self.inventory_text = ft.Text("")
        self.save_status = ft.Text("")

        self.po_placeholder = ft.Text("")
        self.po_table = fdt.DataTable2(
            columns=[
                fdt.DataColumn2(label=ft.Text("PO #")),
                fdt.DataColumn2(label=ft.Text("Distributor")),
                fdt.DataColumn2(label=ft.Text("Qty Ordered"), numeric=True),
                fdt.DataColumn2(label=ft.Text("Unit Cost"), numeric=True),
                fdt.DataColumn2(label=ft.Text("Status")),
                fdt.DataColumn2(label=ft.Text("Order Date")),
            ],
            rows=[],
        )

        self.details_panel = ft.Container(
            visible=False,
            expand=True,
            content=ft.Row(
                expand=True,
                controls=[
                    # Left column: item info & editing.
                    ft.Column(
                        width=300,
                        scroll=ft.ScrollMode.AUTO,
                        controls=[
                            ft.Text("Item Code", size=12, color=ft.Colors.OUTLINE),
                            self.code_text,
                            ft.Divider(),
                            self.name_field,
                            self.distributor_dropdown,
                            ft.Row(
                                controls=[
                                    ft.Button(
                                        "Save Changes",
                                        icon=ft.Icons.SAVE,
                                        on_click=self.handle_save,
                                    ),
                                    self.save_status,
                                ]
                            ),
                            ft.Divider(),
                            ft.Text("Stock", weight=ft.FontWeight.BOLD),
                            self.inventory_text,
                        ],
                    ),
                    ft.VerticalDivider(),
                    # Right column: purchase orders history.
                    ft.Column(
                        expand=True,
                        scroll=ft.ScrollMode.AUTO,
                        controls=[
                            ft.Text("Purchase Orders", weight=ft.FontWeight.BOLD),
                            self.po_placeholder,
                            self.po_table,
                        ],
                    ),
                ],
            ),
        )

        self.content = ft.SafeArea(
            content=ft.Column(
                expand=True,
                controls=[
                    ft.Column(
                        controls=[
                            ft.Text("Item Details", size=30, weight=ft.FontWeight.BOLD),
                            self.search_bar
                        ]
                    ),
                    self.details_panel,
                ],
            )
        )

    def reload(self):
        self.items = self.get_items()
        self.distributor_dropdown.options = self.build_distributor_options()
        if self.selected_item_id is not None and any(
            item.id == self.selected_item_id for item in self.items
        ):
            self.load_item_details(self.selected_item_id)
        self.update()

    def get_items(self) -> list[Item]:
        with DatabaseManager(DB_PATH) as db:
            rows = db.fetch_all(
                "SELECT item_id, item_code, item_name FROM items ORDER BY item_code"
            )
        return [Item(r["item_id"], r["item_code"], r["item_name"]) for r in rows]

    def build_distributor_options(self) -> list[ft.DropdownOption]:
        with DatabaseManager(DB_PATH) as db:
            distros = db.fetch_all(
                "SELECT distributor_id, distributor_name FROM distributors "
                "ORDER BY distributor_name"
            )
        return [
            ft.DropdownOption(
                key=str(d["distributor_id"]), text=d["distributor_name"]
            )
            for d in distros
        ]

    def build_suggestion_tiles(self, items: list[Item]) -> list[ft.Control]:
        return [
            ft.ListTile(
                leading=ft.Icon(ft.Icons.INVENTORY_2_OUTLINED),
                title=ft.Text(f"{item.code} - {item.name}"),
                data=item.id,
                on_click=self.handle_select_item,
            )
            for item in items
        ]

    def update_search_suggestions(self, query: str):
        query = (query or "").strip().lower()
        if not query:
            matches = self.items
        else:
            matches = [
                item
                for item in self.items
                if query in item.code.lower() or query in item.name.lower()
            ]
        self.search_bar.controls = self.build_suggestion_tiles(
            matches[:SEARCH_SUGGESTION_LIMIT]
        )

    def handle_search_change(self, e: ft.Event[ft.SearchBar]):
        self.update_search_suggestions(e.control.value)
        self.search_bar.update()

    async def handle_search_tap(self, e: ft.Event[ft.SearchBar]):
        self.update_search_suggestions(self.search_bar.value)
        self.search_bar.update()
        await self.search_bar.open_view()

    async def handle_search_submit(self, e: ft.Event[ft.SearchBar]):
        query = (e.control.value or "").strip().lower()
        if not query:
            return
        match = next(
            (
                item
                for item in self.items
                if item.code.lower() == query or item.name.lower() == query
            ),
            None,
        ) or next(
            (
                item
                for item in self.items
                if query in item.code.lower() or query in item.name.lower()
            ),
            None,
        )
        if match:
            await self.select_item_by_id(match.id)

    async def handle_select_item(self, e: ft.Event[ft.ListTile]):
        await self.select_item_by_id(e.control.data)

    async def select_item_by_id(self, item_id: int):
        if not self.open_focused_item(item_id):
            return

        self.search_bar.update()
        self.details_panel.update()
        await self.search_bar.close_view(self.search_bar.value)

    def open_focused_item(self, item_id: int) -> bool:
        """Loads an item's details into the panel (sync; safe before page attach)."""
        item = next((i for i in self.items if i.id == item_id), None)
        if item is None:
            return False

        self.selected_item_id = item.id
        self.code_text.value = item.code
        self.name_field.value = item.name
        self.save_status.value = ""
        self.load_item_details(item.id)
        self.details_panel.visible = True
        self.search_bar.value = f"{item.code} - {item.name}"
        return True

    def load_item_details(self, item_id: int):
        with DatabaseManager(DB_PATH) as db:
            inv = db.fetch_one(
                "SELECT * FROM inventory WHERE item_id = ?", (item_id,)
            )
            primary = db.fetch_one(
                "SELECT distributor_id FROM item_distributors "
                "WHERE item_id = ? AND is_primary = TRUE LIMIT 1",
                (item_id,),
            )
            pos = db.fetch_all(
                """
                SELECT po.po_number, po.status, po.order_date, d.distributor_name,
                       pi.quantity_ordered, pi.unit_cost
                FROM po_items pi
                JOIN purchase_orders po ON pi.po_id = po.po_id
                JOIN distributors d ON po.distributor_id = d.distributor_id
                WHERE pi.item_id = ?
                ORDER BY po.order_date DESC
                """,
                (item_id,),
            )

        self.distributor_dropdown.value = (
            str(primary["distributor_id"]) if primary else None
        )

        if inv:
            self.inventory_text.value = (
                f"Available: {inv['quantity_available']}    "
                f"Ordered: {inv['quantity_ordered']}    "
                f"Sold: {inv['quantity_sold']}"
            )
        else:
            self.inventory_text.value = "No inventory record"

        self.po_table.rows = [
            fdt.DataRow2(
                cells=[
                    ft.DataCell(ft.Text(po["po_number"])),
                    ft.DataCell(ft.Text(po["distributor_name"])),
                    ft.DataCell(ft.Text(str(po["quantity_ordered"]))),
                    ft.DataCell(ft.Text(str(po["unit_cost"]))),
                    ft.DataCell(ft.Text(po["status"])),
                    ft.DataCell(ft.Text(po["order_date"] or "")),
                ]
            )
            for po in pos
        ]
        self.po_placeholder.value = (
            "" if pos else "This item is not in any purchase order."
        )
        self.po_placeholder.visible = not pos

    def handle_save(self, e: ft.Event[ft.Button]):
        if self.selected_item_id is None:
            return

        name = (self.name_field.value or "").strip()
        if not name:
            self.save_status.value = "Name cannot be empty"
            self.save_status.color = ft.Colors.ERROR
            self.save_status.update()
            return

        distributor_value = self.distributor_dropdown.value

        try:
            with DatabaseManager(DB_PATH) as db:
                db.execute_query(
                    "UPDATE items SET item_name = ? WHERE item_id = ?",
                    (name, self.selected_item_id),
                )

                # Exactly one primary distributor: clear the flag, then set chosen.
                db.execute_query(
                    "UPDATE item_distributors SET is_primary = FALSE WHERE item_id = ?",
                    (self.selected_item_id,),
                )
                if distributor_value:
                    distributor_id = int(distributor_value)
                    exists = db.fetch_one(
                        "SELECT 1 FROM item_distributors "
                        "WHERE item_id = ? AND distributor_id = ?",
                        (self.selected_item_id, distributor_id),
                    )
                    if exists:
                        db.execute_query(
                            "UPDATE item_distributors SET is_primary = TRUE "
                            "WHERE item_id = ? AND distributor_id = ?",
                            (self.selected_item_id, distributor_id),
                        )
                    else:
                        db.execute_query(
                            "INSERT INTO item_distributors "
                            "(item_id, distributor_id, is_primary) "
                            "VALUES (?, ?, TRUE)",
                            (self.selected_item_id, distributor_id),
                        )

            for item in self.items:
                if item.id == self.selected_item_id:
                    item.name = name
                    break

            self.save_status.value = "Saved"
            self.save_status.color = ft.Colors.GREEN
            self.save_status.update()
        except sqlite3.Error as err:
            self.save_status.value = f"Error: {err}"
            self.save_status.color = ft.Colors.ERROR
            self.save_status.update()
