import sqlite3
from typing import Tuple

from database import DatabaseManager

import flet as ft
import flet_datatable2 as fdt
import pandas as pd

from datatypes import Inventory, Item, Distributor, PurchaseOrder

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
        self.distributor_dropdown = ft.Dropdown(
            label="Select Distributor",
            options=[
                ft.DropdownOption(key=str(d["distributor_id"]), text=d["distributor_name"])
                for d in self.get_distributors()
            ]
        )
        self.po_number_field = ft.TextField(label="PO Number")
        
        # Item Selection for New PO
        self.item_dropdown = ft.Dropdown(
            label="Select Item",
            expand=True,
            options=[
                ft.DropdownOption(key=str(i.id), text=f"{i.code} - {i.name}")
                for i in self.get_items_list()
            ]
        )
        self.qty_field = ft.TextField(label="Qty", width=100, value="1")
        self.cost_field = ft.TextField(label="Unit Cost", width=120, value="0.0")
        
        self.po_items_list = ft.Column(spacing=10, scroll=ft.ScrollMode.AUTO, height=200)
        self.current_po_items: list[dict] = []
        self.add_item_error_text = ft.Text("", color=ft.Colors.ERROR)

        def add_item_to_po(e):
            self.add_item_error_text.value = ""
            if not self.item_dropdown.value:
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
            item = next(i for i in self.get_items_list() if str(i.id) == self.item_dropdown.value)
            self.current_po_items.append({
                "item_id": item.id,
                "code": item.code,
                "name": item.name,
                "qty": qty,
                "cost": cost
            })
            self.refresh_po_items_preview()

        self.add_item_btn = ft.IconButton(icon=ft.Icons.ADD_CIRCLE, on_click=add_item_to_po)

        self.create_po_modal = ft.AlertDialog(
            title=ft.Text("Purchase Order"),
            content=ft.Column([
                self.po_number_field,
                self.distributor_dropdown,
                ft.Divider(),
                ft.Text("Items", weight=ft.FontWeight.BOLD),
                ft.Row([self.item_dropdown, self.qty_field, self.cost_field, self.add_item_btn]),
                self.add_item_error_text,
                self.po_items_list,
            ], tight=True, width=600),
            actions=[
                ft.TextButton("Cancel", on_click=lambda _: self.page.pop_dialog()),
                ft.ElevatedButton("Save PO", on_click=self.save_po),
            ]
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

    def get_distributors(self):
        with DatabaseManager() as db:
            return db.fetch_all("SELECT * FROM distributors")

    def get_items_list(self):
        with DatabaseManager() as db:
            db_items = db.fetch_all("SELECT * FROM items")
            return [Item(itm["item_id"], itm["item_code"], itm["item_name"]) for itm in db_items]

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
                    ft.DataCell(ft.Text(po.status)),
                    ft.DataCell(ft.Text(po.order_date)),
                    ft.DataCell(ft.Row([
                        ft.IconButton(ft.Icons.EDIT, tooltip="Edit", on_click=lambda e, p=po: self.open_po_editor(p)),
                        ft.IconButton(ft.Icons.CHECK_CIRCLE, icon_color="green", tooltip="Receive", on_click=lambda e, p=po: self.receive_po(p)),
                        ft.IconButton(ft.Icons.DELETE, icon_color="red", tooltip="Delete", on_click=lambda e, p=po: self.delete_po(p)),
                    ])),
                ]
            ) for po in self.pos
        ]

    def refresh_po_items_preview(self):
        self.po_items_list.controls = [
            ft.Row([
                ft.Text(f"{item['code']} - {item['name']} x{item['qty']} @ {item['cost']}"),
                ft.IconButton(ft.Icons.CLOSE, on_click=lambda e, i=idx: self.remove_item_from_po(i))
            ]) for idx, item in enumerate(self.current_po_items)
        ]
        self.po_items_list.update()
        # Visual cleanup: update the modal to reflect changes in controls
        self.create_po_modal.update()

    def remove_item_from_po(self, index):
        self.current_po_items.pop(index)
        self.refresh_po_items_preview()

    def save_po(self, e):
        if not self.po_number_field.value or not self.distributor_dropdown.value:
            return

        with DatabaseManager() as db:
            if self.selected_po_id:
                # EDIT EXISTING PO
                db.execute_query(
                    "UPDATE purchase_orders SET po_number = ?, distributor_id = ? WHERE po_id = ?",
                    (self.po_number_field.value, self.distributor_dropdown.value, self.selected_po_id)
                )
                # To simplify item editing, we remove old items and re-insert them
                # IMPORTANT: We must reverse the inventory order count first
                old_items = db.fetch_all("SELECT item_id, quantity_ordered FROM po_items WHERE po_id = ?", (self.selected_po_id,))
                for old in old_items:
                    db.execute_query("UPDATE inventory SET quantity_ordered = quantity_ordered - ? WHERE item_id = ?", (old["quantity_ordered"], old["item_id"]))
                
                db.execute_query("DELETE FROM po_items WHERE po_id = ?", (self.selected_po_id,))
                po_id = self.selected_po_id
            else:
                # CREATE NEW PO
                db.execute_query(
                    "INSERT INTO purchase_orders (po_number, distributor_id, status) VALUES (?, ?, 'ORDERED')",
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
        self.pos = self.get_pos_data()
        self.po_table.rows = self.build_po_rows()
        self.po_table.update()
    def reset_create_po_form(self):
        self.po_number_field.value = ""
        self.distributor_dropdown.value = None
        self.current_po_items = []
        self.selected_po_id = None
        
        # Reset item selection fields too
        self.item_dropdown.value = None
        self.qty_field.value = "1"
        self.cost_field.value = "0.0"
        self.add_item_error_text.value = ""
        
        self.refresh_po_items_preview()
        # Force update all form fields to clear visual state
        self.po_number_field.update()
        self.distributor_dropdown.update()
        self.item_dropdown.update()
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
        
        self.page.show_dialog(self.create_po_modal)
        self.refresh_po_items_preview()

    def receive_po(self, po: PurchaseOrder):
        with DatabaseManager() as db:
            # 1. Update PO status
            db.execute_query("UPDATE purchase_orders SET status = 'RECEIVED', received_date = CURRENT_TIMESTAMP WHERE po_id = ?", (po.id,))
            
            # 2. Fetch items and move quantity_ordered -> quantity_available
            items = db.fetch_all("SELECT item_id, quantity_ordered FROM po_items WHERE po_id = ?", (po.id,))
            for item in items:
                # Update inventory: add to available, subtract from ordered
                db.execute_query("""
                    UPDATE inventory 
                    SET quantity_available = quantity_available + ?, 
                        quantity_ordered = quantity_ordered - ? 
                    WHERE item_id = ?
                """, (item["quantity_ordered"], item["quantity_ordered"], item["item_id"]))

        self.pos = self.get_pos_data()
        self.po_table.rows = self.build_po_rows()
        self.po_table.update()

    def delete_po(self, po: PurchaseOrder):
        with DatabaseManager() as db:
            # Note: Trigger only handles INSERT. We must manually reverse quantity_ordered on delete.
            items = db.fetch_all("SELECT item_id, quantity_ordered FROM po_items WHERE po_id = ?", (po.id,))
            for item in items:
                db.execute_query("UPDATE inventory SET quantity_ordered = quantity_ordered - ? WHERE item_id = ?", (item["quantity_ordered"], item["item_id"]))

            # Delete PO items first (even if CASCADE is on, explicitly doing it is safer if constraints differ)
            db.execute_query("DELETE FROM po_items WHERE po_id = ?", (po.id,))
            db.execute_query("DELETE FROM purchase_orders WHERE po_id = ?", (po.id,))

        self.pos = self.get_pos_data()
        self.po_table.rows = self.build_po_rows()
        self.po_table.update()
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
