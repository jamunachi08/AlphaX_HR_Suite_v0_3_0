from __future__ import annotations

import frappe

from alphax_hr_leave_payroll.utils.policy import get_eosb_amount, get_leave_entitlement


def apply_salary_slip_benefit_preview(doc, method=None):
    """
    Populate the AlphaX custom fields on Salary Slip with leave entitlement
    and EOSB preview data. These are informational fields only — they do not
    affect net pay or payroll components.

    Errors are caught and logged; they never block the Salary Slip save.
    """
    if not doc.employee:
        return

    try:
        as_of = doc.end_date or doc.start_date
        leave_result = get_leave_entitlement(doc.employee, as_of_date=as_of)
        eosb_result  = get_eosb_amount(doc.employee, salary_slip=doc, as_of_date=as_of)

        _set(doc, "custom_service_start_date",    leave_result.get("service_start_date"))
        _set(doc, "custom_service_years",         leave_result.get("service_years"))
        _set(doc, "custom_leave_entitlement_days", leave_result.get("days"))
        _set(doc, "custom_benefit_policy_source", leave_result.get("source"))
        _set(doc, "custom_benefit_profile",       leave_result.get("profile"))
        _set(doc, "custom_eosb_base_salary",      eosb_result.get("base_salary_used"))
        _set(doc, "custom_eosb_eligible_amount",  eosb_result.get("amount"))
        _set(doc, "custom_eosb_note",             eosb_result.get("note"))

    except Exception:
        frappe.log_error(
            title=f"AlphaX: Salary Slip benefit preview failed ({doc.name})",
            message=frappe.get_traceback(),
        )


def _set(doc, field: str, value):
    if hasattr(doc, field):
        setattr(doc, field, value)
