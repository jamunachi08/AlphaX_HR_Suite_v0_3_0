from __future__ import annotations

import frappe


def after_install() -> None:
    bootstrap()


def after_migrate() -> None:
    bootstrap()


def bootstrap() -> None:
    ensure_hr_benefit_settings_records()
    seed_default_company_profiles()


# ── Settings singleton ────────────────────────────────────────────────────────

def ensure_hr_benefit_settings_records() -> None:
    if not frappe.db.exists("DocType", "HR Benefit Settings"):
        return
    if not frappe.db.exists("HR Benefit Settings", "HR Benefit Settings"):
        doc = frappe.get_doc({"doctype": "HR Benefit Settings"})
        doc.insert(ignore_permissions=True)
        frappe.db.commit()


# ── Default company profiles ──────────────────────────────────────────────────

def seed_default_company_profiles() -> None:
    if not frappe.db.exists("DocType", "HR Benefit Profile"):
        return

    companies = frappe.get_all("Company", pluck="name")
    for company in companies:
        # Guard: skip if ANY (active or inactive) company-level profile exists
        if frappe.db.exists(
            "HR Benefit Profile",
            {"company": company, "assignment_level": "Company"},
        ):
            continue

        profile_name = f"{company} - KSA Standard Policy"
        doc = frappe.get_doc(
            {
                "doctype": "HR Benefit Profile",
                "profile_name": profile_name,
                "is_active": 1,
                "company": company,
                "assignment_level": "Company",
                "service_start_basis": "Tenure Reset Date if Available",
                # EOSB — KSA Labour Law Art. 84 defaults
                "eosb_min_service_years": 2,
                "eosb_half_month_limit_years": 5,
                "eosb_include_housing_allowance": 0,
                "encashment_include_housing_allowance": 0,
                # Leave encashment
                "enable_leave_encashment": 1,
                "max_leave_encashment_days": 30,
                # KSA Labour Law leave slabs (Art. 109)
                "service_slabs": [
                    {"from_year": 0, "to_year": 3,  "annual_leave_days": 21},
                    {"from_year": 3, "to_year": 5,  "annual_leave_days": 30},
                    {"from_year": 5, "to_year": None, "annual_leave_days": 35},
                ],
            }
        )
        doc.insert(ignore_permissions=True)

    frappe.db.commit()
