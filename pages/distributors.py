
import sqlite3

from constants import DB_PATH
from database import DatabaseManager
import flet as ft

@ft.control
class DistributorsPage(ft.Container):
    def __init__(self):
        super().__init__()
        self.expand = True

        self.about_to_delete_id: int | None = None
        self.create_distributor_name = ""
        self.status = ft.Text()

        self.confirm_delete_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Are you sure?"),
            content=ft.Text("This will delete the distributor"),
            alignment=ft.Alignment.CENTER,
            actions = [
                ft.Button("Yes", on_click=self.handle_delete),
                ft.Button("No", on_click=lambda e: self.page.pop_dialog())
            ]
        )

        self.view_table = ft.DataTable(
            align=ft.Alignment.TOP_LEFT,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
            expand=True,
            columns=[
                ft.DataColumn(label=ft.Text("ID")),
                ft.DataColumn(label=ft.Text("Name")),
                ft.DataColumn(label=ft.Text("Created at")),
                ft.DataColumn(label=ft.Text("Delete")),
            ],
            rows=self.build_distributors_view(),
        )

        self.create_text_field = ft.TextField(
            label="Name", 
            border_color=ft.Colors.BLUE_ACCENT_400,
            on_change=self.handle_create_name_change,
            on_submit=self.handle_create
        ) 
        self.create_container = ft.Container(
            expand=True, 
            content=ft.Column(
                expand=True,
                controls=[
                    ft.Text("Create Distributor"),
                    self.create_text_field,
                    self.status,
                    ft.Button("Create", on_click=self.handle_create)
                ]
            )
        )

        self.content = ft.Row(
            expand=True,
            controls=[
                self.view_table,
                ft.VerticalDivider(),
                self.create_container
            ]
        )

    def handle_create_name_change(self, e: ft.Event[ft.TextField]):
        self.create_distributor_name = e.control.value

    def handle_create(self):
        if not self.create_distributor_name: return

        try:
            with DatabaseManager(DB_PATH) as db:
                db.execute_query("INSERT INTO distributors ( name ) VALUES ( ? )", ( self.create_distributor_name, ) )

                self.status.value = f"Created {self.create_distributor_name}"
                self.status.color = ft.Colors.GREEN
                self.create_text_field.value = ""
                self.create_distributor_name = ""

                self.update()
                print("Distributor Crated")
        except sqlite3.Error as er:
            self.status.value = f"Error: {er}"
            self.status.color = ft.Colors.ERROR
            self.update()
            print(f"🗃️ General SQLite error: {er}")

        self.refresh_distributors_list()

    def handle_delete(self, e: ft.Event[ft.Button]):
        if self.about_to_delete_id is None: return

        self.page.pop_dialog()

        try:
            with DatabaseManager(DB_PATH) as db:
                db.execute_query("DELETE FROM distributors WHERE distributor_id = ?", ( self.about_to_delete_id, ) )

                self.status.value = f"Distributor Deleted"
                self.status.color = ft.Colors.GREEN
                self.update()
                print("Distributor Deleted")

        except sqlite3.Error as er:
            self.status.value = f"Error: {er}"
            self.status.color = ft.Colors.ERROR
            self.update()
            print(f"SQLite error: {er}")

        self.refresh_distributors_list()
            
    def refresh_distributors_list(self):
        self.view_table.rows = self.build_distributors_view()
        self.update()

    def about_to_delete(self, distro_id: int):
        self.about_to_delete_id = distro_id 
        self.page.show_dialog(self.confirm_delete_dialog)

    def build_distributors_view(self) -> list[ft.DataRow]:
        distros = []
        with DatabaseManager(DB_PATH) as db:
            distros = db.fetch_all("SELECT * FROM distributors")

        return [
            ft.DataRow(
                cells=[
                    ft.DataCell(ft.Text(distro["distributor_id"])),
                    ft.DataCell(ft.Text(distro["name"])),
                    ft.DataCell(ft.Text(distro["created_at"])),
                    ft.DataCell(
                        ft.IconButton(icon=ft.Icons.DELETE, on_click=lambda e, i=distro["distributor_id"]: self.about_to_delete(i))
                    ),
                ]
            )
            for distro in distros
        ] 





