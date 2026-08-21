
from constants import DB_PATH
from database import DatabaseManager
import flet as ft

@ft.control
class DistributorsPage(ft.Container):
    def __init__(self):
        super().__init__()
        self.expand = True

        self.create_distributor_name = ""

        self.viewContainer = ft.ListView(expand=True, controls=self.build_distributors_view())
        self.createContainer = ft.Container(
            expand=True, 
            content=ft.Column(
                expand=True,
                controls=[
                    ft.Text("Create Distributor"),
                    ft.TextField(
                        label="Name", 
                        border_color=ft.Colors.BLUE_ACCENT_400,
                        on_change=self.handle_create_name_change
                    ),
                    ft.Button("Create", on_click=self.handle_create)
                ]
            )
        )

        self.content = ft.Row(
            controls=[
                self.viewContainer,
                ft.VerticalDivider(),
                self.createContainer
            ]
        )

    def handle_create_name_change(self, e: ft.Event[ft.TextField]):
        self.create_distributor_name = e.control.value

    def handle_create(self, e: ft.Event[ft.Button]):
        if not self.create_distributor_name: return

        with DatabaseManager(DB_PATH) as db:
            db.execute_query("INSERT INTO distributors ( name ) VALUES ( ? )", ( self.create_distributor_name, ) )
            print("Distributor Crated")
        self.refresh_distributors_list()

            
    def refresh_distributors_list(self):
        self.viewContainer = ft.ListView(
            controls=self.build_distributors_view()
        )
        self.update()

    def build_distributors_view(self):
        distros = []
        with DatabaseManager(DB_PATH) as db:
            distros = db.fetch_all("SELECT * FROM distributors")
            print(distros)

        return [
            ft.Text(f"{i["name"]}") for i in distros
        ] 





