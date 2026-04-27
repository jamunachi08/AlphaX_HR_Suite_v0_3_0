from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class HRBenefitProfile(Document):

    def validate(self):
        self._validate_assignment_fields()
        self._validate_service_slabs()
        self._validate_eosb_settings()
        self._validate_single_active_policy()

    # ── Field validators ──────────────────────────────────────────────────────

    def _validate_assignment_fields(self):
        if self.assignment_level == "Employee" and not self.employee:
            frappe.throw(_("Employee is mandatory when Assignment Level is Employee."))
        if self.assignment_level == "Grade" and not self.grade:
            frappe.throw(_("Grade is mandatory when Assignment Level is Grade."))
        if self.assignment_level == "Company" and not self.company:
            frappe.throw(_("Company is mandatory when Assignment Level is Company."))
        if not self.service_slabs:
            frappe.throw(_("At least one service slab is required."))

    def _validate_service_slabs(self):
        rows = sorted(self.service_slabs, key=lambda d: flt(d.from_year))
        last_to = None
        open_slab_seen = False

        for idx, row in enumerate(rows, start=1):
            from_year = flt(row.from_year)
            to_year_raw = row.to_year
            to_year = flt(to_year_raw) if to_year_raw not in (None, "", 0) else None
            days = flt(row.annual_leave_days)

            if from_year < 0:
                frappe.throw(_(f"From Year cannot be negative (row {idx})."))
            if days <= 0:
                frappe.throw(_(f"Annual Leave Days must be positive (row {idx})."))
            if to_year is not None and to_year <= from_year:
                frappe.throw(_(f"To Year must be greater than From Year (row {idx})."))
            if last_to is not None and from_year < last_to:
                frappe.throw(_(f"Service slabs must be ordered and non-overlapping (row {idx})."))
            if open_slab_seen:
                frappe.throw(_(f"An open-ended slab (no To Year) must be the last row (row {idx} follows one)."))

            if to_year is None:
                open_slab_seen = True
                last_to = 999999.0
            else:
                last_to = to_year

    def _validate_eosb_settings(self):
        min_yrs   = flt(self.eosb_min_service_years)
        half_lmt  = flt(self.eosb_half_month_limit_years)
        if min_yrs < 0:
            frappe.throw(_("EOSB Minimum Service Years cannot be negative."))
        if half_lmt < 0:
            frappe.throw(_("Half-Month Salary Limit Years cannot be negative."))
        if half_lmt and min_yrs > half_lmt:
            frappe.throw(_(
                "EOSB Minimum Service Years cannot exceed Half-Month Salary Limit Years."
            ))

    def _validate_single_active_policy(self):
        if not self.is_active:
            return

        filters = {
            "name": ["!=", self.name],
            "is_active": 1,
            "assignment_level": self.assignment_level,
        }
        if self.assignment_level == "Employee":
            filters["employee"] = self.employee
        elif self.assignment_level == "Grade":
            filters["grade"] = self.grade
        elif self.assignment_level == "Company":
            filters["company"] = self.company

        if frappe.db.exists("HR Benefit Profile", filters):
            frappe.throw(_(
                "Only one active HR Benefit Profile is allowed per assignment target. "
                "Please deactivate the existing profile before activating this one."
            ))
