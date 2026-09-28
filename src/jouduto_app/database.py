import os
import threading
from typing import Optional, Any, Tuple, List, Dict

import turso
import turso.sync

from datatypes import Inventory, Item
import appstate
import turso_config


# Turso ships its own DB-API exception hierarchy that does NOT subclass
# sqlite3.Error, so every page catches this instead.
DBError = turso.Error


# ---------------------------------------------------------------------------
# Connection management.
#
# Reads are served from a local embedded replica that replicates with the remote
# via `turso.sync` — there is no HTTP-only remote driver in pyturso. Opening a
# sync connection bootstraps over the network, so connections are cached per
# replica for the whole session and shared; a `with DatabaseManager()` block is
# a transaction scope (commit + push / rollback), not a connection.
# ---------------------------------------------------------------------------

class _Connection:
    """A cached Turso connection plus the bookkeeping sync mode needs."""

    def __init__(self, replica_path: str, remote_url: str | None, auth_token: str | None):
        self.replica_path = replica_path
        self.remote_url = remote_url
        self.label = os.path.basename(replica_path)

        parent = os.path.dirname(replica_path)
        if parent:
            os.makedirs(parent, exist_ok=True)

        if remote_url:
            self.conn = turso.sync.connect(
                replica_path,
                remote_url=remote_url,
                auth_token=auth_token,
                client_name=turso_config.client_name(),
                long_poll_timeout_ms=turso_config.pull_timeout_ms(),
                bootstrap_if_empty=True,
            )
        else:
            # Embedded-only (headless scripts and smoke tests).
            self.conn = turso.connect(replica_path)

        self.conn.row_factory = turso.Row
        self.pulled = False

    def _report(self, op: str, err: Exception) -> None:
        message = f"{self.label}: {op} failed - {err}"
        appstate.set_sync_error(message)
        print(f"[turso] {message}")

    def _clear_error(self) -> None:
        appstate.clear_sync_error_if(self.label)

    def pull(self) -> bool:
        """Fetch remote changes into the replica. No-op when embedded.

        A failed pull is reported but not fatal: the local replica is still
        readable, so the app degrades to stale data instead of dying.
        """
        if self.remote_url is None:
            self.pulled = True
            return False
        try:
            changed = bool(self.conn.pull())
        except Exception as err:
            self.pulled = True
            self._report("pull", err)
            return False
        self.pulled = True
        self._clear_error()
        return changed

    def push(self) -> None:
        """Ship local commits to the remote. No-op when embedded."""
        if self.remote_url is None:
            return
        try:
            self.conn.push()
        except Exception as err:
            self._report("push", err)
            return
        self._clear_error()

    def close(self) -> None:
        try:
            if self.remote_url is not None:
                self.push()
                self.conn.checkpoint()
        except Exception:
            pass
        try:
            self.conn.close()
        except Exception:
            pass


_connections: Dict[Tuple[str, Optional[str]], _Connection] = {}
_conn_lock = threading.RLock()


def _remote_url_for(year: int) -> str | None:
    """Remote URL for `year`, or None when running embedded.

    Raises when cloud mode is on but the year has no remote configured: a
    misconfigured deployment should fail immediately and say which variable is
    missing, not silently fall back to whatever happens to be on disk.
    """
    if not appstate.is_remote_enabled():
        return None
    url = turso_config.get_remote_url(year)
    if url is None:
        raise turso_config.TursoConfigError(
            f"No Turso database configured for {year}. Set "
            f"{turso_config.REMOTE_URL_PREFIX}{year} in {turso_config.env_file_path()} "
            f"(see .env.example), or unset TURSO_* to run embedded."
        )
    return url


def year_available(year: int) -> bool:
    """Whether `year` has a database to read at all."""
    if not appstate.is_remote_enabled():
        return os.path.exists(appstate.get_db_path(year))
    return turso_config.get_remote_url(year) is not None


def _get_connection(replica_path: str, remote_url: str | None) -> _Connection:
    key = (replica_path, remote_url)
    with _conn_lock:
        holder = _connections.get(key)
        if holder is None:
            holder = _Connection(
                replica_path,
                remote_url,
                turso_config.get_auth_token() if remote_url else None,
            )
            _connections[key] = holder
        return holder


def pull_all_years(years: list[int] | None = None) -> None:
    """Pull remote changes for every already-open replica."""
    targets = years if years is not None else appstate.get_years()
    with _conn_lock:
        holders = list(_connections.values())
    wanted = set(targets)
    for holder in holders:
        if holder.remote_url is None:
            continue
        year = _year_of_replica(holder.replica_path)
        if wanted and year is not None and year not in wanted:
            continue
        holder.pull()


