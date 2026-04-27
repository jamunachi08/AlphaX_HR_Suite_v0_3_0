from __future__ import annotations

import frappe

from alphax_hr_leave_payroll.utils.policy import get_leave_entitlement


def apply_leave_policy_on_allocation(doc, method=None):
    """
    Populate leave entitlement days on Leave Allocation from the active
    HR Benefit Profile.

    MANUAL OVERRIDE GUARD: If the custom_manual_allocation flag is checked,
    the auto-calculation is skipped and the HR manager's value is preserved.

    Errors are caught and logged; they never block the Leave Allocation save.
    """
    if not getattr(doc, "employee", None):
        return

    # Respect manual override
    if getattr(doc, "custom_manual_allocation", False):
        return

    try:
        result = get_leave_entitlement(
            doc.employee,
            as_of_date=doc.from_date or doc.to_date,
        )

        if result.get("days"):
            doc.new_leaves_allocated = result["days"]

        _set(doc, "custom_policy_source",       result.get("source"))
        _set(doc, "custom_service_years",        result.get("service_years"))
        _set(doc, "custom_entitlement_profile",  result.get("profile"))

        # Warn HR if no profile was found
        if result.get("warning"):
            frappe.msgprint(
                result["warning"],
                title="AlphaX HR — Benefit Profile Warning",
                indicator="orange",
            )

    except Exception:
        frappe.log_error(
            title=f"AlphaX: Leave Allocation policy apply failed ({doc.name})",
            message=frappe.get_traceback(),
        )


def _set(doc, field: str, value):
    if hasattr(doc, field):
        setattr(doc, field, value)
