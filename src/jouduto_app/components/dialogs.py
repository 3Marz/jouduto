"""Reusable dialog controls shared across pages.

Previously each page that deleted a distributor/item/PO declared its own nearly
identical `ft.AlertDialog("Are you sure?")` inline. This is the one place those
confirmations live now, so the phrasing/behavior stays identical everywhere and
the pages just hand it a title, a message, and a callback.
"""

import flet as ft


def confirm_delete(
    *,
    title: str = "Are you sure?",
    message: str = "This will be deleted permanently.",
    confirm_text: str = "Delete",
    deny_text: str = "Cancel",
    on_confirm,
) -> ft.AlertDialog:
    """Build a modal confirm-dialog for destructive actions.

    Args:
        title: Heading shown at the top of the dialog.
        message: Body copy describing exactly what will be removed.
        confirm_text: Label of the destructive (primary) button.
        deny_text: Label of the safe (dismiss) button.
        on_confirm: Callable invoked when the destructive button is clicked.
            It is called with the event; pages typically pop the dialog here
            then perform the delete.

    Example:
        self.confirm_delete_dialog = confirm_delete(
            message="This will permanently remove the distributor.",
            on_confirm=self.handle_delete,
        )
    """
    return ft.AlertDialog(
        modal=True,
        title=ft.Text(title),
        content=ft.Text(message),
        alignment=ft.Alignment.CENTER,
        actions=[
            ft.Button(confirm_text, on_click=on_confirm),
            ft.Button(
                deny_text,
                on_click=lambda e: e.control.page.pop_dialog(),
            ),
        ],
    )