def _year_of_replica(replica_path: str) -> int | None:
    stem = os.path.splitext(os.path.basename(replica_path))[0]
    prefix, _, tail = stem.rpartition("_")
    if prefix == "jouduto" and tail.isdigit():
        return int(tail)
    return None


def close_all_connections() -> None:
    """Flush and close every cached replica (call on app shutdown)."""
    with _conn_lock:
        holders = list(_connections.values())
        _connections.clear()
    for holder in holders:
        holder.close()


# ---------------------------------------------------------------------------
# Shared query helpers. Each takes its own short-lived transaction scope over a
# cached connection, so callers never hand-write SQL or manage a context just
# to fetch a common list. The active year comes from appstate (the same logic
# the pages used inline), so these "just work" against whichever fiscal year is
# selected.
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
        if not year_available(year):
            continue
        with DatabaseManager(year=year) as db:
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


def get_item_history_by_code(item_code: str) -> list[dict]:
    """Inventory history for `item_code` across every year before the active one.

    Each fiscal year is its own database with its own item_ids, so the item is
    matched by item_code (unique within each year's DB). Years where the item
    is not present come back with `found=False` so callers can render it as
    absent rather than failing.
    """
    active_year = appstate.get_active_year()
    history: list[dict] = []
    for year in appstate.get_years():
        if year >= active_year:
            continue
        if not year_available(year):
            continue
        with DatabaseManager(year=year) as db:
            row = db.fetch_one(
                """
                SELECT i.item_code, i.item_name,
                       COALESCE(inv.quantity_available, 0)  AS available,
                       COALESCE(inv.quantity_ordered, 0)   AS ordered,
                       COALESCE(inv.quantity_sold, 0)      AS sold
                FROM items i
                LEFT JOIN inventory inv ON inv.item_id = i.item_id
                WHERE i.item_code = ?
                """,
                (item_code,),
            )
        history.append({
            "year": year,
            "item_code": item_code,
            "found": row is not None,
            "item_name": row["item_name"] if row else "",
            "available": row["available"] if row else 0,
            "ordered": row["ordered"] if row else 0,
            "sold": row["sold"] if row else 0,
        })
    return history


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
    """Transaction scope over a cached Turso replica connection.

    The connection is shared for the life of the session (opening a sync
    connection costs a network round-trip), so `__enter__` just grabs a cursor
    and `__exit__` ends the transaction: commit + push on success, rollback on
    failure. Reads never touch the network.
    """

    def __init__(self, path: str | None = None, year: int | None = None):
        self.year = year if year is not None else appstate.get_active_year()
        self.path = path if path is not None else appstate.get_db_path(self.year)
        self.remote_url: str | None = None
        self._holder: _Connection | None = None
        self.conn: Optional[turso.Connection] = None
        self.cur: Optional[turso.Cursor] = None
        self._dirty = False

    def __enter__(self):
        self.remote_url = _remote_url_for(self.year)
        self._holder = _get_connection(self.path, self.remote_url)
        if not self._holder.pulled:
            self._holder.pull()
        self.conn = self._holder.conn
        self.cur = self.conn.cursor()
        self._dirty = False
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.conn is None:
            return False
        try:
            if exc_type is None:
                if self._dirty:
                    self.conn.commit()
                    if self._holder is not None:
                        self._holder.push()
            else:
                self.conn.rollback()
        finally:
            if self.cur is not None:
                self.cur.close()
                self.cur = None
            self.conn = None
        return False

    def commit_and_push(self) -> None:
        """Commit the open transaction and replicate it immediately.

        `__exit__` already does this once per `with` block; bulk tooling that
        wants to checkpoint a long load (so a failure costs one table, not the
        whole run) calls it in between.
        """
        if self.cur is None or self.conn is None:
            raise Exception("Cursor not initialized")
        self.conn.commit()
        if self._holder is not None:
            self._holder.push()
        self._dirty = False

    def execute_query(self, query: str, params: Tuple[Any, ...] = ()) -> None:

        if self.cur is None:
            raise Exception("Cursor not initialized")
        self.cur.execute(query, params)
        self._dirty = True

    def execute_many_query(self, query: str, params: Tuple[Any, ...] = ()) -> None:

        if self.cur is None:
            raise Exception("Cursor not initialized")
        self.cur.executemany(query, params)
        self._dirty = True


    def execute_script(self, script: str) -> None:

        if self.cur is None:
            raise Exception("Cursor not initialized")
        self.cur.executescript(script)
        self._dirty = True

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
