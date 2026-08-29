import sqlite3
from typing import Optional, Any, Tuple, List, Dict

from datatypes import Inventory, Item

class DatabaseManager:
    def __init__(self, path: str):
        self.path = path
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



