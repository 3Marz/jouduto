
DB_PATH = "data/jouduto.db"
INITIAL_DB_SCHEME = """
CREATE TABLE IF NOT EXISTS distributors (
    distributor_id INTEGER PRIMARY KEY,
    distributor_name TEXT NOT NULL UNIQUE,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS items (
    item_id INTEGER PRIMARY KEY,
    item_code TEXT NOT NULL UNIQUE,
    item_name TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS item_distributors (
    item_id INTEGER NOT NULL,
    distributor_id INTEGER NOT NULL,
    is_primary BOOLEAN DEFAULT FALSE,
    cost_price NUMERIC,
    PRIMARY KEY (item_id, distributor_id),
    FOREIGN KEY (item_id) REFERENCES items(item_id) ON DELETE CASCADE,
    FOREIGN KEY (distributor_id) REFERENCES distributors(distributor_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS inventory (
    inventory_id INTEGER PRIMARY KEY,
    item_id INTEGER NOT NULL UNIQUE,
    quantity_available INTEGER DEFAULT 0,
    quantity_ordered INTEGER DEFAULT 0,
    quantity_sold INTEGER DEFAULT 0,
    cost_price NUMERIC DEFAULT 0.0,
    last_updated TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (item_id) REFERENCES items(item_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS purchase_orders (
    po_id INTEGER PRIMARY KEY,
    po_number TEXT NOT NULL UNIQUE,
    distributor_id INTEGER NOT NULL,
    status TEXT CHECK(status IN ('DRAFT', 'ORDERED', 'RECEIVED', 'CANCELLED')) DEFAULT 'DRAFT',
    order_date TEXT DEFAULT CURRENT_TIMESTAMP,
    expected_date TEXT,
    received_date TEXT,
    notes TEXT,
    FOREIGN KEY (distributor_id) REFERENCES distributors(distributor_id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS po_items (
    po_item_id INTEGER PRIMARY KEY,
    po_id INTEGER NOT NULL,
    item_id INTEGER NOT NULL,
    quantity_ordered INTEGER NOT NULL CHECK (quantity_ordered > 0),
    unit_cost NUMERIC NOT NULL CHECK (unit_cost >= 0),
    UNIQUE (po_id, item_id),
    FOREIGN KEY (po_id) REFERENCES purchase_orders(po_id) ON DELETE CASCADE,
    FOREIGN KEY (item_id) REFERENCES items(item_id) ON DELETE RESTRICT
);

CREATE TRIGGER IF NOT EXISTS trg_po_item_inserted
AFTER INSERT ON po_items
BEGIN
    UPDATE inventory
    SET quantity_ordered = quantity_ordered + NEW.quantity_ordered,
        last_updated = CURRENT_TIMESTAMP
    WHERE item_id = NEW.item_id;
END;

"""


