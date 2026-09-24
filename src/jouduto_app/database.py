import os
import sqlite3
from typing import Optional, Any, Tuple, List, Dict

from datatypes import Inventory, Item
import appstate


# ---------------------------------------------------------------------------
# Shared query helpers. Each opens its own short-lived connection so callers
# never have to hand-write SQL or manage a context just to fetch a common list.
# The active year comes from appstate (the same logic the pages used inline),
# so these "just work" against whichever fiscal year is selected.
# ---------------------------------------------------------------------------

def get_all_distributors() -> list[dict]:
    """Return every distributor row ordered by name."""
    with DatabaseManager() as db:
        return db.fetch_all(
            "SELECT * FROM distributors ORDER BY distributor_name"
        )


def get_distributor_pairs() -> list[tuple[int, str]]:
    """Return (id, name) pairs for populating distributor dropdowns."""
    with DatabaseManager() as db:
        rows = db.fetch_all(
            "SELECT distributor_id, distributor_name FROM distributors "
            "ORDER BY distributor_name"
        )
    return [(r["distributor_id"], r["distributor_name"]) for r in rows]


def get_all_items() -> list[dict]:
    """Return every item row ordered by name."""
    with DatabaseManager() as db:
        return db.fetch_all("SELECT * FROM items ORDER BY item_name")


def get_tag_pairs() -> list[tuple[int, str]]:
    """Return (id, name) pairs for populating tag filter controls."""
    with DatabaseManager() as db:
        rows = db.fetch_all("SELECT tag_id, tag_name FROM tags ORDER BY tag_name")
    return [(r["tag_id"], r["tag_name"]) for r in rows]


def get_item_tag_map() -> dict[int, list[str]]:
    """Return {item_id: [tag_name, ...]} for the active year's DB."""
    with DatabaseManager() as db:
        rows = db.fetch_all(
            """
            SELECT it.item_id, t.tag_name
            FROM item_tags it
            JOIN tags t ON it.tag_id = t.tag_id
            ORDER BY t.tag_name
            """
        )
    mapping: dict[int, list[str]] = {}
    for r in rows:
        mapping.setdefault(r["item_id"], []).append(r["tag_name"])
    return mapping


def get_report_items(distributor_id: int | None = None) -> list[dict]:
    """Return items with inventory + cost for the order report.

    When distributor_id is given, only items supplied by that distributor
    come back, costed at that distributor's price. Otherwise every item is
    returned, costed at its primary distributor's price (falling back to
    the item's first distributor, then inventory-level cost).
    """
    if distributor_id is not None:
        with DatabaseManager() as db:
            return db.fetch_all(
                """
                SELECT i.item_id, i.item_code, i.item_name,
                       inv.quantity_available AS available,
                       inv.quantity_ordered AS ordered,
                       inv.quantity_sold AS sold,
                       id_.cost_price, d.distributor_name
                FROM items i
                JOIN inventory inv ON inv.item_id = i.item_id
                JOIN item_distributors id_ ON id_.item_id = i.item_id
                                          AND id_.distributor_id = ?
                JOIN distributors d ON d.distributor_id = id_.distributor_id
                ORDER BY i.item_name
                """,
                (distributor_id,),
            )

    with DatabaseManager() as db:
        rows = db.fetch_all(
            """
            SELECT i.item_id, i.item_code, i.item_name,
                   inv.quantity_available AS available,
                   inv.quantity_ordered AS ordered,
                   inv.quantity_sold AS sold,
                   inv.cost_price
            FROM items i
            LEFT JOIN inventory inv ON inv.item_id = i.item_id
            ORDER BY i.item_name
            """
        )
        id_rows = db.fetch_all(
            """
            SELECT id_.item_id, id_.cost_price, d.distributor_name
            FROM item_distributors id_
            JOIN distributors d ON d.distributor_id = id_.distributor_id
            ORDER BY id_.item_id, id_.is_primary DESC
            """
        )
        distro_by_item: dict[int, list[dict]] = {}
        for r in id_rows:
            distro_by_item.setdefault(r["item_id"], []).append(r)

    for row in rows:
        row["cost_price"] = row["cost_price"] or 0
        row["distributor_name"] = ""
        row["distributor_id"] = None
        for d in distro_by_item.get(row["item_id"], []):
            if d["cost_price"] is not None:
                row["cost_price"] = d["cost_price"]
                row["distributor_name"] = d["distributor_name"]
                break
    return rows


def get_item_year_sales() -> dict[str, dict[int, int]]:
    """Return {item_code: {year: quantity_sold}} across every year's DB.

    Each fiscal year is its own database with its own item_ids, so rows are
    matched across years by item_code (unique within each year's DB).
    """
    sales: dict[str, dict[int, int]] = {}
    for year in appstate.get_years():
        db_path = appstate.get_db_path(year)
        if not os.path.exists(db_path):
            continue
        with DatabaseManager(db_path) as db:
            rows = db.fetch_all(
                """
                SELECT i.item_code, COALESCE(inv.quantity_sold, 0) AS sold
                FROM items i
                LEFT JOIN inventory inv ON inv.item_id = i.item_id
                """
            )
        for r in rows:
            sales.setdefault(r["item_code"], {})[year] = r["sold"]
    return sales


