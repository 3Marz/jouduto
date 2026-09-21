import sqlite3
from typing import Tuple

from database import DatabaseManager, get_all_items

import flet as ft
import flet_datatable2 as fdt
import pandas as pd

from datatypes import Inventory, Item, Distributor, PurchaseOrder
from components.dropdowns import DistributorDropdown


def _split_pasted_row(line: str) -> list[str]:
    """Split a pasted row into columns: tabs preferred, whitespace as fallback."""
    if "\t" in line:
        return line.split("\t")
    return line.split()


def parse_pasted_rows(text: str) -> tuple[list[tuple[str, int, float]], list[str]]:
    """Parse clipboard text of 'item_code <tab> qty <tab> cost' rows.

    Returns (rows, problems) where problems describe malformed lines.
    """
    rows: list[tuple[str, int, float]] = []
    problems: list[str] = []
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    for lineno, raw in enumerate(normalized.split("\n"), start=1):
        line = raw.strip()
        if not line:
            continue
        cols = _split_pasted_row(line)
        if len(cols) != 3:
            problems.append(f"Line {lineno}: expected 3 columns, got {len(cols)}")
            continue
        code = cols[0].strip()
        try:
            qty = int(cols[1].strip().replace(",", ""))
        except ValueError:
            problems.append(f"Line {lineno}: invalid qty '{cols[1].strip()}'")
            continue
        try:
            cost = float(cols[2].strip().replace(",", ""))
        except ValueError:
            problems.append(f"Line {lineno}: invalid cost '{cols[2].strip()}'")
            continue
        if qty <= 0:
            problems.append(f"Line {lineno}: qty must be > 0")
            continue
        if cost < 0:
            problems.append(f"Line {lineno}: cost must be >= 0")
            continue
        rows.append((code, qty, cost))
    return rows, problems


SEARCH_SUGGESTION_LIMIT = 50


