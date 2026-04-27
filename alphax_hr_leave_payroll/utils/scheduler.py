"""
alphax_hr_leave_payroll.utils.scheduler
=========================================
Scheduled tasks:
  - Monthly EOSB provision snapshot (creates HR EOSB Provision Log records)
  - Weekly EOSB liability alert email to HR Manager users
"""
from __future__ import annotations

import frappe
from frappe.utils import nowdate, flt, fmt_money

from alphax_hr_leave_payroll.utils.policy import (
    get_eosb_amount,
    get_leave_entitlement,
    resolve_benefit_profile,
)


def run_monthly_eosb_provision_snapshot() -> None:
    """
    Loop all active employees and create/update an HR EOSB Provision Log
    record for the current month. Runs on the 1st of each month.
    Idempotent: if a log already exists for this month it is updated.
    """
    if not frappe.db.exists("DocType", "HR EOSB Provision Log"):
        return

    today = nowdate()
    month_key = today[:7]  # YYYY-MM

    employees = frappe.get_all(
        "Employee",
        filters={"status": "Active"},
        fields=["name", "company", "employee_name"],
    )

    for emp in employees:
        try:
            eosb = get_eosb_amount(emp.name, as_of_date=today)
            leave = get_leave_entitlement(emp.name, as_of_date=today)

            existing = frappe.db.get_value(
                "HR EOSB Provision Log",
                {"employee": emp.name, "month_key": month_key},
                "name",
            )

            data = {
                "doctype": "HR EOSB Provision Log",
                "employee": emp.name,
                "company": emp.company,
                "month_key": month_key,
                "snapshot_date": today,
                "service_years": eosb.get("service_years", 0),
                "eosb_amount": eosb.get("amount", 0),
                "base_salary_used": eosb.get("base_salary_used", 0),
                "leave_entitlement_days": leave.get("days", 0),
                "benefit_profile": leave.get("profile") or "",
                "policy_source": leave.get("source") or "",
            }

            if existing:
                doc = frappe.get_doc("HR EOSB Provision Log", existing)
                doc.update(data)
                doc.save(ignore_permissions=True)
            else:
                frappe.get_doc(data).insert(ignore_permissions=True)

        except Exception:
            frappe.log_error(
                title=f"AlphaX EOSB Snapshot failed for {emp.name}",
                message=frappe.get_traceback(),
            )

    frappe.db.commit()


def send_eosb_liability_alert() -> None:
    """
    Send a weekly summary email to all users with the HR Manager role.
    Includes total EOSB liability across all active employees.
    """
    if not frappe.db.exists("DocType", "HR EOSB Provision Log"):
        return

    today = nowdate()
    month_key = today[:7]

    rows = frappe.get_all(
        "HR EOSB Provision Log",
        filters={"month_key": month_key},
        fields=["employee", "company", "eosb_amount", "service_years", "leave_entitlement_days"],
        order_by="eosb_amount desc",
    )

    if not rows:
        return

    total_eosb = sum(flt(r.eosb_amount) for r in rows)
    employee_count = len(rows)

    # Build HTML table for top 10
    table_rows = "".join(
        f"<tr><td>{r.employee}</td><td>{r.company}</td>"
        f"<td>{r.service_years:.2f}</td>"
        f"<td style='text-align:right'>{fmt_money(r.eosb_amount)}</td>"
        f"<td style='text-align:right'>{r.leave_entitlement_days}</td></tr>"
        for r in rows[:10]
    )

    html = f"""
    <h3>AlphaX HR Suite — Weekly EOSB Liability Summary ({today})</h3>
    <p>
      <strong>Total EOSB Liability:</strong> {fmt_money(total_eosb)}<br>
      <strong>Active Employees in snapshot:</strong> {employee_count}
    </p>
    <table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;font-size:13px">
      <thead style="background:#f5f5f5">
        <tr>
          <th>Employee</th><th>Company</th><th>Service Yrs</th>
          <th>EOSB Amount</th><th>Leave Days</th>
        </tr>
      </thead>
      <tbody>{table_rows}</tbody>
    </table>
    {'<p><em>Showing top 10 by EOSB amount. Full data in HR EOSB Provision Log.</em></p>' if employee_count > 10 else ''}
    """

    hr_managers = frappe.get_all(
        "Has Role",
        filters={"role": "HR Manager", "parenttype": "User"},
        pluck="parent",
    )

    for user in hr_managers:
        try:
            frappe.sendmail(
                recipients=[user],
                subject=f"[AlphaX HR] Weekly EOSB Liability — {fmt_money(total_eosb)}",
                message=html,
            )
        except Exception:
            frappe.log_error(
                title=f"AlphaX EOSB alert email failed for {user}",
                message=frappe.get_traceback(),
            )
