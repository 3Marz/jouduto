#!/usr/bin/env python3
"""Seed the Jouduto database with sample data for development and testing.

By default this refuses to touch a database that already contains items, so a
mistyped command can't wipe your real data. Use --reset to explicitly wipe first.

Examples:
    python scripts/seed.py                                  # seed data/jouduto.db (refuses if non-empty)
    python scripts/seed.py --reset                          # wipe existing data, then seed
    python scripts/seed.py --db /tmp/opencode/test.db --reset
    python scripts/seed.py --items 6000                     # stress-test the item search
"""

from __future__ import annotations

import argparse
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import constants
import appstate
from database import DatabaseManager


ADJECTIVES = [
    "Compact", "Heavy Duty", "Wireless", "Industrial", "Portable",
    "Premium", "Basic", "Smart", "Pro", "Mini",
]
NOUNS = [
    "Drill", "Sensor", "Cable", "Battery", "Pump", "Valve",
    "Controller", "Adapter", "Module", "Kit", "Filter", "Bracket",
]
DISTRIBUTOR_NAMES = [
    "Acme Supply", "Global Parts", "Nova Trading", "Orion Distribution",
    "Pioneer Wholesale", "Summit Goods", "Vertex Supply", "Zenith Traders",
]
STATUSES = ["ORDERED", "DRAFT"]
STATUS_WEIGHTS = [0.7, 0.3]


def has_data(db: DatabaseManager) -> bool:
    row = db.fetch_one("SELECT COUNT(*) AS n FROM items")
    return bool(row and row["n"] > 0)


def wipe(db: DatabaseManager) -> None:
    for table in (
        "po_items",
        "purchase_orders",
        "inventory",
        "item_distributors",
        "items",
        "distributors",
    ):
        db.execute_query(f"DELETE FROM {table}")


def seed(db: DatabaseManager, rng: random.Random, args: argparse.Namespace) -> None:
    distributor_ids: list[int] = []
    base_names = [DISTRIBUTOR_NAMES[i % len(DISTRIBUTOR_NAMES)] for i in range(args.distributors)]
    for i, base in enumerate(base_names):
        db.execute_query(
            "INSERT INTO distributors (distributor_name) VALUES (?)",
            (f"{base} {i + 1}",),
        )
        distributor_ids.append(db.cur.lastrowid)

    item_ids: list[int] = []
    for i in range(args.items):
        db.execute_query(
            "INSERT INTO items (item_code, item_name) VALUES (?, ?)",
            (f"SKU-{i + 1:05d}", f"{rng.choice(ADJECTIVES)} {rng.choice(NOUNS)} {i + 1}"),
        )
        item_ids.append(db.cur.lastrowid)

    for item_id in item_ids:
        cost = round(rng.uniform(1.0, 80.0), 2)
        db.execute_query(
            "INSERT INTO item_distributors (item_id, distributor_id, is_primary, cost_price) "
            "VALUES (?, ?, TRUE, ?)",
            (item_id, rng.choice(distributor_ids), cost),
        )
        db.execute_query(
            "INSERT INTO inventory (item_id, quantity_available, quantity_sold, cost_price) "
            "VALUES (?, ?, ?, ?)",
            (item_id, rng.randint(0, 200), rng.randint(0, 150), cost),
        )

    now = datetime.now()
    for i in range(args.pos):
        status = rng.choices(STATUSES, weights=STATUS_WEIGHTS)[0]
        order_dt = now - timedelta(days=rng.randint(0, 365))
        expected_dt = order_dt + timedelta(days=rng.randint(3, 30))
        db.execute_query(
            "INSERT INTO purchase_orders "
            "(po_number, distributor_id, status, order_date, expected_date, notes) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                f"PO-{order_dt.year}-{i + 1:04d}",
                rng.choice(distributor_ids),
                status,
                order_dt.isoformat(sep=" "),
                expected_dt.isoformat(sep=" "),
                None,
            ),
        )
        po_id = db.cur.lastrowid

        for _ in range(rng.randint(1, 5)):
            item_id = rng.choice(item_ids)
            qty = rng.randint(1, 25)
            unit_cost = round(rng.uniform(1.0, 80.0), 2)
            db.execute_query(
                "INSERT INTO po_items (po_id, item_id, quantity_ordered, unit_cost) "
                "VALUES (?, ?, ?, ?)",
                (po_id, item_id, qty, unit_cost),
            )
            # Only placed (ORDERED) POs reserve quantity_ordered in inventory.
            if status == "ORDERED":
                db.execute_query(
                    "UPDATE inventory SET quantity_ordered = quantity_ordered + ? "
                    "WHERE item_id = ?",
                    (qty, item_id),
                )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Seed the Jouduto database with sample data.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--db",
        default=appstate.get_db_path(),
        help="database file path (defaults to the active year's DB)",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="delete all existing rows before seeding (required if DB is non-empty)",
    )
    parser.add_argument("--items", type=int, default=200, help="number of items to generate")
    parser.add_argument("--distributors", type=int, default=8, help="number of distributors")
    parser.add_argument("--pos", type=int, default=40, help="number of purchase orders")
    parser.add_argument("--seed", type=int, default=42, help="random seed for reproducibility")
    args = parser.parse_args(argv)

    rng = random.Random(args.seed)
    db_path = Path(args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with DatabaseManager(str(db_path)) as db:
        db.execute_script(constants.INITIAL_DB_SCHEME)

        if has_data(db) and not args.reset:
            print(f"Refusing to seed: {db_path} already contains items.")
            print("Re-run with --reset to wipe it first.")
            return 1

        if args.reset:
            wipe(db)
            print(f"Wiped existing data in {db_path}")

        seed(db, rng, args)

        counts = {
            "distributors": db.fetch_one("SELECT COUNT(*) AS n FROM distributors")["n"],
            "items": db.fetch_one("SELECT COUNT(*) AS n FROM items")["n"],
            "inventory": db.fetch_one("SELECT COUNT(*) AS n FROM inventory")["n"],
            "purchase_orders": db.fetch_one("SELECT COUNT(*) AS n FROM purchase_orders")["n"],
            "po_items": db.fetch_one("SELECT COUNT(*) AS n FROM po_items")["n"],
        }

    print(f"Seeded {db_path}:")
    for name, n in counts.items():
        print(f"  {name:16} {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
