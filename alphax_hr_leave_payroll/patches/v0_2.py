from __future__ import annotations

import frappe


def execute():
    """
    v0.2 patch — seed HR Benefit Settings singleton if absent.
    FIX: was named after_install_seed() — Frappe patch runner requires execute().
    """
    if not frappe.db.exists("DocType", "HR Benefit Settings"):
        return
    if not frappe.db.exists("HR Benefit Settings", "HR Benefit Settings"):
        doc = frappe.get_doc({"doctype": "HR Benefit Settings"})
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
