"""Reusable dropdown controls shared across pages.

These centralize the "load rows from the active year's DB and build the
options" step that was previously copy-pasted into items, item_details,
distributors and purchase_orders. Swapping all of them to these tiny controls
removes the inline SQL + option-building noise from those pages.
"""

import flet as ft

from database import get_distributor_pairs


@ft.control
class DistributorDropdown(ft.Dropdown):
    """A distributor picker pre-populated from the active year's DB.

    Example:
        self.distributor_dropdown = DistributorDropdown(
            label="Select Distributor",
            value=str(item.main_distributor_id),
            on_select=self.handle_distributor_change,
        )
    """

    def __init__(
        self,
        *,
        label: str = "Select Distributor",
        value: str | None = None,
        expand: bool = True,
        dense: bool = True,
        text_size: int = 16,
        border_radius: int = 12,
        on_select=None,
    ):
        pairs = get_distributor_pairs()
        super().__init__(
            label=label,
            value=value,
            expand=expand,
            dense=dense,
            text_size=text_size,
            border_radius=border_radius,
            options=[
                ft.DropdownOption(key=str(d_id), text=d_name)
                for d_id, d_name in pairs
            ],
            on_select=on_select,
        )

    def refresh(self):
        """Re-pull the distributor options (no inline SQL in pages)."""
        self.options = [
            ft.DropdownOption(key=str(d_id), text=d_name)
            for d_id, d_name in get_distributor_pairs()
        ]
