import flet as ft

from appstate import get_active_year, get_years
from database import get_dashboard_stats


def _fmt(n: int) -> str:
    """Format a large number for compact display (e.g. 797401 -> '797K')."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def _make_stat_ring(label: str, value: int, color: ft.Colors, max_val: int = 1) -> ft.Container:
    """A circular stat card with a ProgressRing + bold count + label."""
    ratio = min(value / max_val, 1.0) if max_val else 0
    return ft.Container(
        content=ft.Column(
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            alignment=ft.MainAxisAlignment.CENTER,
            controls=[
                ft.ProgressRing(
                    value=ratio,
                    width=60,
                    height=60,
                    stroke_width=8,
                    color=color,
                    bgcolor=ft.Colors.with_opacity(0.15, color),
                ),
                ft.Text(
                    _fmt(value),
                    size=20,
                    weight=ft.FontWeight.BOLD,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Text(
                    label,
                    size=11,
                    color=ft.Colors.with_opacity(0.7, ft.Colors.ON_SURFACE),
                    text_align=ft.TextAlign.CENTER,
                ),
            ],
            spacing=4,
        ),
        alignment=ft.Alignment(0, 0),
        width=120,
        padding=ft.Padding.symmetric(vertical=12),
    )


def _make_health_bar(label: str, value: int, color: ft.Colors, max_val: int) -> ft.Row:
    """A single horizontal bar row: label + ProgressBar + count."""
    ratio = min(value / max_val, 1.0) if max_val else 0
    return ft.Row(
        controls=[
            ft.Text(label, size=12, width=90, color=ft.Colors.with_opacity(0.7, ft.Colors.ON_SURFACE)),
            ft.ProgressBar(
                value=ratio,
                expand=True,
                color=color,
                bgcolor=ft.Colors.with_opacity(0.12, color),
                bar_height=12,
                border_radius=6,
            ),
            ft.Text(_fmt(value), size=12, weight=ft.FontWeight.W_500, width=60, text_align=ft.TextAlign.RIGHT),
        ],
        spacing=8,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )


@ft.control
class HomePage(ft.Container):
    def __init__(self, on_year_change=None, on_navigate=None):
        super().__init__()
        self.expand = True
        self.on_year_change = on_year_change or (lambda year: None)
        self.on_navigate = on_navigate or (lambda route: None)

        # Year selector
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

        # Dashboard stats
        stats = get_dashboard_stats()
        total_inventory = max(stats["total_available"] + stats["total_ordered"] + stats["total_sold"], 1)

        # Stat rings row
        stat_rings = ft.Row(
            alignment=ft.MainAxisAlignment.SPACE_EVENLY,
            controls=[
                _make_stat_ring("Items", stats["total_items"], ft.Colors.PRIMARY),
                _make_stat_ring("Available", stats["total_available"], ft.Colors.GREEN, total_inventory),
                _make_stat_ring("Low Stock", stats["low_stock"], ft.Colors.AMBER_600, stats["total_items"]),
                _make_stat_ring("Out of Stock", stats["out_of_stock"], ft.Colors.RED, stats["total_items"]),
                _make_stat_ring("Active POs", stats["active_pos"], ft.Colors.TEAL),
            ],
        )

        # Stock health bars
        stock_bars = ft.Column(
            spacing=6,
            controls=[
                ft.Text("Stock Health", size=14, weight=ft.FontWeight.W_600),
                _make_health_bar("Available", stats["total_available"], ft.Colors.GREEN, total_inventory),
                _make_health_bar("Sold", stats["total_sold"], ft.Colors.BLUE, total_inventory),
                _make_health_bar("Ordered", stats["total_ordered"], ft.Colors.ORANGE, total_inventory),
            ],
        )

        # Navigation section: big square cards
        nav_cards = ft.Row(
            wrap=True,
            alignment=ft.MainAxisAlignment.SPACE_EVENLY,
            controls=[
                self._make_nav_card("Items", ft.Icons.INVENTORY_2_OUTLINED, "/items"),
                self._make_nav_card("Item Details", ft.Icons.SEARCH, "/item-details"),
                self._make_nav_card("Distributors", ft.Icons.BUSINESS_OUTLINED, "/distributors"),
                self._make_nav_card("Purchase Orders", ft.Icons.SHOPPING_CART_CHECKOUT_OUTLINED, "/pos"),
                self._make_nav_card("Order Report", ft.Icons.ASSESSMENT_OUTLINED, "/order-report"),
            ],
        )

        self.content = ft.Column(
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            controls=[
                # Year selector row
                ft.Row(
                    margin=ft.Margin(top=12),
                    spacing=12,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        self.year_dropdown,
                        self.year_caption,
                    ],
                ),
                ft.Divider(height=1),
                # Navigation
                ft.Container(
                    content=ft.Column(
                        controls=[
                            ft.Text("Navigate", size=22, weight=ft.FontWeight.BOLD),
                            ft.Container(height=8),  # spacer
                            nav_cards,
                        ],
                        spacing=6,
                    ),
                    padding=ft.Padding.symmetric(horizontal=16, vertical=12),
                ),
                ft.Divider(height=1),
                # Dashboard
                ft.Container(
                    content=ft.Column(
                        controls=[
                            ft.Text("Dashboard", size=22, weight=ft.FontWeight.BOLD),
                            stat_rings,
                            stock_bars,
                        ],
                        spacing=14,
                    ),
                    padding=ft.Padding.symmetric(horizontal=16, vertical=8),
                ),
            ],
        )

    def _make_nav_card(self, label: str, icon: str, route: str) -> ft.Container:
        """Big square navigation card with icon + label."""
        return ft.Container(
            content=ft.Column(
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
                controls=[
                    ft.Icon(icon, size=36),
                    ft.Text(label, size=13, weight=ft.FontWeight.W_500, text_align=ft.TextAlign.CENTER),
                ],
                spacing=8,
            ),
            width=150,
            height=120,
            border_radius=16,
            bgcolor=ft.Colors.with_opacity(0.08, ft.Colors.PRIMARY),
            alignment=ft.Alignment(0, 0),
            on_click=self._nav(route),
            ink=True,
        )

    def _nav(self, route: str):
        def handler(e):
            self.on_navigate(route)
        return handler

    def handle_year_change(self, e: ft.Event[ft.Dropdown]):
        try:
            year = int(e.control.value)
        except (TypeError, ValueError):
            return
        self.on_year_change(year)
