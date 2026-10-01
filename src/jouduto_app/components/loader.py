"""A modal loading overlay shown while the app reaches the Turso cloud database.

Why a plain `update()` is not enough
------------------------------------
Flet runs synchronous control event handlers *inline on its own event loop*
(`base_control.py` calls `event_handler()` directly), and it flushes UI patches
from a separate task on that same loop (`flet_socket_server.py` drains a send
queue). So a handler that blocks on a network round-trip freezes the loop, and
any `update()` it performs stays queued until the handler returns -- the client
would only ever see the overlay *after* the wait it was meant to cover.

Flet has a supported way out of this. For **generator** event handlers it runs
`session.after_event()` and `await asyncio.sleep(0)` after every `yield`, which
hands the send loop a turn to flush the queued patch before the handler resumes.
That is exactly the shape needed here: make the overlay visible, `yield`, and
only then block on Turso.

So cloud work must run inside a generator handler -- see `cloud_loading`.
"""

from __future__ import annotations

import functools
import inspect
import threading
from typing import Callable, Iterator

import flet as ft

import database

DEFAULT_MESSAGE = "Syncing with the cloud database…"


class LoadingOverlay(ft.Container):
    """Full-window scrim with a spinner, stacked above the whole app.

    Sized with `left/top/right/bottom` so it covers its `ft.Stack` parent, and
    clickable so the UI underneath cannot be driven while it is up.
    """

    def __init__(self, page: ft.Page):
        super().__init__(
            visible=False,
            left=0,
            top=0,
            right=0,
            bottom=0,
            bgcolor=ft.Colors.with_opacity(0.55, ft.Colors.BLACK),
            alignment=ft.Alignment(0, 0),
            on_click=lambda e: None,
        )
        self._page = page
        # Cloud operations nest (a handler may call helpers that themselves
        # open a transaction), so the overlay is reference counted rather than
        # toggled, or an inner operation would hide it while work continues.
        self._depth = 0
        self._lock = threading.RLock()

        self.spinner = ft.ProgressRing(width=42, height=42, stroke_width=4)
        self.label = ft.Text(DEFAULT_MESSAGE, color=ft.Colors.WHITE, size=14)
        self.content = ft.Column(
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=14,
            controls=[self.spinner, self.label],
        )

    def begin(self, message: str = DEFAULT_MESSAGE) -> None:
        """Show the overlay and queue it for the client."""
        with self._lock:
            self._depth += 1
            if self._depth > 1:
                return
            self.label.value = message
            self.visible = True
        self.update()

    def end(self) -> None:
        """Hide the overlay once the outermost cloud operation finishes."""
        with self._lock:
            self._depth = max(0, self._depth - 1)
            if self._depth > 0:
                return
            self.visible = False
        # `begin()` called `update()`, which makes Flet skip its per-event
        # auto-update for the whole event. Flushing the page here restores the
        # usual "mutate controls and return" behaviour for the handler.
        self._page.update()


_active_overlay: LoadingOverlay | None = None


def set_active_overlay(overlay: LoadingOverlay | None) -> None:
    global _active_overlay
    _active_overlay = overlay


def get_active_overlay() -> LoadingOverlay | None:
    return _active_overlay


def run_handler(handler: Callable, *args) -> None:
    """Invoke an event handler exactly the way Flet does.

    `cloud_loading` returns a generator so Flet can flush the overlay before
    the handler blocks, which means the decorated handler must be *iterated*,
    not just called. Headless callers (the smoke scripts) have to do the same,
    otherwise the body never runs.
    """
    result = handler(*args)
    if inspect.isgenerator(result):
        for _ in result:
            pass


def _drive(overlay, message, blocking, call) -> Iterator[None]:
    """Run `call` with the overlay up, yielding once so Flet flushes first.

    The single `yield` is the whole trick: Flet runs `after_event()` and
    `await asyncio.sleep(0)` for every value a generator handler yields, which
    is the one moment the event loop is free enough to write the overlay patch
    to the socket before `call` blocks on Turso.
    """
    if blocking:
        overlay.begin(message)
        yield
    try:
        call()
    finally:
        if blocking:
            overlay.end()


def cloud_loading(message: str = DEFAULT_MESSAGE, *, force: bool = False) -> Callable:
    """Show the loading overlay around a cloud-bound event handler.

    The decorated function stays a plain `def`; the wrapper is what Flet sees,
    and it is a *generator* so the overlay patch is flushed before the handler
    blocks.

    `force` marks handlers that always cross the network because they write
    (the transaction end pushes) or explicitly refresh. Without it the overlay
    appears only when the handler will really need the network -- see
    `database.will_hit_network()` -- so warm local reads never flash a spinner.
    """

    def decorate(handler: Callable) -> Callable:
        # The decorator runs in the class body, where `handler` is still the
        # plain function and carries its leading `self`, so remember that here
        # and take it explicitly: a wrapper of plain `*args` would not receive
        # the instance, and one of `(e=None)` would mistake it for the event.
        # Flet still infers arity correctly either way, because
        # `functools.wraps` points `inspect.signature` at the original -- and
        # some handlers take no event at all (`DistributorsPage.handle_create`
        # is wired to on_submit/on_click, which Flet calls with no arguments).
        params = list(inspect.signature(handler).parameters)
        is_method = bool(params) and params[0] in ("self", "cls")
        takes_event = bool(params[1:] if is_method else params)

        def start() -> tuple:
            overlay = _active_overlay
            return overlay, overlay is not None and (
                force or database.will_hit_network()
            )

        if is_method:
            @functools.wraps(handler)
            def wrapper(self, *args):
                overlay, blocking = start()
                call = (
                    (lambda: handler(self, args[0]))
                    if takes_event and args
                    else (lambda: handler(self))
                )
                yield from _drive(overlay, message, blocking, call)
        else:
            @functools.wraps(handler)
            def wrapper(*args):
                overlay, blocking = start()
                call = (
                    (lambda: handler(args[0]))
                    if takes_event and args
                    else (lambda: handler())
                )
                yield from _drive(overlay, message, blocking, call)

        return wrapper

    return decorate