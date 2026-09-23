"""Order Report page: pick report options on the left, generated order
quantities on the right, then export the result to Excel.

The heavy lifting lives in `ordering.calculate_order` (pure math) and the
queries in `database` (get_report_items / get_item_year_sales / tag maps),
so this page is only glue + presentation.
"""

import flet as ft
import flet_datatable2 as fdt
import pandas as pd

from database import (
    get_distributor_pairs,
    get_item_tag_map,
    get_item_year_sales,
    get_report_items,
    get_tag_pairs,
)
from ordering import calculate_order, selling_power

# Report option defaults (editable in the options panel).
DEFAULT_TARGET_DAYS = 540
DEFAULT_MINIMUM_ORDER_QTY = 0
DEFAULT_ORDER_MULTIPLE = 1

ALL_DISTRIBUTORS_KEY = "all"


def _as_float(value, default: float) -> float:
    """Parse a TextField value into a float, falling back to a default."""
    try:
        return float(str(value).strip() or default)
    except ValueError:
        return default


def _fmt_money(value: float) -> str:
    return f"$ {value:,.2f}"


class OrderReportPage(ft.Container):
    def __init__(self):
        super().__init__()
        self.expand = True

        # --- Options panel (left column) ---
        self.distributor_dropdown = ft.Dropdown(
            label="Distributor",
            value=ALL_DISTRIBUTORS_KEY,
            expand=True,
            dense=True,
            border_radius=12,
            options=[
                ft.DropdownOption(key=ALL_DISTRIBUTORS_KEY, text="All distributors"),
                *[
                    ft.DropdownOption(key=str(d_id), text=d_name)
                    for d_id, d_name in get_distributor_pairs()
                ],
            ],
        )

        self.tag_checkboxes: list[ft.Checkbox] = [
            ft.Checkbox(label=name, data=name, value=False)
            for _, name in get_tag_pairs()
        ]
        self.no_tags_text = ft.Text(
            "No tags available",
            italic=True,
            size=12,
            color=ft.Colors.with_opacity(0.6, ft.Colors.ON_SURFACE),
        )
        self.tags_panel = ft.Container(
            height=140,
            border=ft.Border.all(1, ft.Colors.with_opacity(0.15, ft.Colors.OUTLINE)),
            border_radius=10,
            padding=4,
            content=ft.Column(
                spacing=0,
                scroll=ft.ScrollMode.AUTO,
                controls=(self.tag_checkboxes if self.tag_checkboxes else [self.no_tags_text]),
            ),
        )

        self.target_days_field = ft.TextField(
            label="Target stock (days)",
            value=str(DEFAULT_TARGET_DAYS),
            dense=True, text_size=13, border_radius=12, keyboard_type=ft.KeyboardType.NUMBER,
        )
        self.minimum_order_qty_field = ft.TextField(
            label="Minimum order qty",
            value=str(DEFAULT_MINIMUM_ORDER_QTY),
            dense=True, text_size=13, border_radius=12, keyboard_type=ft.KeyboardType.NUMBER,
        )
        self.order_multiple_field = ft.TextField(
            label="Order multiple",
            value=str(DEFAULT_ORDER_MULTIPLE),
            dense=True, text_size=13, border_radius=12, keyboard_type=ft.KeyboardType.NUMBER,
        )
        self.include_zeroed_switch = ft.Switch(
            label="Include items with no sales",
            value=False,
        )

        self.generate_button = ft.Button(
            "Generate Report",
            icon=ft.Icons.PLAY_ARROW,
            on_click=self.handle_generate,
        )
        self.options_error_text = ft.Text("", color=ft.Colors.ERROR, size=12)

        # --- Results panel (right column) ---
        self.export_button = ft.Button(
            "Export to Excel",
            icon=ft.Icons.FILE_DOWNLOAD_OUTLINED,
            on_click=self.handle_export,
        )
        self.export_status = ft.Text("")
        self.summary_text = ft.Text("", size=14, weight=ft.FontWeight.W_600)

        self.results_table = fdt.DataTable2(
            expand=True,
            column_spacing=24,
            horizontal_margin=8,
            heading_row_height=34,
            heading_row_color=ft.Colors.SURFACE_CONTAINER,
            columns=[
                fdt.DataColumn2(label=ft.Text("Code")),
                fdt.DataColumn2(label=ft.Text("Name"), fixed_width=220),
                fdt.DataColumn2(label=ft.Text("Distributor")),
                fdt.DataColumn2(label=ft.Text("Unit Cost"), heading_row_alignment=ft.MainAxisAlignment.START),
                fdt.DataColumn2(label=ft.Text("Sold"), numeric=True, heading_row_alignment=ft.MainAxisAlignment.START),
                fdt.DataColumn2(label=ft.Text("Avail"), numeric=True, heading_row_alignment=ft.MainAxisAlignment.START),
                fdt.DataColumn2(label=ft.Text("Ord"), numeric=True, heading_row_alignment=ft.MainAxisAlignment.START),
                fdt.DataColumn2(label=ft.Text("Daily Rate"), numeric=True, heading_row_alignment=ft.MainAxisAlignment.START),
                fdt.DataColumn2(label=ft.Text("Needs Order")),
                fdt.DataColumn2(label=ft.Text("Target Inv"), numeric=True, heading_row_alignment=ft.MainAxisAlignment.START),
                fdt.DataColumn2(label=ft.Text("Rec Qty"), numeric=True, heading_row_alignment=ft.MainAxisAlignment.START),
                fdt.DataColumn2(label=ft.Text("Est Cost"), heading_row_alignment=ft.MainAxisAlignment.START),
            ],
            rows=[],
        )
        self.no_results_text = ft.Text(
            "Run the report to see recommended order quantities.",
            italic=True,
            size=12,
            color=ft.Colors.with_opacity(0.6, ft.Colors.ON_SURFACE),
        )
        self.results_list = ft.Container(
            expand=True,
            border=ft.Border.all(1, ft.Colors.SURFACE_CONTAINER),
            border_radius=12,
            content=ft.Column(
                controls=[self.results_table, self.no_results_text],
            ),
        )

        self.report_rows: list[dict] = []

        # --- Assembly: two columns (options | results) ---
        options_column = ft.Container(
            width=320,
            content=ft.Column(
                spacing=12,
                scroll=ft.ScrollMode.AUTO,
                controls=[
                    ft.Text("Report Options", size=18, weight=ft.FontWeight.BOLD),
                    self.distributor_dropdown,
                    ft.Text("Tags (must all match)", size=13, weight=ft.FontWeight.W_600),
                    self.tags_panel,
                    self.target_days_field,
                    self.minimum_order_qty_field,
                    self.order_multiple_field,
                    self.include_zeroed_switch,
                    self.generate_button,
                    self.options_error_text,
                ],
            ),
        )

        results_column = ft.Column(
            expand=True,
            spacing=10,
            controls=[
                ft.Row(
                    controls=[
                        ft.Text("Generated Items", size=18, weight=ft.FontWeight.BOLD),
                        ft.Container(width=8),
                        self.export_button,
                        self.export_status,
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                self.summary_text,
                self.results_list,
            ],
        )

        self.content = ft.SafeArea(
            content=ft.Row(
                expand=True,
                controls=[
                    options_column,
                    ft.VerticalDivider(),
                    results_column,
                ],
            )
        )

    # ------------------------------------------------------------------
    # Report generation
    # ------------------------------------------------------------------
    def handle_generate(self, e: ft.Event[ft.Control] = None):
        self.export_status.value = ""
        self.options_error_text.value = ""

        distributor_value = self.distributor_dropdown.value
        distributor_id = (
            None
            if distributor_value in (None, "", ALL_DISTRIBUTORS_KEY)
            else int(distributor_value)
        )
        selected_tags = [cb.data for cb in self.tag_checkboxes if cb.value]

        target_days = _as_float(self.target_days_field.value, DEFAULT_TARGET_DAYS)
        minimum_order_qty = _as_float(self.minimum_order_qty_field.value, DEFAULT_MINIMUM_ORDER_QTY)
        order_multiple = _as_float(self.order_multiple_field.value, DEFAULT_ORDER_MULTIPLE)
        include_zeroed = bool(self.include_zeroed_switch.value)

        if target_days <= 0 or minimum_order_qty < 0 or order_multiple <= 0:
            self.options_error_text.value = (
                "Target stock days and order multiple must be > 0; "
                "minimum order qty must be >= 0"
            )
            self.options_error_text.update()
            return

        items = get_report_items(distributor_id)
        if selected_tags:
            tag_map = get_item_tag_map()
            items = [
                it for it in items
                if all(t in tag_map.get(it["item_id"], []) for t in selected_tags)
            ]

        sales_by_code = get_item_year_sales()

        rows: list[dict] = []
        for it in items:
            daily_rate = selling_power(sales_by_code.get(it["item_code"], {}))
            if daily_rate <= 0 and not include_zeroed:
                continue

            available = int(it["available"] or 0)
            ordered = int(it["ordered"] or 0)

            result = calculate_order(
                annual_sold=daily_rate * 365,
                current_qty=available,
                incoming_qty=ordered,
                target_days=target_days,
                minimum_order_qty=minimum_order_qty,
                order_multiple=order_multiple,
            )

            rows.append({
                "item_code": it["item_code"],
                "item_name": it["item_name"],
                "distributor": it.get("distributor_name") or "",
                "unit_cost": float(it["cost_price"] or 0),
                "sold": int(it["sold"] or 0),
                "available": available,
                "ordered": ordered,
                "daily_rate": round(result["daily_demand"], 3),
                "needs_order": result["should_order"],
                "target_inventory": round(result["target_stock"], 0),
                "quantity": result["qty"],
                "est_cost": round(result["qty"] * float(it["cost_price"] or 0), 2),
            })

        rows.sort(key=lambda r: r["quantity"], reverse=True)
        self.report_rows = rows
        self.results_table.rows = self.build_result_rows(rows)
        self.no_results_text.visible = not rows

        if not rows:
            self.summary_text.value = "No items matched the selected options."
        else:
            total_qty = sum(r["quantity"] for r in rows)
            total_cost = sum(r["est_cost"] for r in rows)
            reorder_count = sum(1 for r in rows if r["needs_order"])
            self.summary_text.value = (
                f"{len(rows)} item(s)  •  {reorder_count} need reordering  •  "
                f"total qty {total_qty:,}  •  est. cost {_fmt_money(total_cost)}"
            )

        self.summary_text.update()
        self.results_list.update()

    def build_result_rows(self, rows: list[dict]) -> list[fdt.DataRow2]:
        table_rows = []
        for r in rows:
            table_rows.append(fdt.DataRow2(
                cells=[
                    ft.DataCell(ft.Text(r["item_code"])),
                    ft.DataCell(ft.Text(r["item_name"])),
                    ft.DataCell(ft.Text(r["distributor"])),
                    ft.DataCell(ft.Text(_fmt_money(r["unit_cost"]))),
                    ft.DataCell(ft.Text(f"{r['sold']:,}")),
                    ft.DataCell(ft.Text(f"{r['available']:,}")),
                    ft.DataCell(ft.Text(f"{r['ordered']:,}")),
                    ft.DataCell(ft.Text(f"{r['daily_rate']:.3f}")),
                    ft.DataCell(ft.Text(
                        "Yes" if r["needs_order"] else "No",
                        color=ft.Colors.ERROR if r["needs_order"] else ft.Colors.GREEN,
                        weight=ft.FontWeight.W_500,
                    )),
                    ft.DataCell(ft.Text(f"{r['target_inventory']:,}")),
                    ft.DataCell(ft.Text(f"{r['quantity']:,}", weight=ft.FontWeight.W_700)),
                    ft.DataCell(ft.Text(_fmt_money(r["est_cost"]))),
                ]
            ))
        return table_rows

    # ------------------------------------------------------------------
    # Excel export
    # ------------------------------------------------------------------
    async def handle_export(self, e: ft.Event[ft.Control] = None):
        if not self.report_rows:
            self.export_status.value = "Generate a report first."
            self.export_status.color = ft.Colors.ERROR
            self.export_status.update()
            return

        path = await ft.FilePicker().save_file(
            dialog_title="Export Order Report",
            file_name="order_report.xlsx",
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["xlsx"],
        )
        if not path:
            return
        if not path.lower().endswith(".xlsx"):
            path += ".xlsx"

        df = pd.DataFrame([
            {
                "Item Code": r["item_code"],
                "Item Name": r["item_name"],
                "Distributor": r["distributor"],
                "Unit Cost": r["unit_cost"],
                "Sold (YTD)": r["sold"],
                "Available": r["available"],
                "Ordered": r["ordered"],
                "Daily Rate": r["daily_rate"],
                "Needs Order": "Yes" if r["needs_order"] else "No",
                "Target Inventory": r["target_inventory"],
                "Recommended Qty": r["quantity"],
                "Est. Cost": r["est_cost"],
            }
            for r in self.report_rows
        ])
        df.to_excel(path, index=False)

        self.export_status.value = f"Exported to {path}"
        self.export_status.color = ft.Colors.GREEN
        self.export_status.update()
