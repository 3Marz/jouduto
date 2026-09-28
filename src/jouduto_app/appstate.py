
from datetime import datetime
import os
import flet as ft

FIRST_YEAR = 2023
DATA_DIR = "data"
# Cloud-backed years live in their own directory: a Turso replica must start
# absent-or-empty so the SDK can bootstrap it from the remote, and the original
# local jouduto_{year}.db files stay put as backups.
REPLICA_SUBDIR = "replicas"
DB_TEMPLATE = "jouduto_{year}.db"

_active_year: int = datetime.now().year
_sync_error: str = ""
_remote_enabled: bool = True


def get_active_year() -> int:
    return _active_year


def set_active_year(year: int) -> None:
    global _active_year
    _active_year = year


def get_years() -> list[int]:
    return list(range(FIRST_YEAR, datetime.now().year + 1))


def get_db_path(year: int | None = None) -> str:
    """Local replica file for `year`.

    This is a *cache*: the remote Turso database is the source of truth and
    the file is populated by `turso.sync.connect(..., bootstrap_if_empty=True)`.
    """
    target = year if year is not None else _active_year
    return os.path.join(DATA_DIR, REPLICA_SUBDIR, DB_TEMPLATE.format(year=target))


# Backwards-compatible alias: the replica is still a per-year SQLite file, the
# only difference is which directory it lives in.
get_replica_path = get_db_path


def set_sync_error(message: str) -> None:
    """Record a replication failure so the UI can surface it (fail loudly)."""
    global _sync_error
    _sync_error = message


def get_sync_error() -> str:
    return _sync_error


def clear_sync_error_if(prefix: str) -> None:
    """Drop a recorded sync error only when it belongs to `prefix`.

    Several years replicate independently, so a successful push for one year
    must not hide a still-broken one.
    """
    global _sync_error
    if _sync_error.startswith(f"{prefix}: "):
        _sync_error = ""


def set_remote_enabled(enabled: bool) -> None:
    """Turn cloud replication on/off for the whole process.

    The headless scripts (seed, smoke tests) flip this off so they work against
    a plain local embedded database with no network at all.
    """
    global _remote_enabled
    _remote_enabled = enabled


def is_remote_enabled() -> bool:
    return _remote_enabled


# A distinct theme color per fiscal year so the active year is visible
# at a glance. Explicit entries for known years; future years fall back
# to a deterministic pick from the palette below.
YEAR_COLORS: dict[int, str] = {
    2023: ft.Colors.GREEN_500,
    2024: ft.Colors.INDIGO_500,  
    2025: ft.Colors.ORANGE_500,  
    2026: ft.Colors.CYAN_500,  
}

_FALLBACK_YEAR_COLORS = ["#B3261E", "#0B57D0", "#146C2E", "#B93815", "#6A1B9A", "#006A6A"]


def get_year_color(year: int | None = None) -> str:
    target = year if year is not None else _active_year
    if target in YEAR_COLORS:
        return YEAR_COLORS[target]
    return _FALLBACK_YEAR_COLORS[(target - FIRST_YEAR) % len(_FALLBACK_YEAR_COLORS)]
