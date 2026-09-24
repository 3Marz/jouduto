
from datetime import datetime
import os
import flet as ft

FIRST_YEAR = 2023
DATA_DIR = "data"
DB_TEMPLATE = "jouduto_{year}.db"

_active_year: int = datetime.now().year


def get_active_year() -> int:
    return _active_year


def set_active_year(year: int) -> None:
    global _active_year
    _active_year = year


def get_years() -> list[int]:
    return list(range(FIRST_YEAR, datetime.now().year + 1))


def get_db_path(year: int | None = None) -> str:
    target = year if year is not None else _active_year
    return os.path.join(DATA_DIR, DB_TEMPLATE.format(year=target))


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