def get_dashboard_stats() -> dict:
    """Pull aggregate inventory/PO stats for the Home dashboard."""
    with DatabaseManager() as db:
        row = db.fetch_one("SELECT COUNT(*) AS cnt FROM items")
        total_items = row["cnt"] if row else 0

        row = db.fetch_one("SELECT COUNT(*) AS cnt FROM distributors")
        distributors = row["cnt"] if row else 0

        row = db.fetch_one(
            "SELECT COALESCE(SUM(quantity_available), 0) AS avail, "
            "COALESCE(SUM(quantity_ordered), 0) AS ordered, "
            "COALESCE(SUM(quantity_sold), 0) AS sold FROM inventory"
        )
        total_available = row["avail"] if row else 0
        total_ordered = row["ordered"] if row else 0
        total_sold = row["sold"] if row else 0

        row = db.fetch_one(
            "SELECT COUNT(*) AS cnt FROM inventory WHERE quantity_available < 10"
        )
        low_stock = row["cnt"] if row else 0

        row = db.fetch_one(
            "SELECT COUNT(*) AS cnt FROM inventory WHERE quantity_available = 0"
        )
        out_of_stock = row["cnt"] if row else 0

        row = db.fetch_one(
            "SELECT COUNT(*) AS cnt FROM purchase_orders WHERE status = 'ORDERED'"
        )
        active_pos = row["cnt"] if row else 0

    return {
        "total_items": total_items,
        "total_available": total_available,
        "total_ordered": total_ordered,
        "total_sold": total_sold,
        "low_stock": low_stock,
        "out_of_stock": out_of_stock,
        "active_pos": active_pos,
        "distributors": distributors,
    }

# One-time migration: collapse PO statuses to DRAFT/ORDERED. Existing databases
# created before this change used ORDERED/RECEIVED/CANCELLED (plus an INSERT
# trigger that reserved quantity_ordered). Rebuilt the purchase_orders table so
# the CHECK/DEFAULT reflect the new concept and drop the now-unused trigger.
_OLD_PO_TRIGGER = "trg_po_item_inserted"


def migrate_po_statuses(db):
    """Ensure purchase_orders uses only DRAFT/ORDERED; no-op if already new."""
    table = db.fetch_one(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='purchase_orders'"
    )
    create_sql = (table or {}).get("sql") or ""
    if "RECEIVED" not in create_sql:
        return

    db.execute_script(f"""
        PRAGMA foreign_keys = OFF;
        ALTER TABLE purchase_orders RENAME TO purchase_orders_legacy;
        DROP TRIGGER IF EXISTS {_OLD_PO_TRIGGER};
        CREATE TABLE purchase_orders (
            po_id INTEGER PRIMARY KEY,
            po_number TEXT NOT NULL UNIQUE,
            distributor_id INTEGER NOT NULL,
            status TEXT CHECK(status IN ('DRAFT', 'ORDERED')) DEFAULT 'DRAFT',
            order_date TEXT DEFAULT CURRENT_TIMESTAMP,
            expected_date TEXT,
            received_date TEXT,
            notes TEXT,
            FOREIGN KEY (distributor_id) REFERENCES distributors(distributor_id) ON DELETE RESTRICT
        );
        INSERT INTO purchase_orders
            (po_id, po_number, distributor_id, status, order_date, expected_date, received_date, notes)
        SELECT po_id, po_number, distributor_id,
               CASE WHEN status = 'ORDERED' THEN 'ORDERED'
                    WHEN status = 'RECEIVED' THEN 'ORDERED'
                    ELSE 'DRAFT' END,
               order_date, expected_date, received_date, notes
        FROM purchase_orders_legacy;
        DROP TABLE purchase_orders_legacy;
    """)

class DatabaseManager:
    def __init__(self, path: str | None = None):
        self.path = path if path is not None else appstate.get_db_path()
        self.conn: Optional[sqlite3.Connection] = None
        self.cur: Optional[sqlite3.Cursor] = None

    def __enter__(self):
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.cur = self.conn.cursor()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.conn:
            if exc_type is None:
                self.conn.commit()
            else:
                self.conn.rollback()

            if self.cur:
                self.cur.close()
            self.conn.close()

    def execute_query(self, query: str, params: Tuple[Any, ...] = ()) -> None:

        if self.cur is None:
            raise Exception("Cursor not initialized")
        self.cur.execute(query, params)

    def execute_many_query(self, query: str, params: Tuple[Any, ...] = ()) -> None:

        if self.cur is None:
            raise Exception("Cursor not initialized")
        self.cur.executemany(query, params)


    def execute_script(self, script: str) -> None:

        if self.cur is None:
            raise Exception("Cursor not initialized")
        self.cur.executescript(script)

    def fetch_all(self, query: str, params: Tuple[Any, ...] = ()) -> List[Dict[str, Any]]:

        if self.cur is None:
            raise Exception("Cursor not initialized")
        self.cur.execute(query, params)
        return [dict(row) for row in self.cur.fetchall()]

    def fetch_one(self, query: str, params: Tuple[Any, ...] = ()) -> Optional[Dict[str, Any]]:

        if self.cur is None:
            raise Exception("Cursor not initialized")
        self.cur.execute(query, params)
        row = self.cur.fetchone()
        return dict(row) if row else None

    def fetch_simple_one_item(self, item_code: str) -> Item | None: 

        if self.cur is None:
            raise Exception("Cursor not initialized")

        self.cur.execute("SELECT * FROM items WHERE items.item_code = ?", (item_code,))
        it = self.cur.fetchone()
        if not it: 
            return None

        self.cur.execute("SELECT * FROM inventory WHERE inventory.item_id = ?", (it["item_id"],))
        db_inv = self.cur.fetchone()
        inv = Inventory(db_inv["inventory_id"], db_inv["item_id"], db_inv["quantity_available"], db_inv["quantity_ordered"], db_inv["quantity_sold"]) if db_inv else None
        return Item(it["item_id"], it["item_code"], it["item_name"], inventory=inv)



