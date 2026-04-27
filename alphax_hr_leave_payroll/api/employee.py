from __future__ import annotations

import frappe
from frappe import _


def validate_employee_benefit_controls(doc, method=None):
    """
    Validate tenure reset governance controls on Employee save.

    Rules (configurable via HR Benefit Settings):
      1. Tenure Reset Reason is mandatory when reset date is set.
      2. Tenure Reset Approved By is mandatory when approval is required.
      3. Approver must not be the employee themselves.
      4. Approver must hold the HR Manager role.
    """
    if not getattr(doc, "tenure_reset_date", None):
        return

    settings = None
    if frappe.db.exists("DocType", "HR Benefit Settings"):
        settings = frappe.get_single("HR Benefit Settings")

    require_reason   = int(getattr(settings, "require_tenure_reset_reason",   1) if settings else 1)
    require_approval = int(getattr(settings, "enable_tenure_reset_approval",  1) if settings else 1)

    if require_reason and not getattr(doc, "tenure_reset_reason", None):
        frappe.throw(_(
            "Tenure Reset Reason is mandatory when a Service Tenure Reset Date is set."
        ))

    if require_approval:
        approver = getattr(doc, "tenure_reset_approved_by", None)
        if not approver:
            frappe.throw(_(
                "Tenure Reset Approved By is mandatory when Service Tenure Reset Date is set."
            ))

        # Approver must not be the employee's own user account
        emp_user = frappe.db.get_value("Employee", doc.name, "user_id")
        if emp_user and approver == emp_user:
            frappe.throw(_(
                "The tenure reset approver cannot be the employee's own user account."
            ))

        # Approver must hold HR Manager or System Manager role
        approver_roles = frappe.get_roles(approver)
        if not ({"HR Manager", "System Manager"} & set(approver_roles)):
            frappe.throw(_(
                "Tenure Reset Approved By must be a user with the HR Manager or System Manager role. "
                f"User '{approver}' does not qualify."
            ))
