# AlphaX HR Suite — v0.5.0

KSA-ready HR governance suite for **ERPNext / Frappe HRMS**.
Covers leave entitlement, EOSB, payroll previews, and compliance reporting.

## Installation

```bash
bench get-app alphax_hr_leave_payroll <path-or-repo>
bench --site your-site install-app alphax_hr_leave_payroll
bench --site your-site migrate
```

## Requirements

- ERPNext / Frappe HRMS v15 or v16
- Python 3.10+
- python-dateutil >= 2.8 (`bench pip install python-dateutil`)

## Features

- 3-tier benefit profile resolution (Employee → Grade → Company)
- KSA Labour Law Art. 109 leave slabs (21 / 30 / 35 days)
- KSA Labour Law Art. 84 EOSB two-tier formula with fractional year proration
- EOSB Settlement DocType (submittable, immutable after submit, on_cancel handler)
- Salary Slip EOSB & leave preview (informational — never affects net pay)
- Leave Allocation auto-calculation with manual override flag
- Tenure reset governance with role-validated approver
- Monthly EOSB provision snapshot (HR EOSB Provision Log)
- Weekly EOSB liability alert email to HR Managers
- Employee EOSB Liability report (Script Report, bar chart, summary)
- Employee Leave Entitlement Matrix report (Script Report, donut chart)
- Whitelisted API endpoints for dashboards and employee self-service
- HR User read-only role on all DocTypes
- 32 standalone unit tests (no Frappe site required)

## Running Tests

```bash
# Standalone — no Frappe site needed
cd alphax_hr_leave_payroll
python -m unittest tests.test_policy -v

# Via bench
bench --site your-site run-tests --app alphax_hr_leave_payroll
```

## Changelog

See CHANGELOG section in the full documentation.
