"""Order recommendation math — Python port of the simplified `calculateOrder`.

Everything here is pure — no flet, no database. The core function is a
faithful conversion of the JavaScript order-calculation algorithm:

- Average daily demand = annualSold / 365
- Target stock         = daily_demand * target_days   (days of cover we want)
- Inventory position   = current_qty + incoming_qty   (in-transit counts)
- Order only when target stock exceeds the inventory position; qty =
  target stock - inventory position, floored at minimum_order_qty and
  rounded UP to the order_multiple.
- Items with no sales are never ordered (should_order = False, qty = 0).

Example:
    calc = calculate_order(
        annual_sold=3650, current_qty=120, incoming_qty=0,
        target_days=540, minimum_order_qty=0, order_multiple=1,
    )
"""

import math
from datetime import date

DAYS_PER_YEAR = 365.0


def days_elapsed_in_year(year: int, today: date | None = None) -> float:
    """Days elapsed in `year` as of `today` (full 365 for any past year)."""
    today = today or date.today()
    if year < today.year:
        return DAYS_PER_YEAR
    if year == today.year:
        return max((today - date(year, 1, 1)).days, 1)
    return DAYS_PER_YEAR


def selling_power(sales_by_year: dict[int, int], today: date | None = None) -> float:
    """Average daily sales rate across every year that has data (0 if none).

    Used to turn the per-fiscal-year `quantity_sold` history (each year is
    its own database) into a single number; the caller can annualize it
    with `* 365` to feed `calculate_order`.
    """
    rates = [
        sold / days_elapsed_in_year(year, today)
        for year, sold in sales_by_year.items()
        if sold > 0
    ]
    if not rates:
        return 0.0
    return sum(rates) / len(rates)


def calculate_order(
    *,
    annual_sold: int | float,
    current_qty: int | float,
    incoming_qty: int | float = 0,
    target_days: int | float = 540,
    minimum_order_qty: int | float = 0,
    order_multiple: int | float = 1,
) -> dict:
    """Decide whether an item needs ordering this round and by how much.

    Args:
        annual_sold: units sold over the reference year; 0/negative means
            the item has no sales history (and is never ordered).
        current_qty: units currently on the shelf (quantity_available).
        incoming_qty: units already in transit / on order (quantity_ordered).
        target_days: how many days of stock we want to hold on hand.
        minimum_order_qty: never order less than this.
        order_multiple: round order qty UP to a multiple of this.

    Returns: dict with should_order, qty, target_stock, inventory_position.
    """
    annual_sold = float(annual_sold or 0)
    current_qty = float(current_qty or 0)
    incoming_qty = float(incoming_qty or 0)

    if annual_sold <= 0:
        return {
            "should_order": False,
            "qty": 0,
            "target_stock": 0.0,
            "inventory_position": current_qty + incoming_qty,
            "daily_demand": 0.0,
        }

    daily_demand = annual_sold / DAYS_PER_YEAR

    target_stock = daily_demand * target_days

    inventory_position = current_qty + incoming_qty

    qty = target_stock - inventory_position

    if qty <= 0:
        return {
            "should_order": False,
            "qty": 0,
            "target_stock": target_stock,
            "inventory_position": inventory_position,
            "daily_demand": daily_demand,
        }

    qty = max(qty, minimum_order_qty)
    qty = math.ceil(qty / order_multiple) * order_multiple

    return {
        "should_order": True,
        "qty": qty,
        "target_stock": target_stock,
        "inventory_position": inventory_position,
        "daily_demand": daily_demand,
    }