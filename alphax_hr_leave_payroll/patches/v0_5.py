from __future__ import annotations

import frappe

from alphax_hr_leave_payroll.install import bootstrap


def execute():
    """
    v0.5 migration patch:
    1. Re-run bootstrap (safe — idempotent).
    2. Backfill encashment_include_housing_allowance from eosb_include_housing_allowance
       on existing profiles that don't yet have the new field set.
    3. Ensure all existing EOSB Settlements have a status value set.
    """
    bootstrap()
    _backfill_encashment_flag()
    _backfill_settlement_status()


def _backfill_encashment_flag():
    """Copy eosb_include_housing_allowance → encashment_include_housing_allowance
    for profiles where the new field is not yet set (migrating from v0.4)."""
    if not frappe.db.exists("DocType", "HR Benefit Profile"):
        return

    profiles = frappe.get_all(
        "HR Benefit Profile",
        filters={"encashment_include_housing_allowance": 0},
        fields=["name", "eosb_include_housing_allowance"],
    )
    for p in profiles:
        if p.eosb_include_housing_allowance:
            frappe.db.set_value(
                "HR Benefit Profile",
                p.name,
                "encashment_include_housing_allowance",
                1,
                update_modified=False,
            )

    frappe.db.commit()


def _backfill_settlement_status():
    """Set status = 'Submitted' for submitted settlements and 'Draft' for drafts."""
    if not frappe.db.exists("DocType", "EOSB Settlement"):
        return

    # docstatus 1 = submitted, 0 = draft, 2 = cancelled
    frappe.db.sql("""
        UPDATE `tabEOSB Settlement`
        SET status = CASE
            WHEN docstatus = 1 THEN 'Submitted'
            WHEN docstatus = 2 THEN 'Cancelled'
            ELSE 'Draft'
        END
        WHERE status IS NULL OR status = ''
    """)
    frappe.db.commit()
