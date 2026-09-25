"""Browser-style tabs for the Jouduto shell.

Each tab is a full independent "app instance": it has its own fiscal YEAR, its
own Home page and its own navigation stack (route, title, page control), so
scrolling, selection, search, sort and year state are all per-tab. The shell
below is the whole app's window: [TabStrip, Divider, ContentArea].

Because the rest of the app reads the active year through the module-global
`appstate`, the shell keeps that global in sync with the ACTIVE tab's year
(before rendering and before navigating/constructing pages). Switched-away
tabs keep their own year and their own constructed pages; only lazy DB reads
happen under the active tab's year context.

Pages keep calling `page.navigate(...)`; `main.py` wires `on_route_change`
into `AppShell.navigate` which steers the route into the ACTIVE tab's stack.

This module has no imports from pages/ (home pages and route types are
injected as callbacks/lookups), so there is no import cycle.
"""

import urllib.parse

import flet as ft

import appstate


class Tab:
    """One browser tab: its own fiscal year + navigation stack."""

    def __init__(self, shell: "AppShell", tab_id: int, year: int, home: ft.Control):
        self.shell = shell
        self.id = tab_id
        self.year = year
        self.home = home
        self.stack: list[tuple[str, str, ft.Control]] = [("/", "Home", home)]

    @property
    def title(self) -> str:
        return self.stack[-1][1]

    @property
    def label(self) -> str:
        """Chip text: current page title plus the tab's fiscal year."""
        return f"{self.title} · {self.year}"

    @staticmethod
    def base_route(route: str) -> str:
        return route.split("?", 1)[0]

    def navigate(self, route: str) -> None:
        """Apply a route to THIS tab's stack (mirrors the old single-stack
        route_change logic, but confined to this tab)."""
        base = self.base_route(route)

        if base == "/":
            self.stack = [("/", "Home", self.home)]
            return

        current = self.shell.pages_by_route.get(base)
        if current is None:
            return

        if base == "/item-details":
            # Keep the layers beneath (e.g. Items) so backing out restores them.
            prefix = [e for e in self.stack if self.base_route(e[0]) != "/item-details"]
            if not prefix or all(self.base_route(e[0]) == "/" for e in prefix):
                prefix = [("/", "Home", self.home)]

            content = current.page_type()
            query = urllib.parse.parse_qs(route.split("?", 1)[1]) if "?" in route else {}
            item_param = query.get("item")
            if item_param:
                try:
                    content.open_focused_item(int(item_param[0]))
                except ValueError:
                    pass

            self.stack = prefix + [(route, current.title, content)]
            return

        # Regular section page: [Home, Section]. Reuse a section already open
        # in this tab so its state survives a round-trip.
        existing = next(
            (e for e in self.stack if self.base_route(e[0]) == base),
            None,
        )
        if existing is None:
            existing = (base, current.title, current.page_type())
        self.stack = [("/", "Home", self.home), existing]

    def back(self) -> None:
        if len(self.stack) > 1:
            self.stack.pop()


