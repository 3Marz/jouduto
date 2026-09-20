import sqlite3
from typing import Optional, Any, Tuple, List, Dict

from datatypes import Inventory, Item
import appstate

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



