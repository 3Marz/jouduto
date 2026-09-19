import flet as ft

from appstate import get_active_year, get_years

@ft.control
class HomePage(ft.Container):
    def __init__(self, on_year_change=None):
        super().__init__()
        self.expand = True
        self.on_year_change = on_year_change or (lambda year: None)

        self.year_caption = ft.Text(
            f"Working in {get_active_year()}",
            theme_style=ft.TextThemeStyle.TITLE_MEDIUM,
        )
        self.year_dropdown = ft.Dropdown(
            width=140,
            label="Year",
            value=str(get_active_year()),
            options=[
                ft.DropdownOption(key=str(year), text=str(year))
                for year in get_years()
            ],
            on_select=self.handle_year_change,
        )

        self.content = ft.Column(
            expand=True,
            controls=[
                ft.Text("Home Page", size=30, weight=ft.FontWeight.BOLD),
                ft.Row(
                    spacing=12,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        self.year_dropdown,
                        self.year_caption,
                    ],
                ),
            ],
        )

    def handle_year_change(self, e: ft.Event[ft.Dropdown]):
        try:
            year = int(e.control.value)
        except (TypeError, ValueError):
            return
        self.year_caption.value = f"Working in {year}"
        self.on_year_change(year)
        self.year_caption.update()