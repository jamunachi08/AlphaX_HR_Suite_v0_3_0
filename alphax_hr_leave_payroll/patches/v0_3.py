from __future__ import annotations

from alphax_hr_leave_payroll.install import (
    ensure_hr_benefit_settings_records,
    seed_default_company_profiles,
)


def execute():
    ensure_hr_benefit_settings_records()
    seed_default_company_profiles()