@ft.control
class POPage(ft.Container):
    def __init__(self):
        super().__init__()
        self.expand = True

        # State
        self.pos: list[PurchaseOrder] = self.get_pos_data()
        self.selected_po_id: int | None = None
        
        # --- Components for PO List ---
        self.po_table = fdt.DataTable2(
            expand=True,
            columns=[
                fdt.DataColumn2(label=ft.Text("PO #"), on_sort=self.handle_sort),
                fdt.DataColumn2(label=ft.Text("Distributor"), on_sort=self.handle_sort),
                fdt.DataColumn2(label=ft.Text("Status"), on_sort=self.handle_sort),
                fdt.DataColumn2(label=ft.Text("Order Date"), on_sort=self.handle_sort),
                fdt.DataColumn2(label=ft.Text("Actions")),
            ],
            rows=self.build_po_rows()
        )

        # --- Create PO Modal ---
        self.distributor_dropdown = DistributorDropdown(
            label="Select Distributor",
            dense=True,
            text_size=16,
            border_radius=12,
        )
        self.po_number_field = ft.TextField(
            label="PO Number",
            dense=True,
            text_size=21,
            border_radius=12,
        )
        
        # Item Selection for New PO: searchable (avoids loading the full catalog into a Dropdown)
        self.items: list[Item] = self.get_items_list()
        self.selected_item_id: int | None = None
        self.item_search = ft.SearchBar(
            bar_hint_text="Search item by code or name...",
            view_hint_text="Type an item code or name...",
            expand=True,
            on_change=self.handle_item_search_change,
            on_submit=self.handle_item_search_submit,
            on_tap=self.handle_item_search_tap,
            controls=self.build_item_suggestion_tiles(
                self.items[:SEARCH_SUGGESTION_LIMIT]
            ),
        )
        self.qty_field = ft.TextField(
            label="Qty", width=72, value="1",
            dense=True, text_size=13, border_radius=12,
        )
        self.cost_field = ft.TextField(
            label="Unit Cost", width=96, value="0.0",
            dense=True, text_size=13, border_radius=12,
        )
        
        self.po_items_placeholder = ft.Text(
            "No items added yet",
            italic=True,
            margin=ft.Margin.all(12),
            color=ft.Colors.with_opacity(0.6, ft.Colors.ON_SURFACE),
        )
        self.po_items_table = fdt.DataTable2(
            expand=True,
            column_spacing=40,
            horizontal_margin=8,
            heading_row_height=34,
            heading_row_color=ft.Colors.SURFACE_CONTAINER,
            columns=[
                fdt.DataColumn2(fixed_width=130, label=ft.Text("Code")),
                fdt.DataColumn2(fixed_width=300, label=ft.Text("Name")),
                fdt.DataColumn2(label=ft.Text("Qty"), numeric=True, heading_row_alignment=ft.MainAxisAlignment.START),
                fdt.DataColumn2(label=ft.Text("Unit Cost"), heading_row_alignment=ft.MainAxisAlignment.START),
                fdt.DataColumn2(label=ft.Text("Amount"), heading_row_alignment=ft.MainAxisAlignment.START),
                fdt.DataColumn2(fixed_width=80, label=ft.Text("Actions")),
            ],
            rows=[],
        )
        self.po_items_list = ft.Container(
            expand=True,
            border=ft.Border.all(1, ft.Colors.SURFACE_CONTAINER),
            border_radius=12,
            content=ft.Column(
                controls=[
                    self.po_items_table,
                    self.po_items_placeholder,
                ],
            ),
        )
        self.current_po_items: list[dict] = []
        self.add_item_error_text = ft.Text("", color=ft.Colors.ERROR)
        self.po_items_total = ft.Text("", size=18, weight=ft.FontWeight.W_600)

        def add_item_to_po(e):
            self.add_item_error_text.value = ""
            if self.selected_item_id is None:
                self.add_item_error_text.value = "Select an item first"
                self.add_item_error_text.update()
                return
            try:
                qty = int(self.qty_field.value)
                cost = float(self.cost_field.value)
            except (TypeError, ValueError):
                self.add_item_error_text.value = "Qty must be a whole number and Unit Cost a number"
                self.add_item_error_text.update()
                return
            if qty <= 0 or cost < 0:
                self.add_item_error_text.value = "Qty must be > 0 and Unit Cost >= 0"
                self.add_item_error_text.update()
                return
            item = next((i for i in self.items if i.id == self.selected_item_id), None)
            if item is None:
                return
            self.current_po_items.append({
                "item_id": item.id,
                "code": item.code,
                "name": item.name,
                "qty": qty,
                "cost": cost
            })
            self.refresh_po_items_preview()

        self.add_item_btn = ft.IconButton(
            icon=ft.Icons.ADD_CIRCLE,
            icon_size=24,
            width=40,
            height=40,
            on_click=add_item_to_po,
        )

        # --- Paste-from-Excel import ---
        self.paste_button = ft.Button(
            "Paste from Excel",
            icon=ft.Icons.CONTENT_PASTE,
            height=32,
            on_click=self.handle_paste_excel,
        )
        self.paste_field = ft.TextField(
            label="Pasted rows (item_code, qty, cost)",
            hint_text="Ctrl+V rows copied from Excel here, then press 'Add to Order'",
            multiline=True,
            min_lines=3,
            max_lines=8,
            expand=True,
            dense=True,
            text_size=13,
            border_radius=12,
        )
        self.paste_status = ft.Text("", size=12)
        self.paste_panel = ft.Column(
            visible=False,
            spacing=6,
            controls=[
                self.paste_field,
                ft.Row(
                    controls=[
                        ft.Button(
                            "Add to Order",
                            icon=ft.Icons.ADD,
                            height=32,
                            on_click=self.add_pasted_items,
                        ),
                        ft.TextButton("Clear", on_click=self.clear_paste),
                    ],
                ),
            ],
        )

        self.create_po_modal = ft.AlertDialog(
            title=ft.Text("Add/Edit Purchase Orders", weight=ft.FontWeight.BOLD),
            content=ft.Column([
                ft.Row(
                    controls=[
                        ft.Row([
                            self.po_number_field,
                            self.distributor_dropdown,
                        ], expand=True),
                        ft.Row([
                            ft.Text("Total : ", weight=ft.FontWeight.BOLD),
                            self.po_items_total,
                        ]),
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN
                ),
                ft.Divider(),
                ft.Text("Items", weight=ft.FontWeight.BOLD, size=14),
                ft.Row(
                    [self.item_search, self.qty_field, self.cost_field, self.add_item_btn],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Row(
                    controls=[
                        self.paste_button,
                        self.paste_status,
                        self.add_item_error_text,
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                self.paste_panel,
                self.po_items_list,
            ], tight=True, width=840, height=520),
            actions=[
                ft.TextButton("Cancel", on_click=lambda _: self.page.pop_dialog()),
                ft.ElevatedButton("Save PO", on_click=self.save_po),
            ]
        )

        # Read-only view of a PO (no editing, no inventory changes)
        self.view_po_status = ft.Text("")
        self.view_po_number = ft.Text("", size=13)
        self.view_po_distributor = ft.Text("", size=13)
        self.view_po_date = ft.Text("", size=13)
        self.view_po_total = ft.Text("", size=18, weight=ft.FontWeight.W_700)
        self.view_po_table = fdt.DataTable2(
            columns=[
                fdt.DataColumn2(label=ft.Text("Code")),
                fdt.DataColumn2(label=ft.Text("Name"), fixed_width=300),
                fdt.DataColumn2(label=ft.Text("Qty"), numeric=True, heading_row_alignment=ft.MainAxisAlignment.START),
                fdt.DataColumn2(label=ft.Text("Unit Cost"), heading_row_alignment=ft.MainAxisAlignment.START),
                fdt.DataColumn2(label=ft.Text("Amount"), heading_row_alignment=ft.MainAxisAlignment.START),
            ],
            rows=[],
            expand=True,
            heading_row_color=ft.Colors.SURFACE_CONTAINER,
            column_spacing=40,
            horizontal_margin=8,
            heading_row_height=34,
        )

        def view_row(label: str, value: ft.Control) -> ft.Row:
            return ft.Row(
                [
                    ft.Text(label, weight=ft.FontWeight.W_600, size=13, width=110),
                    value,
                ],
                spacing=8,
            )

        self.view_po_modal = ft.AlertDialog(
            title=ft.Text("Purchase Order Details"),
            content=ft.Column(
                controls=[
                    ft.Container(
                        padding=ft.Padding.symmetric(horizontal=8, vertical=4),
                        border_radius=10,
                        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                        width=90,
                        alignment=ft.Alignment.CENTER,
                        content=self.view_po_status,
                    ),
                    view_row("PO Number", self.view_po_number),
                    view_row("Distributor", self.view_po_distributor),
                    view_row("Order Date", self.view_po_date),
                    ft.Divider(),
                    ft.Text("Items", weight=ft.FontWeight.BOLD, size=14),
                    ft.Container(
                        height=260,
                        content=ft.Column(
                            controls=[self.view_po_table],
                        ),
                    ),
                    ft.Row([
                        ft.Text("Total", weight=ft.FontWeight.BOLD),
                        self.view_po_total,
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ], tight=True, width=840, height=520),
            actions=[
                ft.TextButton("Close", on_click=lambda _: self.page.pop_dialog()),
            ],
        )

        self.content = ft.SafeArea(
            content=ft.Column(
                expand=True,
                controls=[
                    ft.Row(
                        controls=[
                            ft.Button(
                                "New PO", 
                                icon=ft.Icons.ADD, 
                                on_click=lambda _: self.handle_new_po()
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN
                    ),
                    self.po_table
                ]
            )
        )

    def reload(self):
        self.pos = self.get_pos_data()
        self.po_table.rows = self.build_po_rows()
        self.po_table.update()

    def handle_new_po(self):
        self.page.show_dialog(self.create_po_modal)
        self.reset_create_po_form()

    def get_items_list(self):
        return [
            Item(itm["item_id"], itm["item_code"], itm["item_name"])
            for itm in get_all_items()
        ]

    def get_pos_data(self) -> list[PurchaseOrder]:
        pos = []
        with DatabaseManager() as db:
            db_pos = db.fetch_all("""
                SELECT po.*, d.distributor_name 
                FROM purchase_orders po 
                JOIN distributors d ON po.distributor_id = d.distributor_id
            """)
            for p in db_pos:
                pos.append(PurchaseOrder(
                    id=p["po_id"],
                    po_number=p["po_number"],
                    distributor_id=p["distributor_id"],
                    distributor_name=p["distributor_name"],
                    status=p["status"],
                    order_date=p["order_date"],
                    expected_date=p["expected_date"],
                    received_date=p["received_date"],
                    notes=p["notes"]
                ))
        return pos

    def build_po_rows(self):
        return [
            fdt.DataRow2(
                cells=[
                    ft.DataCell(ft.Text(po.po_number)),
                    ft.DataCell(ft.Text(po.distributor_name)),
                    ft.DataCell(ft.Text(
                        po.status,
                        color=ft.Colors.GREEN if po.status == "ORDERED" else ft.Colors.GREY
                    )),
                    ft.DataCell(ft.Text(po.order_date or "-")),
                    ft.DataCell(ft.Row(self._po_actions(po))),
                ]
            ) for po in self.pos
        ]

    def _po_actions(self, po: PurchaseOrder) -> list[ft.Control]:
        actions = [
            ft.IconButton(ft.Icons.VISIBILITY, tooltip="View",
                          on_click=lambda e, p=po: self.open_po_viewer(p))
        ]
        if po.status == "DRAFT":
            actions.append(
                ft.IconButton(ft.Icons.EDIT, tooltip="Edit",
                              on_click=lambda e, p=po: self.open_po_editor(p))
            )
            actions.append(
                ft.IconButton(ft.Icons.CHECK_CIRCLE, icon_color="green", tooltip="Place Order",
                              on_click=lambda e, p=po: self.mark_po_ordered(p))
            )
        else:
            actions.append(
                ft.IconButton(ft.Icons.UNDO, tooltip="Revert to Draft",
                              on_click=lambda e, p=po: self.revert_po_to_draft(p))
            )
        actions.append(
            ft.IconButton(ft.Icons.DELETE, icon_color="red", tooltip="Delete",
                          on_click=lambda e, p=po: self.delete_po(p))
        )
        return actions

    def refresh_po_table(self):
        self.pos = self.get_pos_data()
        self.po_table.rows = self.build_po_rows()
        self.po_table.update()

    def refresh_po_items_preview(self):
        self.po_items_table.rows = [
            fdt.DataRow2(
                cells=[
                    ft.DataCell(ft.Text(item["code"])),
                    ft.DataCell(ft.Text(item["name"])),
                    ft.DataCell(ft.Text(str(item["qty"]))),
                    ft.DataCell(ft.Text("$ "+str(item["cost"]))),
                    ft.DataCell(ft.Text("$ "+str(round(item["qty"] * item["cost"], 2)))),
                    ft.DataCell(
                        ft.IconButton(
                            ft.Icons.CLOSE,
                            icon_size=18,
                            icon_color=ft.Colors.ERROR,
                            tooltip="Remove",
                            on_click=lambda e, i=idx: self.remove_item_from_po(i),
                        )
                    ),
                ]
            )
            for idx, item in enumerate(self.current_po_items)
        ]

        self.po_items_total.value = f"$ {sum(r['qty'] * r['cost'] for r in self.current_po_items):.4f}"
        self.po_items_total.update()

        self.po_items_placeholder.visible = not self.current_po_items
        self.po_items_list.update()
        # Visual cleanup: update the modal to reflect changes in controls
        self.create_po_modal.update()

    def remove_item_from_po(self, index):
        self.current_po_items.pop(index)
        self.refresh_po_items_preview()

    def handle_paste_excel(self, e):
        self.paste_panel.visible = True
        text = ""
        clipboard_read = False
        try:
            import pyperclip
            text = pyperclip.paste() or ""
            clipboard_read = True
        except Exception:
            pass

        self.paste_field.value = text.strip()
        if text.strip():
            self.paste_status.value = "Clipboard loaded. Review then press 'Add to Order'."
            self.paste_status.color = ft.Colors.GREEN
        elif clipboard_read:
            self.paste_status.value = (
                "Clipboard is empty or has no text — Ctrl+V into the box, then 'Add to Order'."
            )
            self.paste_status.color = ft.Colors.ERROR
        else:
            self.paste_status.value = (
                "Could not read the clipboard — Ctrl+V into the box, then 'Add to Order'."
            )
            self.paste_status.color = ft.Colors.ERROR
        self.create_po_modal.update()

    def add_pasted_items(self, e):
        rows, problems = parse_pasted_rows(self.paste_field.value or "")

        self.paste_panel.visible = False

        if not rows:
            self.paste_status.value = (
                "Nothing to add. " + ("; ".join(problems[:3]) if problems else "No valid rows found.")
            )
            self.paste_status.color = ft.Colors.ERROR
            self.paste_status.update()
            self.create_po_modal.update()
            return

        with DatabaseManager() as db:
            db_items = db.fetch_all(
                "SELECT item_id, item_code, item_name FROM items"
            )
        by_code = {it["item_code"]: it for it in db_items}
        by_code_lower = {it["item_code"].lower(): it for it in db_items}

        added = 0
        unknown: list[str] = []
        by_id: dict[int, dict] = {}
        for code, qty, cost in rows:
            item = by_code.get(code) or by_code_lower.get(code.lower())
            if item is None:
                unknown.append(code)
                continue
            item_id = item["item_id"]
            if item_id in by_id:
                by_id[item_id]["qty"] += qty
                by_id[item_id]["cost"] = cost
            else:
                by_id[item_id] = {
                    "item_id": item_id,
                    "code": item["item_code"],
                    "name": item["item_name"],
                    "qty": qty,
                    "cost": cost,
                }
            added += 1

        self.current_po_items.extend(by_id.values())
        self.refresh_po_items_preview()

        messages: list[str] = [f"Added {added} row(s)."]
        if unknown:
            messages.append(f"Unknown codes: {', '.join(sorted(set(unknown)))}")
        if problems:
            messages.append("; ".join(problems[:3]))
        if len(problems) > 3:
            messages.append(f"...and {len(problems) - 3} more problem line(s).")
        self.paste_status.value = " ".join(messages)
        self.paste_status.color = ft.Colors.ERROR if (unknown or problems) else ft.Colors.GREEN
        self.paste_status.update()
        self.create_po_modal.update()

    def clear_paste(self, e):
        self.paste_field.value = ""
        self.paste_status.value = ""
        self.paste_panel.visible = False
        self.create_po_modal.update()

    # --- Searchable item picker (like the item-details page) ---
    def build_item_suggestion_tiles(self, items: list[Item]) -> list[ft.ListTile]:
        return [
            ft.ListTile(
                leading=ft.Icon(ft.Icons.INVENTORY_2_OUTLINED),
                title=ft.Text(f"{item.code} - {item.name}"),
                data=item.id,
                on_click=self.handle_item_select,
            )
            for item in items
        ]

    def update_item_suggestions(self, query: str):
        query = (query or "").strip().lower()
        if not query:
            matches = self.items
        else:
            matches = [
                item
                for item in self.items
                if query in item.code.lower() or query in item.name.lower()
            ]
        self.item_search.controls = self.build_item_suggestion_tiles(
            matches[:SEARCH_SUGGESTION_LIMIT]
        )

    def handle_item_search_change(self, e: ft.Event[ft.SearchBar]):
        self.update_item_suggestions(e.control.value)
        self.item_search.update()

    async def handle_item_search_tap(self, e: ft.Event[ft.SearchBar]):
        self.update_item_suggestions(self.item_search.value)
        self.item_search.update()
        await self.item_search.open_view()

    async def handle_item_search_submit(self, e: ft.Event[ft.SearchBar]):
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

    async def handle_item_select(self, e: ft.Event[ft.ListTile]):
        await self.select_item_by_id(e.control.data)

    async def select_item_by_id(self, item_id: int):
        item = next((item for item in self.items if item.id == item_id), None)
        if item is None:
            return
        self.selected_item_id = item.id
        self.item_search.value = f"{item.code} - {item.name}"
        self.item_search.update()
        await self.item_search.close_view(self.item_search.value)

    def save_po(self, e):
        if not self.po_number_field.value or not self.distributor_dropdown.value:
            return

        with DatabaseManager() as db:
            if self.selected_po_id:
                # EDIT EXISTING DRAFT
                db.execute_query(
                    "UPDATE purchase_orders SET po_number = ?, distributor_id = ? WHERE po_id = ?",
                    (self.po_number_field.value, self.distributor_dropdown.value, self.selected_po_id)
                )
                # Draft POs don't touch inventory, so we can simply replace the lines.
                db.execute_query("DELETE FROM po_items WHERE po_id = ?", (self.selected_po_id,))
                po_id = self.selected_po_id
            else:
                # CREATE NEW PO (starts as a Draft; ordered qty is reserved on 'Place Order')
                db.execute_query(
                    "INSERT INTO purchase_orders (po_number, distributor_id, status, order_date) VALUES (?, ?, 'DRAFT', NULL)",
                    (self.po_number_field.value, self.distributor_dropdown.value)
                )
                po_id = db.cur.lastrowid

            # Insert Items
            for item in self.current_po_items:
                db.execute_query(
                    "INSERT INTO po_items (po_id, item_id, quantity_ordered, unit_cost) VALUES (?, ?, ?, ?)",
                    (po_id, item["item_id"], item["qty"], item["cost"])
                )

        self.page.pop_dialog()
        self.reset_create_po_form()
        self.refresh_po_table()
    def reset_create_po_form(self):
        self.po_number_field.value = ""
        self.distributor_dropdown.value = None
        self.current_po_items = []
        self.selected_po_id = None
        
        # Reset item selection fields too
        self.selected_item_id = None
        self.item_search.value = ""
        self.qty_field.value = "1"
        self.cost_field.value = "0.0"
        self.add_item_error_text.value = ""
        self.paste_field.value = ""
        self.paste_status.value = ""
        self.paste_panel.visible = False
        
        self.refresh_po_items_preview()
        # Force update all form fields to clear visual state
        self.po_number_field.update()
        self.distributor_dropdown.update()
        self.item_search.update()
        self.qty_field.update()
        self.cost_field.update()

    def open_po_editor(self, po: PurchaseOrder):
        self.selected_po_id = po.id
        self.po_number_field.value = po.po_number
        self.distributor_dropdown.value = str(po.distributor_id)
        
        # Load existing items
        with DatabaseManager() as db:
            db_items = db.fetch_all("""
                SELECT pi.item_id, i.item_name, i.item_code, pi.quantity_ordered, pi.unit_cost 
                FROM po_items pi 
                JOIN items i ON pi.item_id = i.item_id 
                WHERE pi.po_id = ?
            """, (po.id,))
            self.current_po_items = [
                {"item_id": item["item_id"], "code": item["item_code"], "name": item["item_name"], "qty": item["quantity_ordered"], "cost": item["unit_cost"]}
                for item in db_items
            ]

        self.paste_field.value = ""
        self.paste_status.value = ""
        self.paste_panel.visible = False
        self.view_po_total.value =  "" 

        self.page.show_dialog(self.create_po_modal)
        self.refresh_po_items_preview()

    def open_po_viewer(self, po: PurchaseOrder):
        self.view_po_number.value = po.po_number
        self.view_po_distributor.value = po.distributor_name
        self.view_po_date.value = po.order_date or "—"
        self.view_po_status.value = po.status
        self.view_po_status.color = ft.Colors.GREEN if po.status == "ORDERED" else ft.Colors.GREY

        with DatabaseManager() as db:
            rows = db.fetch_all("""
                SELECT pi.item_id, i.item_name, i.item_code, pi.quantity_ordered, pi.unit_cost
                FROM po_items pi
                JOIN items i ON pi.item_id = i.item_id
                WHERE pi.po_id = ?
            """, (po.id,))

        self.view_po_table.rows = [
            fdt.DataRow2(
                cells=[
                    ft.DataCell(ft.Text(r["item_code"])),
                    ft.DataCell(ft.Text(r["item_name"])),
                    ft.DataCell(ft.Text(str(r["quantity_ordered"]))),
                    ft.DataCell(ft.Text("$ "+str(r["unit_cost"]))),
                    ft.DataCell(ft.Text("$ "+str(round(r["quantity_ordered"] * r["unit_cost"], 2)))),
                ]
            )
            for r in rows
        ]
        self.view_po_total.value = f"$ {sum(r['quantity_ordered'] * r['unit_cost'] for r in rows):.4f}"

        self.page.show_dialog(self.view_po_modal)


    def mark_po_ordered(self, po: PurchaseOrder):
        with DatabaseManager() as db:
            # Reserve ordered quantity once the order is actually placed.
            items = db.fetch_all(
                "SELECT item_id, quantity_ordered FROM po_items WHERE po_id = ?", (po.id,)
            )
            for item in items:
                db.execute_query(
                    "UPDATE inventory SET quantity_ordered = quantity_ordered + ? WHERE item_id = ?",
                    (item["quantity_ordered"], item["item_id"]),
                )
            db.execute_query(
                "UPDATE purchase_orders SET status = 'ORDERED', order_date = COALESCE(order_date, CURRENT_TIMESTAMP) WHERE po_id = ?",
                (po.id,),
            )
        self.refresh_po_table()

    def revert_po_to_draft(self, po: PurchaseOrder):
        with DatabaseManager() as db:
            # Release the reserved ordered quantity back out.
            items = db.fetch_all(
                "SELECT item_id, quantity_ordered FROM po_items WHERE po_id = ?", (po.id,)
            )
            for item in items:
                db.execute_query(
                    "UPDATE inventory SET quantity_ordered = MAX(0, quantity_ordered - ?) WHERE item_id = ?",
                    (item["quantity_ordered"], item["item_id"]),
                )
            db.execute_query(
                "UPDATE purchase_orders SET status = 'DRAFT', order_date = NULL WHERE po_id = ?",
                (po.id,),
            )
        self.refresh_po_table()

    def delete_po(self, po: PurchaseOrder):
        with DatabaseManager() as db:
            # Reverse the reserved ordered quantity (only meaningful for ORDERED POs).
            items = db.fetch_all("SELECT item_id, quantity_ordered FROM po_items WHERE po_id = ?", (po.id,))
            for item in items:
                db.execute_query("UPDATE inventory SET quantity_ordered = MAX(0, quantity_ordered - ?) WHERE item_id = ?", (item["quantity_ordered"], item["item_id"]))

            # Delete PO items first (even if CASCADE is on, explicitly doing it is safer if constraints differ)
            db.execute_query("DELETE FROM po_items WHERE po_id = ?", (po.id,))
            db.execute_query("DELETE FROM purchase_orders WHERE po_id = ?", (po.id,))

        self.refresh_po_table()
    def handle_sort(self, e: ft.DataColumnSortEvent):
        # Simplified sort for POs
        sorters = [
            lambda p: p.po_number,
            lambda p: p.distributor_name,
            lambda p: p.status,
            lambda p: p.order_date,
        ]
        if e.column_index < len(sorters):
            self.pos.sort(key=sorters[e.column_index], reverse=not e.ascending)
            self.po_table.sort_column_index = e.column_index
            self.po_table.sort_ascending = e.ascending
            self.po_table.rows = self.build_po_rows()
            self.po_table.update()
