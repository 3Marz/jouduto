
import sqlite3

from database import DatabaseManager
from datatypes import Item

from components.dropdowns import DistributorDropdown

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

        # --- New Item ---
        self.new_item_code_field = ft.TextField(label="Item Code", dense=True, text_size=13, border_radius=12)
        self.new_item_name_field = ft.TextField(
            label="Item Name", dense=True, text_size=13, border_radius=12,
            on_submit=self.handle_create_item,
        )
        self.new_item_distributor_dropdown = DistributorDropdown(
            label="Main Distributor",
            expand=True,
            dense=True,
            text_size=13,
            border_radius=12,
        )
        self.new_item_status = ft.Text("")
        self.new_item_modal = ft.AlertDialog(
            title=ft.Text("New Item"),
            content=ft.Column([
                self.new_item_code_field,
                self.new_item_name_field,
                self.new_item_distributor_dropdown,
                self.new_item_status,
            ], tight=True, width=380, spacing=10),
            actions=[
                ft.TextButton("Cancel", on_click=lambda _: self.page.pop_dialog()),
                ft.ElevatedButton("Create", on_click=self.handle_create_item),
            ],
        )
        self.new_item_button = ft.Button(
            "New Item",
            icon=ft.Icons.ADD,
            height=40,
            on_click=lambda e: self.page.show_dialog(self.new_item_modal),
        )

        # --- Tags ---
        self.item_tags: list[tuple[int, str]] = []
        self.pending_added_tags: set[str] = set()
        self.pending_removed_tags: set[str] = set()
        self.all_tags: list[tuple[int, str]] = self.get_all_tags()
        self.tags_wrap = ft.Row(wrap=True, spacing=6, run_spacing=6, controls=[])
        self.tag_search = ft.SearchBar(
            bar_hint_text="Search tags or type a new one...",
            view_hint_text="Pick an existing tag or type to create it",
            expand=True,
            on_change=self.handle_tag_search_change,
            on_submit=self.handle_tag_search_submit,
            on_tap=self.handle_tag_search_tap,
            controls=self.build_tag_suggestion_tiles(self.all_tags),
        )

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
        self.distributor_dropdown = DistributorDropdown(
            label="Main Distributor",
            expand=True,
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
                            ft.Divider(),
                            ft.Text("Tags", weight=ft.FontWeight.BOLD),
                            self.tags_wrap,
                            self.tag_search,
                            ft.Divider(),
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
                        ],
                    ),
                    ft.VerticalDivider(),
                    # Right column: purchase orders history.
                    ft.Column(
                        expand=True,
                        scroll=ft.ScrollMode.AUTO,
                        controls=[
                            ft.Text("Stock", weight=ft.FontWeight.BOLD),
                            self.inventory_text,
                            ft.Divider(),
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
                    ft.Row(
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            self.new_item_button,
                            self.search_bar,
                        ]
                    ),
                    self.details_panel,
                ],
            )
        )

    def reload(self):
        self.items = self.get_items()
        self.distributor_dropdown.refresh()
        self.new_item_distributor_dropdown.refresh()
        self.all_tags = self.get_all_tags()
        self.update_tag_suggestions(self.tag_search.value)
        if self.selected_item_id is not None and any(
            item.id == self.selected_item_id for item in self.items
        ):
            self.load_item_details(self.selected_item_id)
        self.update()

    def get_items(self) -> list[Item]:
        with DatabaseManager() as db:
            rows = db.fetch_all(
                "SELECT item_id, item_code, item_name FROM items ORDER BY item_code"
            )
        return [Item(r["item_id"], r["item_code"], r["item_name"]) for r in rows]

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
        with DatabaseManager() as db:
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
            tag_rows = db.fetch_all(
                """
                SELECT t.tag_id, t.tag_name
                FROM item_tags it
                JOIN tags t ON it.tag_id = t.tag_id
                WHERE it.item_id = ?
                ORDER BY t.tag_name
                """,
                (item_id,),
            )

        self.item_tags = [(r["tag_id"], r["tag_name"]) for r in tag_rows]
        self.pending_added_tags.clear()
        self.pending_removed_tags.clear()
        self.rebuild_tags_ui()

        self.distributor_dropdown.value = (
            str(primary["distributor_id"]) if primary else None
        )

        if inv:
            self.inventory_text.value = (
                f"Ordered: {inv['quantity_ordered']}    "
                f"Available: {inv['quantity_available']}    "
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

    def handle_create_item(self, e: ft.Event[ft.Control] = None):
        code = (self.new_item_code_field.value or "").strip()
        name = (self.new_item_name_field.value or "").strip()
        if not code or not name:
            self.new_item_status.value = "Code and Name are required"
            self.new_item_status.color = ft.Colors.ERROR
            self.new_item_status.update()
            return

        try:
            with DatabaseManager() as db:
                db.execute_query(
                    "INSERT INTO items (item_code, item_name) VALUES (?, ?)",
                    (code, name),
                )
                item_id = db.cur.lastrowid
                db.execute_query(
                    "INSERT INTO inventory (item_id, quantity_available, quantity_ordered, quantity_sold) "
                    "VALUES (?, 0, 0, 0)",
                    (item_id,),
                )
                distributor_value = self.new_item_distributor_dropdown.value
                if distributor_value:
                    db.execute_query(
                        "INSERT INTO item_distributors (item_id, distributor_id, is_primary) "
                        "VALUES (?, ?, TRUE)",
                        (item_id, int(distributor_value)),
                    )
        except sqlite3.Error as err:
            self.new_item_status.value = f"Error: {err}"
            self.new_item_status.color = ft.Colors.ERROR
            self.new_item_status.update()
            return

        self.new_item_code_field.value = ""
        self.new_item_name_field.value = ""
        self.new_item_distributor_dropdown.value = None
        self.new_item_status.value = ""
        self.page.pop_dialog()

        self.items = self.get_items()
        self.search_bar.controls = self.build_suggestion_tiles(self.items[:SEARCH_SUGGESTION_LIMIT])
        self.search_bar.update()
        self.open_focused_item(item_id)

    def current_tag_names(self) -> list[str]:
        names = [n for _, n in self.item_tags if n not in self.pending_removed_tags]
        names.extend(sorted(self.pending_added_tags))
        return names

    def rebuild_tags_ui(self):
        names = self.current_tag_names()
        if not names:
            self.tags_wrap.controls = [
                ft.Text(
                    "No tags",
                    italic=True,
                    size=12,
                    color=ft.Colors.with_opacity(0.6, ft.Colors.ON_SURFACE),
                )
            ]
            return
        self.tags_wrap.controls = [
            ft.Chip(
                label=ft.Text(name),
                delete_icon=ft.Icons.CLOSE,
                delete_icon_tooltip="Remove tag",
                delete_icon_color=ft.Colors.ERROR,
                on_delete=lambda e, n=name: self.handle_remove_tag(n),
            )
            for name in names
        ]

    def get_all_tags(self) -> list[tuple[int, str]]:
        with DatabaseManager() as db:
            return [
                (r["tag_id"], r["tag_name"])
                for r in db.fetch_all("SELECT tag_id, tag_name FROM tags ORDER BY tag_name")
            ]

    def build_tag_suggestion_tiles(self, tags: list[tuple[int, str]]) -> list[ft.Control]:
        return [
            ft.ListTile(
                leading=ft.Icon(ft.Icons.TAG),
                title=ft.Text(name),
                data=name,
                on_click=self.handle_select_existing_tag,
            )
            for _, name in tags
        ]

    def update_tag_suggestions(self, query: str):
        query = (query or "").strip().lower()
        if not query:
            matches = self.all_tags
        else:
            matches = [
                tag for tag in self.all_tags if query in tag[1].lower()
            ]
        self.tag_search.controls = self.build_tag_suggestion_tiles(matches)

    def handle_tag_search_change(self, e: ft.Event[ft.SearchBar]):
        self.update_tag_suggestions(e.control.value)
        self.tag_search.update()

    async def handle_tag_search_tap(self, e: ft.Event[ft.SearchBar]):
        self.update_tag_suggestions(self.tag_search.value)
        self.tag_search.update()
        await self.tag_search.open_view()

    async def handle_tag_search_submit(self, e: ft.Event[ft.SearchBar]):
        name = (self.tag_search.value or "").strip()
        if name:
            self.add_tag(name)
        await self.tag_search.close_view(self.tag_search.value)

    async def handle_select_existing_tag(self, e: ft.Event[ft.ListTile]):
        self.add_tag(e.control.data)
        await self.tag_search.close_view(self.tag_search.value)

    def add_tag(self, name: str):
        if not name or name in self.current_tag_names():
            return
        if name in self.pending_removed_tags:
            self.pending_removed_tags.discard(name)
        else:
            self.pending_added_tags.add(name)
        self.tag_search.value = ""
        self.rebuild_tags_ui()
        self.tags_wrap.update()
        self.tag_search.update()
        self.update_tag_suggestions("")

    def handle_remove_tag(self, name: str):
        if name in self.pending_added_tags:
            self.pending_added_tags.discard(name)
        else:
            self.pending_removed_tags.add(name)
        self.rebuild_tags_ui()
        self.tags_wrap.update()

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
            with DatabaseManager() as db:
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

                # Commit tag changes (inline auto-create as needed).
                for tagname in self.pending_added_tags:
                    db.execute_query(
                        "INSERT OR IGNORE INTO tags (tag_name) VALUES (?)",
                        (tagname,),
                    )
                    tag_row = db.fetch_one(
                        "SELECT tag_id FROM tags WHERE tag_name = ?", (tagname,)
                    )
                    if tag_row:
                        db.execute_query(
                            "INSERT OR IGNORE INTO item_tags (item_id, tag_id) VALUES (?, ?)",
                            (self.selected_item_id, tag_row["tag_id"]),
                        )
                for tagname in self.pending_removed_tags:
                    tag_row = db.fetch_one(
                        "SELECT tag_id FROM tags WHERE tag_name = ?", (tagname,)
                    )
                    if tag_row:
                        db.execute_query(
                            "DELETE FROM item_tags WHERE item_id = ? AND tag_id = ?",
                            (self.selected_item_id, tag_row["tag_id"]),
                        )
                # Drop tags that no longer belong to any item.
                db.execute_query(
                    "DELETE FROM tags WHERE tag_id NOT IN (SELECT DISTINCT tag_id FROM item_tags)"
                )
                self.item_tags = [
                    (r["tag_id"], r["tag_name"])
                    for r in db.fetch_all(
                        """
                        SELECT t.tag_id, t.tag_name
                        FROM item_tags it
                        JOIN tags t ON it.tag_id = t.tag_id
                        WHERE it.item_id = ?
                        ORDER BY t.tag_name
                        """,
                        (self.selected_item_id,),
                    )
                ]
                self.pending_added_tags.clear()
                self.pending_removed_tags.clear()

            for item in self.items:
                if item.id == self.selected_item_id:
                    item.name = name
                    break

            self.rebuild_tags_ui()
            self.tags_wrap.update()
            self.all_tags = self.get_all_tags()
            self.update_tag_suggestions("")
            self.tag_search.update()
            self.save_status.value = "Saved"
            self.save_status.color = ft.Colors.GREEN
            self.save_status.update()
        except sqlite3.Error as err:
            self.save_status.value = f"Error: {err}"
            self.save_status.color = ft.Colors.ERROR
            self.save_status.update()
