
from dataclasses import dataclass, field

@dataclass
class Distributor:
    id: int
    name: str
    is_primary: bool

@dataclass 
class Inventory:
    id: int
    item_id: int
    quantity_available: int = 0
    quantity_ordered: int = 0
    quantity_sold: int = 0
    cost_price: float = 0.0
    last_updated: str = ""

@dataclass
class Item:
    id: int
    code: str
    name: str
    created_at: str = "2026-01-01 00:00:00"
    inventory: Inventory | None = None
    distributors: list[Distributor] = field(default_factory=list)

