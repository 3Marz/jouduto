import sqlite3
from typing import Optional, Any, Tuple, List, Dict

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
        # Executes a command that doesn't return data (CREATE, INSERT, UPDATE, DELETE). #
        if self.cur is None:
            raise Exception("Cursor not initialized")
        self.cur.execute(query, params)

    def execute_script(self, script: str) -> None:
        # Executes a script that doesn't return data (CREATE, INSERT, UPDATE, DELETE). #
        if self.cur is None:
            raise Exception("Cursor not initialized")
        self.cur.executescript(script)

    def fetch_all(self, query: str, params: Tuple[Any, ...] = ()) -> List[Dict[str, Any]]:
        # Executes a query and returns all results as a list of dictionaries. #
        if self.cur is None:
            raise Exception("Cursor not initialized")
        self.cur.execute(query, params)
        return [dict(row) for row in self.cur.fetchall()]

    def fetch_one(self, query: str, params: Tuple[Any, ...] = ()) -> Optional[Dict[str, Any]]:
        # Executes a query and returns the first result row as a dictionary #
        if self.cur is None:
            raise Exception("Cursor not initialized")
        self.cur.execute(query, params)
        row = self.cur.fetchone()
        return dict(row) if row else None