class AppShell:
    """The tabbed app window: strip + content area, N independent tabs."""

    def __init__(
        self,
        *,
        page: ft.Page,
        pages_by_route: dict,
        make_home,
        on_active_tab_changed=None,
    ):
        self.page = page
        self.pages_by_route = pages_by_route
        self.make_home = make_home
        self.on_active_tab_changed = on_active_tab_changed

        self.tabs: list[Tab] = []
        self.active_tab_id: int | None = None
        self._next_tab_id = 1

        self.strip_chips = ft.Row(spacing=6, scroll=ft.ScrollMode.HIDDEN, expand=True)
        self.add_button = ft.IconButton(
            icon=ft.Icons.ADD,
            tooltip="New tab",
            on_click=lambda e: self.add_tab(),
        )
        self.strip = ft.Container(
            content=ft.Row(
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[self.strip_chips, self.add_button],
            ),
            padding=ft.Padding.symmetric(horizontal=6, vertical=2),
            bgcolor=ft.Colors.SURFACE_CONTAINER_LOWEST,
        )
        self.content_area = ft.Container(expand=True, padding=0)
        self.root_view = ft.View(
            route="/",
            controls=[
                self.strip,
                ft.Divider(height=1),
                ft.SafeArea(expand=True, content=self.content_area),
            ],
        )

        self.add_tab()

    # ------------------------------------------------------------------
    # Tab management
    # ------------------------------------------------------------------
    def _tab(self, tab_id: int | None = None) -> Tab | None:
        tid = tab_id if tab_id is not None else self.active_tab_id
        return next((t for t in self.tabs if t.id == tid), None)

    def _new_tab_year(self) -> int:
        """A new tab inherits its year from the tab it is opened from."""
        active = self._tab()
        if active is not None:
            return active.year
        return appstate.get_active_year()

    def add_tab(self, e: ft.Event[ft.IconButton] = None) -> Tab:
        year = self._new_tab_year()
        appstate.set_active_year(year)  # context for HomePage construction
        tab = Tab(self, self._next_tab_id, year, self.make_home())
        self._next_tab_id += 1
        self.tabs.append(tab)
        self.active_tab_id = tab.id
        self.render()
        self._notify_active_tab_changed()
        return tab

    def close_tab(self, tab_id: int) -> None:
        if len(self.tabs) <= 1:
            # Closing the last tab spawns a fresh Home tab (browser behavior),
            # inheriting the just-closed tab's year.
            appstate.set_active_year(self._tab().year if self._tab() else appstate.get_active_year())
            self.tabs = []
            self._next_tab_id += 1  # keep ids unique for a fresh session
            self.add_tab()
            return

        index = next(i for i, t in enumerate(self.tabs) if t.id == tab_id)
        self.tabs.pop(index)
        if self.active_tab_id == tab_id:
            self.active_tab_id = self.tabs[max(0, index - 1)].id
        self.render()
        self._notify_active_tab_changed()

    def switch_tab(self, tab_id: int) -> None:
        if self._tab(tab_id) is not None:
            self.active_tab_id = tab_id
            self.render()
            self._notify_active_tab_changed()

    def navigate(self, route: str) -> None:
        tab = self._tab()
        if tab is not None:
            appstate.set_active_year(tab.year)  # context for page constructors
            tab.navigate(route)
            self.render()

    def back(self) -> None:
        tab = self._tab()
        if tab is not None:
            tab.back()
            self.render()

    def change_year_for_active_tab(self, year: int) -> None:
        """Re-point ONLY the active tab at a different fiscal year."""
        tab = self._tab()
        if tab is None:
            return
        tab.year = year
        appstate.set_active_year(year)  # context for the fresh Home build
        tab.home = self.make_home()
        tab.stack = [("/", "Home", tab.home)]
        self.render()
        self._notify_active_tab_changed()

    def _notify_active_tab_changed(self) -> None:
        tab = self._tab()
        if tab is not None and self.on_active_tab_changed is not None:
            self.on_active_tab_changed(tab)

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------
    def render(self) -> None:
        tab = self._tab()
        if tab is not None:
            # DB reads from this tab's pages must target this tab's year.
            appstate.set_active_year(tab.year)

        self.strip_chips.controls = [
            self._make_chip(t, active=(t.id == self.active_tab_id))
            for t in self.tabs
        ]

        if tab is not None:
            self.content_area.content = self._make_page(tab)

        self.page.update()

    def _make_chip(self, tab: Tab, active: bool) -> ft.Container:
        return ft.Container(
            content=ft.Row(
                tight=True,
                spacing=2,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Text(
                        tab.label,
                        size=13,
                        weight=ft.FontWeight.W_600 if active else ft.FontWeight.W_400,
                    ),
                    ft.IconButton(
                        icon=ft.Icons.CLOSE,
                        icon_size=14,
                        tooltip="Close tab",
                        on_click=lambda e, t=tab.id: self.close_tab(t),
                    ),
                ],
            ),
            padding=ft.Padding.symmetric(horizontal=10, vertical=2),
            border_radius=10,
            bgcolor=(
                ft.Colors.with_opacity(0.18, ft.Colors.PRIMARY)
                if active
                else ft.Colors.with_opacity(0.05, ft.Colors.ON_SURFACE)
            ),
            on_click=lambda e, t=tab.id: self.switch_tab(t),
            ink=True,
            tooltip=f"Switch to {tab.label}",
        )

    def _make_page(self, tab: Tab) -> ft.Column:
        route, title, content = tab.stack[-1]
        depth = len(tab.stack)

        header_controls: list[ft.Control] = []
        if depth > 1:
            header_controls.append(
                ft.IconButton(
                    icon=ft.Icons.ARROW_BACK,
                    tooltip="Back",
                    on_click=lambda e: self.back(),
                )
            )
        header_controls.append(
            ft.Text(
                title,
                italic=True,
                weight=ft.FontWeight.W_900,
                theme_style=ft.TextThemeStyle.TITLE_LARGE,
                expand=True,
            )
        )
        year = tab.year
        header_controls.append(
            ft.Container(
                content=ft.Text(
                    str(year),
                    weight=ft.FontWeight.BOLD,
                    size=20,
                ),
                tooltip=f"Active fiscal year: {year}",
            )
        )

        return ft.Column(
            expand=True,
            spacing=0,
            controls=[
                ft.Container(
                    height=50,
                    bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                    border_radius=ft.BorderRadius.all(10),
                    padding=ft.Padding.symmetric(horizontal=20),
                    margin=ft.Margin(bottom=8),
                    content=ft.Row(
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=header_controls,
                    ),
                ),
                ft.SafeArea(expand=True, content=content),
            ],
        )
