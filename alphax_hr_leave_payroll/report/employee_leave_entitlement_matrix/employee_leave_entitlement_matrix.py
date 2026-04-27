"""
Employee Leave Entitlement Matrix Report
=========================================
Shows leave entitlement days for all active employees based on their
active benefit profile and service years. Groups by profile and slab.
"""
from __future__ import annotations

import frappe
from frappe.utils import nowdate, flt

from alphax_hr_leave_payroll.utils.policy import get_leave_entitlement


def execute(filters=None):
    filters = filters or {}
    company = filters.get("company")
    as_of   = filters.get("as_of_date") or nowdate()

    columns = _get_columns()
    data    = _get_data(company, as_of)
    chart   = _get_chart(data)
    summary = _get_summary(data)

    return columns, data, None, chart, summary


def _get_columns():
    return [
        {"fieldname": "employee",            "label": "Employee",            "fieldtype": "Link",     "options": "Employee", "width": 130},
        {"fieldname": "employee_name",       "label": "Name",                "fieldtype": "Data",     "width": 160},
        {"fieldname": "company",             "label": "Company",             "fieldtype": "Data",     "width": 120},
        {"fieldname": "department",          "label": "Department",          "fieldtype": "Data",     "width": 130},
        {"fieldname": "designation",         "label": "Designation",         "fieldtype": "Data",     "width": 130},
        {"fieldname": "service_start_date",  "label": "Service Start Date",  "fieldtype": "Date",     "width": 120},
        {"fieldname": "service_years",       "label": "Service Years",       "fieldtype": "Float",    "width": 100, "precision": 2},
        {"fieldname": "entitlement_days",    "label": "Entitlement Days",    "fieldtype": "Float",    "width": 120},
        {"fieldname": "policy_source",       "label": "Policy Source",       "fieldtype": "Data",     "width": 100},
        {"fieldname": "benefit_profile",     "label": "Benefit Profile",     "fieldtype": "Data",     "width": 180},
        {"fieldname": "warning",             "label": "Warning",             "fieldtype": "Small Text","width": 200},
    ]


def _get_data(company, as_of):
    emp_filters = {"status": "Active"}
    if company:
        emp_filters["company"] = company

    employees = frappe.get_all(
        "Employee",
        filters=emp_filters,
        fields=["name", "employee_name", "company", "department", "designation"],
        order_by="company, department, employee_name",
    )

    rows = []
    for emp in employees:
        try:
            result = get_leave_entitlement(emp.name, as_of_date=as_of)
            rows.append({
                "employee":           emp.name,
                "employee_name":      emp.employee_name,
                "company":            emp.company,
                "department":         emp.department or "",
                "designation":        emp.designation or "",
                "service_start_date": result.get("service_start_date"),
                "service_years":      round(flt(result.get("service_years", 0)), 2),
                "entitlement_days":   result.get("days", 0),
                "policy_source":      result.get("source") or "—",
                "benefit_profile":    result.get("profile") or "No profile",
                "warning":            result.get("warning") or "",
            })
        except Exception:
            frappe.log_error(title=f"Leave Entitlement Report: failed for {emp.name}")

    return rows


def _get_chart(data):
    if not data:
        return None

    # Distribution of entitlement day values
    from collections import Counter
    counts = Counter(int(r["entitlement_days"]) for r in data if r["entitlement_days"])
    labels = sorted(counts.keys())
    return {
        "data": {
            "labels":   [str(l) + " days" for l in labels],
            "datasets": [{"name": "Employees", "values": [counts[l] for l in labels]}],
        },
        "type": "donut",
        "title": "Leave Entitlement Distribution",
    }


def _get_summary(data):
    no_profile = [r for r in data if r["benefit_profile"] == "No profile"]
    avg_days = (
        round(sum(flt(r["entitlement_days"]) for r in data) / len(data), 1)
        if data else 0
    )
    return [
        {"label": "Total Employees",         "value": len(data),          "datatype": "Int"},
        {"label": "Without Benefit Profile", "value": len(no_profile),    "datatype": "Int",
         "indicator": "red" if no_profile else "green"},
        {"label": "Avg Entitlement Days",    "value": avg_days,           "datatype": "Float"},
    ]
