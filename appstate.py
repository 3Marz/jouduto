from datetime import datetime
import os

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