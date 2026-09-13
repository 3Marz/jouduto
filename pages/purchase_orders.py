
import sqlite3

from database import DatabaseManager
from constants import DB_PATH

import flet as ft
import pandas as pd

from datatypes import Inventory, Item, Distributor

@ft.control
class POPage(ft.Container):
    def __init__(self):
        super().__init__()
        self.expand = True

        
        self.select_po_dialog = ft.AlertDialog(
            title=ft.Row(controls=[ft.Icon(ft.Icons.LIST), ft.Text("Select PO")]),
            content=ft.DataTable(
                columns=[
                    ft.DataColumn(label="Id"),
                    ft.DataColumn(label="Distributor"),
                    ft.DataColumn(label="Name"),
                ]
            )
        )

        self.content = ft.SafeArea(
            content=ft.Column(
                expand=True,
                controls=[
                    ft.Row(
                        controls=[
                            ft.Button(
                                "Select Purchase Order",
                                on_click=lambda e: self.page.show_dialog(self.select_po_dialog)
                            )
                        ]
                    ),
                    ft.Container(
                        content=ft.Text("ASd")
                    )
                ]
            )
        )


