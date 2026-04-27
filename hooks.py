from __future__ import annotations

# ── App identity ──────────────────────────────────────────────────────────────
app_name        = "alphax_hr_leave_payroll"
app_title       = "AlphaX HR Suite"
app_publisher   = "AlphaX"
app_description = (
    "KSA-ready HR suite: leave entitlement, EOSB, payroll governance "
    "& reporting for ERPNext/HRMS"
)
app_email       = "support@alphax.example"
app_license     = "MIT"
app_version     = "0.5.0"

# ── Lifecycle ─────────────────────────────────────────────────────────────────
after_install = "alphax_hr_leave_payroll.install.after_install"
after_migrate = "alphax_hr_leave_payroll.install.after_migrate"

# ── Fixtures ──────────────────────────────────────────────────────────────────
fixtures = [
    {
        "dt": "Custom Field",
        "filters": [
            ["name", "in", [
                # Employee
                "Employee-alphax_benefit_section",
                "Employee-tenure_reset_date",
                "Employee-tenure_reset_reason",
                "Employee-tenure_reset_approved_by",
                # Leave Allocation
                "Leave Allocation-alphax_section",
                "Leave Allocation-custom_manual_allocation",
                "Leave Allocation-custom_policy_source",
                "Leave Allocation-custom_service_years",
                "Leave Allocation-custom_entitlement_profile",
                # Salary Slip
                "Salary Slip-alphax_benefit_section",
                "Salary Slip-custom_service_start_date",
                "Salary Slip-custom_service_years",
                "Salary Slip-custom_leave_entitlement_days",
                "Salary Slip-custom_benefit_policy_source",
                "Salary Slip-custom_benefit_profile",
                "Salary Slip-custom_eosb_base_salary",
                "Salary Slip-custom_eosb_eligible_amount",
                "Salary Slip-custom_eosb_note",
            ]]
        ],
    }
]

# ── Document events ───────────────────────────────────────────────────────────
doc_events = {
    "Salary Slip": {
        "validate": "alphax_hr_leave_payroll.api.salary_slip.apply_salary_slip_benefit_preview",
    },
    "Leave Allocation": {
        "validate": "alphax_hr_leave_payroll.api.leave_allocation.apply_leave_policy_on_allocation",
    },
    "Employee": {
        "validate": "alphax_hr_leave_payroll.api.employee.validate_employee_benefit_controls",
    },
}

# ── Scheduled tasks ───────────────────────────────────────────────────────────
scheduler_events = {
    "monthly": [
        "alphax_hr_leave_payroll.utils.scheduler.run_monthly_eosb_provision_snapshot",
    ],
    "weekly": [
        "alphax_hr_leave_payroll.utils.scheduler.send_eosb_liability_alert",
    ],
}
