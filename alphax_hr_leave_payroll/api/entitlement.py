"""
alphax_hr_leave_payroll.api.entitlement
=========================================
Whitelisted API endpoints for:
  - Leave entitlement preview (no document required)
  - EOSB preview (no document required)
  - Full benefit summary (both combined)

These endpoints are safe for self-service portal use.
"""
from __future__ import annotations

import frappe
from frappe.utils import nowdate

from alphax_hr_leave_payroll.utils.policy import (
    get_eosb_amount,
    get_leave_encashment_amount,
    get_leave_entitlement,
)


@frappe.whitelist()
def get_employee_benefit_summary(employee: str, as_of_date: str | None = None) -> dict:
    """
    Return a full benefit summary for an employee.

    Permissions: The calling user must be an HR Manager, System Manager,
    or the employee's own linked user.

    Usage (from JS or portal):
      frappe.call("alphax_hr_leave_payroll.api.entitlement.get_employee_benefit_summary",
                  {employee: "EMP-0001"})
    """
    _assert_access(employee)

    today = as_of_date or nowdate()
    leave  = get_leave_entitlement(employee, as_of_date=today)
    eosb   = get_eosb_amount(employee, as_of_date=today)

    return {
        "employee": employee,
        "as_of_date": today,
        "leave": leave,
        "eosb": eosb,
    }


@frappe.whitelist()
def get_leave_entitlement_preview(employee: str, as_of_date: str | None = None) -> dict:
    """Return leave entitlement details for an employee."""
    _assert_access(employee)
    return get_leave_entitlement(employee, as_of_date=as_of_date or nowdate())


@frappe.whitelist()
def get_eosb_preview(employee: str, as_of_date: str | None = None) -> dict:
    """Return EOSB calculation details for an employee."""
    _assert_access(employee)
    return get_eosb_amount(employee, as_of_date=as_of_date or nowdate())


@frappe.whitelist()
def get_leave_encashment_preview(
    employee: str,
    leave_days: float,
    as_of_date: str | None = None,
) -> dict:
    """Return leave encashment calculation for a given number of days."""
    _assert_access(employee)
    return get_leave_encashment_amount(
        employee, float(leave_days), as_of_date=as_of_date or nowdate()
    )


@frappe.whitelist()
def get_company_eosb_exposure(company: str) -> dict:
    """
    Return total EOSB liability for all active employees in a company.
    Requires HR Manager role.
    """
    if "HR Manager" not in frappe.get_roles() and "System Manager" not in frappe.get_roles():
        frappe.throw(frappe._("HR Manager role required."), frappe.PermissionError)

    employees = frappe.get_all(
        "Employee",
        filters={"company": company, "status": "Active"},
        pluck="name",
    )

    total = 0.0
    breakdown = []
    for emp in employees:
        try:
            result = get_eosb_amount(emp, as_of_date=nowdate())
            total += result.get("amount", 0)
            breakdown.append({
                "employee": emp,
                "service_years": result.get("service_years"),
                "eosb_amount": result.get("amount"),
                "source": result.get("source"),
            })
        except Exception:
            frappe.log_error(title=f"EOSB exposure calc failed for {emp}")

    return {
        "company": company,
        "total_eosb_liability": round(total, 2),
        "employee_count": len(breakdown),
        "breakdown": sorted(breakdown, key=lambda x: x["eosb_amount"], reverse=True),
    }


# ── Access control helper ─────────────────────────────────────────────────────

def _assert_access(employee: str) -> None:
    """Allow HR Manager, System Manager, or the employee's own linked user."""
    roles = set(frappe.get_roles())
    if {"HR Manager", "System Manager", "HR User"} & roles:
        return

    emp_user = frappe.db.get_value("Employee", employee, "user_id")
    if emp_user and emp_user == frappe.session.user:
        return

    frappe.throw(
        frappe._("You do not have permission to view benefit details for {0}.").format(employee),
        frappe.PermissionError,
    )
