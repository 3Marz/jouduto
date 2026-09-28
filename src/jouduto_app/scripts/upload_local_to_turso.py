#!/usr/bin/env python3
"""Upload the legacy local jouduto_{year}.db files into their Turso databases.

The four original SQLite files under `data/` are the real dataset. Creating the
databases on Turso does not copy their contents, so this walks each fiscal year,
replays its rows into the local replica through the sync connection, and pushes
the changes to the remote.

Explicit primary keys are preserved so item_id / po_id stay stable across the
migration. Rows are committed and pushed table-by-table to keep each HTTP body
small and to make a partial failure easy to identify and retry.

Examples:
    python scripts/upload_local_to_turso.py --dry-run     # show the plan only
    python scripts/upload_local_to_turso.py               # upload empty targets
    python scripts/upload_local_to_turso.py --force       # wipe target, then upload
    python scripts/upload_local_to_turso.py --year 2026   # one fiscal year
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import appstate
import constants
import database

# Insert order respects the foreign keys: parents before children.
TABLES = [
    "distributors",
    "items",
    "item_distributors",
    "inventory",
    "purchase_orders",
    "po_items",
    "tags",
    "item_tags",
]


def local_source(year: int) -> Path:
    """The pre-Turso local file for `year` (data/jouduto_{year}.db)."""
    return Path(appstate.DATA_DIR) / appstate.DB_TEMPLATE.format(year=year)


def target_count(db: database.DatabaseManager, table: str) -> int:
    return db.fetch_one(f"SELECT COUNT(*) AS c FROM {table}")["c"]


def upload_year(year: int, force: bool, dry_run: bool) -> bool:
    source_path = local_source(year)
    if not source_path.exists():
        print(f"[{year}] no local source at {source_path}, skipping")
        return True

    if not database.year_available(year):
        print(f"[{year}] no TURSO_URL_{year} configured, skipping")
        return True

    source = sqlite3.connect(f"file:{source_path}?mode=ro", uri=True)
    source.row_factory = sqlite3.Row
    source_counts = {
        table: source.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in TABLES
    }
    total = sum(source_counts.values())
    print(f"[{year}] {source_path} -> Turso ({total} rows) {source_counts}")

    if dry_run:
        source.close()
        return True

    with database.DatabaseManager(year=year) as db:
        db.execute_script(constants.INITIAL_DB_SCHEME)

        existing = target_count(db, "items")
        if existing and not force:
            print(
                f"[{year}] remote already has {existing} items; "
                f"re-run with --force to wipe and re-upload"
            )
            source.close()
            return False

        if force:
            for table in reversed(TABLES):
                db.execute_query(f"DELETE FROM {table}")
            # One commit for the wipe so the remote is not briefly empty-of-old
            # while partially loaded.
            db.commit_and_push()

        for table in TABLES:
            rows = [dict(r) for r in source.execute(f"SELECT * FROM {table}")]
            if not rows:
                continue
            columns = list(rows[0].keys())
            placeholders = ", ".join("?" for _ in columns)
            column_list = ", ".join(columns)
            db.execute_many_query(
                f"INSERT OR REPLACE INTO {table} ({column_list}) VALUES ({placeholders})",
                [tuple(r[c] for c in columns) for r in rows],
            )
            # Commit + push per table: small HTTP bodies, and a failure only
            # affects the table being loaded.
            db.commit_and_push()
            print(f"[{year}]   {table}: {len(rows)}")

        verified = {t: target_count(db, t) for t in TABLES}
        db.commit_and_push()

    source.close()

    mismatches = {
        t: (source_counts[t], verified[t])
        for t in TABLES
        if source_counts[t] != verified[t]
    }
    if mismatches:
        print(f"[{year}] MISMATCH (expected, actual): {mismatches}")
        return False
    print(f"[{year}] verified: {verified}")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--year", type=int, action="append", help="limit to these years")
    parser.add_argument("--force", action="store_true", help="delete target rows first")
    parser.add_argument("--dry-run", action="store_true", help="report without writing")
    args = parser.parse_args(argv)

    years = args.year or appstate.get_years()
    results = [upload_year(y, args.force, args.dry_run) for y in years]

    database.close_all_connections()
    ok = all(results)
    print("\nUpload complete." if ok else "\nUpload finished with problems.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
