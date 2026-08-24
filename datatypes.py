
from dataclasses import dataclass, field

@dataclass
class Distributor:
    id: int
    name: str

@dataclass 
class Inventory:
    id: int
    item_id: int
    quantity_available: int
    quantity_ordered: int
    quantity_sold: int
    cost_price: float
    last_updated: str

@dataclass
class Item:
    id: int
    code: str
    name: str
    created_at: str = "2021-01-01 00:00:00"
    inventory: Inventory | None = None
    distributors: list[Distributor] = field(default_factory=list)

