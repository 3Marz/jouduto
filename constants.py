
DB_PATH = "data/jouduto.db"
INITIAL_DB_SCHEME = """
CREATE TABLE IF NOT EXISTS distributors (
    distributor_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS warehouses (
    warehouse_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS items (
    item_id INTEGER PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS item_distributors (
    item_id INTEGER NOT NULL,
    distributor_id INTEGER NOT NULL,
    is_primary INTEGER,
    cost_price NUMERIC,
    PRIMARY KEY (item_id, distributor_id),
    FOREIGN KEY (item_id) REFERENCES items(item_id),
    FOREIGN KEY (distributor_id) REFERENCES distributors(distributor_id)
);

CREATE TABLE IF NOT EXISTS inventory (
    inventory_id INTEGER PRIMARY KEY,
    item_id INTEGER NOT NULL UNIQUE,
    quantity_available INTEGER DEFAULT 0,
    quantity_ordered INTEGER DEFAULT 0,
    quantity_sold INTEGER DEFAULT 0,
    cost_price NUMERIC DEFAULT 0.0,
    last_updated TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (item_id) REFERENCES items(item_id)
);
"""


