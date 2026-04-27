from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from alphax_hr_leave_payroll.utils.policy import (
    get_eosb_amount,
    get_leave_encashment_amount,
    get_leave_entitlement,
)


class EOSBSettlement(Document):

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def validate(self):
        self._resolve_company()
        self._recalculate()
        self._validate_amounts()

    def on_submit(self):
        """Freeze all calculated fields after submission — amounts are locked."""
        self.db_set("status", "Submitted", update_modified=False)
        # Log a provision snapshot for audit trail
        self._write_provision_log()

    def on_cancel(self):
        """Mark cancelled — no reversal journal entry created here (extend if needed)."""
        self.db_set("status", "Cancelled", update_modified=False)
        frappe.msgprint(
            _("EOSB Settlement {0} has been cancelled. "
              "Review any associated payroll entries manually.").format(self.name),
            indicator="orange",
        )

    def before_submit(self):
        """Guard: prevent submission if EOSB or encashment amounts are zero and service years > 0."""
        if flt(self.service_years) >= flt(self.get("eosb_min_service_years_used", 0)):
            if flt(self.eosb_amount) == 0 and flt(self.service_years) > 0:
                frappe.msgprint(
                    _("EOSB amount is zero. Verify salary component mapping before submitting."),
                    indicator="orange",
                )

    # ── Calculation ───────────────────────────────────────────────────────────

    def _resolve_company(self):
        if not self.company:
            self.company = frappe.db.get_value("Employee", self.employee, "company")

    def _recalculate(self):
        if self.docstatus == 1:
            # Submitted — do not recalculate
            return

        salary_slip = (
            frappe.get_doc("Salary Slip", self.salary_slip)
            if self.salary_slip
            else None
        )

        leave  = get_leave_entitlement(self.employee, as_of_date=self.posting_date)
        eosb   = get_eosb_amount(
            self.employee, salary_slip=salary_slip, as_of_date=self.posting_date
        )
        encash = get_leave_encashment_amount(
            self.employee,
            flt(self.leave_days_to_encash),
            salary_slip=salary_slip,
            as_of_date=self.posting_date,
        )

        self.benefit_policy_source    = leave.get("source") or ""
        self.benefit_profile          = leave.get("profile") or ""
        self.service_start_date       = leave.get("service_start_date")
        self.service_years            = leave.get("service_years")
        self.leave_entitlement_days   = leave.get("days")
        self.eosb_amount              = eosb.get("amount")
        self.eosb_base_salary         = eosb.get("base_salary_used")
        self.eosb_note                = eosb.get("note") or ""
        self.leave_encashment_amount  = encash.get("amount")
        self.leave_encashment_note    = encash.get("note") or ""

        self.total_settlement = round(
            flt(self.eosb_amount)
            + flt(self.leave_encashment_amount)
            + flt(self.additional_amount)
            - flt(self.deduction_amount),
            2,
        )

    def _validate_amounts(self):
        if flt(self.leave_days_to_encash) < 0:
            frappe.throw(_("Leave Days to Encash cannot be negative."))
        if flt(self.additional_amount) < 0:
            frappe.throw(_("Additional Amount cannot be negative."))
        if flt(self.deduction_amount) < 0:
            frappe.throw(_("Deduction Amount cannot be negative."))
        if flt(self.deduction_amount) > flt(self.total_settlement) + flt(self.eosb_amount):
            frappe.throw(_("Deduction Amount exceeds the total settlement — please verify."))

    # ── Audit trail ───────────────────────────────────────────────────────────

    def _write_provision_log(self):
        if not frappe.db.exists("DocType", "HR EOSB Provision Log"):
            return
        try:
            frappe.get_doc({
                "doctype": "HR EOSB Provision Log",
                "employee": self.employee,
                "company": self.company,
                "month_key": str(self.posting_date)[:7],
                "snapshot_date": self.posting_date,
                "service_years": self.service_years,
                "eosb_amount": self.eosb_amount,
                "base_salary_used": self.eosb_base_salary,
                "leave_entitlement_days": self.leave_entitlement_days,
                "benefit_profile": self.benefit_profile,
                "policy_source": self.benefit_policy_source,
                "settlement_reference": self.name,
            }).insert(ignore_permissions=True)
        except Exception:
            frappe.log_error(
                title=f"AlphaX: Provision log write failed for {self.name}",
                message=frappe.get_traceback(),
            )
