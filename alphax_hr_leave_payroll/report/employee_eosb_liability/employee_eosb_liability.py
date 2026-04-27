"""
Employee EOSB Liability Report
==============================
Lists all active employees with their current EOSB liability,
service years, benefit profile, and base salary used.
Grouped by company with subtotals.
"""
from __future__ import annotations

import frappe
from frappe.utils import nowdate, flt

from alphax_hr_leave_payroll.utils.policy import get_eosb_amount, resolve_benefit_profile


def execute(filters=None):
    filters = filters or {}
    company  = filters.get("company")
    as_of    = filters.get("as_of_date") or nowdate()
    min_yrs  = flt(filters.get("min_service_years") or 0)

    columns = _get_columns()
    data    = _get_data(company, as_of, min_yrs)
    chart   = _get_chart(data)
    summary = _get_summary(data)

    return columns, data, None, chart, summary


def _get_columns():
    return [
        {"fieldname": "employee",         "label": "Employee",         "fieldtype": "Link",     "options": "Employee", "width": 130},
        {"fieldname": "employee_name",    "label": "Name",             "fieldtype": "Data",     "width": 160},
        {"fieldname": "company",          "label": "Company",          "fieldtype": "Link",     "options": "Company",  "width": 130},
        {"fieldname": "department",       "label": "Department",       "fieldtype": "Data",     "width": 130},
        {"fieldname": "date_of_joining",  "label": "Date of Joining",  "fieldtype": "Date",     "width": 110},
        {"fieldname": "service_years",    "label": "Service Years",    "fieldtype": "Float",    "width": 100, "precision": 2},
        {"fieldname": "profile",          "label": "Benefit Profile",  "fieldtype": "Data",     "width": 160},
        {"fieldname": "policy_source",    "label": "Policy Source",    "fieldtype": "Data",     "width": 90},
        {"fieldname": "base_salary",      "label": "Base Salary (SAR)","fieldtype": "Currency", "width": 130},
        {"fieldname": "eosb_amount",      "label": "EOSB Amount (SAR)","fieldtype": "Currency", "width": 140},
        {"fieldname": "note",             "label": "Note",             "fieldtype": "Small Text","width": 250},
    ]


def _get_data(company, as_of, min_yrs):
    filters = {"status": "Active"}
    if company:
        filters["company"] = company

    employees = frappe.get_all(
        "Employee",
        filters=filters,
        fields=["name", "employee_name", "company", "department", "date_of_joining"],
        order_by="company, employee_name",
    )

    rows = []
    for emp in employees:
        try:
            result = get_eosb_amount(emp.name, as_of_date=as_of)
            svc_yrs = flt(result.get("service_years", 0))

            if min_yrs and svc_yrs < min_yrs:
                continue

            rows.append({
                "employee":        emp.name,
                "employee_name":   emp.employee_name,
                "company":         emp.company,
                "department":      emp.department or "",
                "date_of_joining": emp.date_of_joining,
                "service_years":   round(svc_yrs, 2),
                "profile":         result.get("source") and result.get("source", "") or "—",
                "policy_source":   result.get("source") or "—",
                "base_salary":     result.get("base_salary_used", 0),
                "eosb_amount":     result.get("amount", 0),
                "note":            result.get("note", ""),
            })
        except Exception:
            frappe.log_error(title=f"EOSB Report: failed for {emp.name}")

    return rows


def _get_chart(data):
    if not data:
        return None

    # Top 10 by EOSB amount
    top10 = sorted(data, key=lambda r: r["eosb_amount"], reverse=True)[:10]
    return {
        "data": {
            "labels":   [r["employee_name"] for r in top10],
            "datasets": [{"name": "EOSB Amount (SAR)", "values": [r["eosb_amount"] for r in top10]}],
        },
        "type": "bar",
        "fieldtype": "Currency",
        "title": "Top 10 Employees by EOSB Liability",
    }


def _get_summary(data):
    total = sum(flt(r["eosb_amount"]) for r in data)
    non_zero = [r for r in data if flt(r["eosb_amount"]) > 0]
    return [
        {"label": "Total Employees",          "value": len(data),      "datatype": "Int"},
        {"label": "Employees with EOSB",      "value": len(non_zero),  "datatype": "Int"},
        {"label": "Total EOSB Liability (SAR)","value": round(total, 2),"datatype": "Currency",
         "indicator": "red" if total > 1_000_000 else "orange" if total > 100_000 else "green"},
    ]
