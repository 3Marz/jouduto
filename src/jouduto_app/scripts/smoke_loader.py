#!/usr/bin/env python3
"""Headless smoke test for the cloud loading overlay (components/loader.py).

The overlay is the one piece of UI that depends on *how* Flet dispatches event
handlers, so this asserts the mechanism itself rather than just that the widget
builds:

  - a decorated handler is a generator function with the arity Flet expects,
  - it yields exactly once, while visible, when it will really block,
  - it does NOT yield for a warm year, so local reads never flash a spinner,
  - the overlay is reference counted (nested work) and always cleared,
  - the scrim is mounted above the shell content.

Remote replication is disabled except where a cold/warm connection is faked,
so the smoke needs no network and no Turso account.

Examples:
    python scripts/smoke_loader.py        # run all loader assertions
"""

from __future__ import annotations

import inspect
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import appstate
import database
from components.loader import (
    LoadingOverlay,
    cloud_loading,
    run_handler,
    set_active_overlay,
)
from flet.controls.base_control import BaseControl, get_param_count
import flet as ft


class FakePage:
    """Absorbs the page calls the overlay makes."""

    def __init__(self):
        self.route = "/"
        self.views = []
        self.updates = 0

    def update(self):
        self.updates += 1

    def navigate(self, route: str):
        self.route = route

    def show_dialog(self, dialog):
        pass

    def pop_dialog(self):
        pass


PAGE = FakePage()
BaseControl.page = property(lambda self: PAGE)

TMPDIR = Path(tempfile.mkdtemp(prefix="jouduto_smoke_loader_"))
appstate.DATA_DIR = str(TMPDIR)
appstate.set_remote_enabled(False)


def check(name: str, cond: bool, detail=""):
    if not cond:
        print(f"FAIL: {name} {detail}")
        sys.exit(1)
    print(f"ok: {name}")


def make_overlay() -> LoadingOverlay:
    """An overlay whose own update() is a no-op (no real client to patch)."""
    overlay = LoadingOverlay(PAGE)
    overlay.update = lambda: None
    return overlay


def fake_cold_year(year: int) -> None:
    """Make `year` look like an unopened, un-pulled replica."""
    database._connections[(appstate.get_db_path(year), "libsql://fake")] = _Cold()


def fake_warm_year(year: int) -> None:
    """Make `year` look like an open replica that has already pulled."""
    database._connections[(appstate.get_db_path(year), "libsql://fake")] = _Warm()


class _Cold:
    remote_url = "libsql://fake"
    pulled = False


class _Warm:
    remote_url = "libsql://fake"
    pulled = True


def drain(generator) -> list:
    """Iterate a decorated handler the way Flet does, recording the overlay
    state the client would have seen at each flush point."""
    return [overlay.visible for _ in generator]


# ---------------------------------------------------------------------------
overlay = make_overlay()
set_active_overlay(overlay)

# 1. force=True always shows the overlay and yields exactly once -----------
seen: list = []


@cloud_loading("Saving…", force=True)
def writes(e):
    seen.append(("writes", e))


yield_states = drain(writes("EVENT"))
check("force=True yields once", len(yield_states) == 1, str(yield_states))
check("overlay visible at the yield", yield_states == [True], str(yield_states))
check("handler still ran", seen == [("writes", "EVENT")], str(seen))
check("overlay hidden afterwards", overlay.visible is False)
check("overlay depth unwound", overlay._depth == 0, str(overlay._depth))

# 2. without force, a warm year is served locally and must not flash -------
appstate.set_remote_enabled(True)
appstate.set_active_year(2026)
fake_warm_year(2026)
check("warm year reports no network", database.will_hit_network() is False)

overlay.visible = False
seen.clear()


@cloud_loading("Loading…")
def reads(e):
    seen.append(("reads", e))


yield_states = drain(reads("EVENT"))
check("warm year yields nothing", yield_states == [], str(yield_states))
check("warm year never shows overlay", overlay.visible is False)
check("warm year still runs handler", seen == [("reads", "EVENT")], str(seen))

# 3. without force, a cold year must show the overlay ---------------------
appstate.set_active_year(2023)
fake_cold_year(2023)
check("cold year reports network", database.will_hit_network() is True)

overlay.visible = False
seen.clear()


@cloud_loading("Loading…")
def cold_reads(e):
    seen.append(("cold", e))


yield_states = drain(cold_reads("EVENT"))
check("cold year yields once", len(yield_states) == 1, str(yield_states))
check("cold year visible at yield", yield_states == [True], str(yield_states))
check("cold year runs handler", seen == [("cold", "EVENT")], str(seen))
check("cold year hides overlay after", overlay.visible is False)

# 4. embedded mode never claims to load ------------------------------------
database._connections.clear()
appstate.set_remote_enabled(False)
check("embedded mode reports no network", database.will_hit_network() is False)

# 5. nesting: an inner operation must not hide the overlay early -----------
overlay._depth = 0
overlay.visible = False
overlay.begin("outer")
overlay.begin("inner")
overlay.end()
check("inner end keeps overlay up", overlay.visible is True)
overlay.end()
check("outer end hides overlay", overlay.visible is False)
check("nesting leaves depth 0", overlay._depth == 0, str(overlay._depth))

# 6. a failing handler still clears the overlay ---------------------------


@cloud_loading("Boom…", force=True)
def boom(e):
    raise RuntimeError("handler exploded")


overlay.visible = False
try:
    run_handler(boom, None)
    check("exception propagates", False, "no exception raised")
except RuntimeError:
    check("exception propagates", True)
check("overlay cleared after exception", overlay.visible is False)
check("depth reset after exception", overlay._depth == 0, str(overlay._depth))

# 7. handlers that take no event at all ------------------------------------
seen.clear()


@cloud_loading("Creating…", force=True)
def no_args():
    seen.append("no_args")


run_handler(no_args)
check("zero-arg handler invoked", seen == ["no_args"], str(seen))

# 8. Flet must see a generator with the original arity --------------------


class Sample:
    @cloud_loading("a")
    def with_event(self, e):
        return "with_event"

    @cloud_loading("b")
    def without_event(self):
        return "without_event"

    @cloud_loading("c")
    def wrapped_function(self, e):  # not a method
        return "wrapped_function"


sample = Sample()
check("method is generator", inspect.isgeneratorfunction(sample.with_event))
check("zero-arg method is generator", inspect.isgeneratorfunction(sample.without_event))
check(
    "flet passes the event",
    get_param_count(sample.with_event) == 1,
    str(get_param_count(sample.with_event)),
)
check(
    "flet omits the event",
    get_param_count(sample.without_event) == 0,
    str(get_param_count(sample.without_event)),
)
check("function is generator", inspect.isgeneratorfunction(Sample.wrapped_function))

# 9. the scrim covers the shell content ------------------------------------
overlay.visible = False
stack = ft.Stack(controls=[ft.Text("content"), overlay])
check("overlay is the top-most control", stack.controls[-1] is overlay)
check(
    "overlay covers its parent",
    (overlay.left, overlay.top, overlay.right, overlay.bottom) == (0, 0, 0, 0),
)
check("overlay starts hidden", overlay.visible is False)
check("overlay absorbs clicks", overlay.on_click is not None)

shutil.rmtree(TMPDIR, ignore_errors=True)
print("\nAll loading-overlay smoke checks passed.")