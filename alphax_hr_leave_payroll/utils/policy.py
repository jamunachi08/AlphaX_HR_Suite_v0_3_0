"""
alphax_hr_leave_payroll.utils.policy
=====================================
Core calculation engine for:
  - Benefit profile resolution  (Employee → Grade → Company hierarchy)
  - Leave entitlement           (KSA Labour Law Art. 109)
  - EOSB amount                 (KSA Labour Law Art. 84, with proration)
  - Leave encashment amount
  - Service year computation    (dateutil.relativedelta for leap-year accuracy)

All functions are pure / side-effect-free except for DB reads.
Caching uses frappe.local to avoid repeated DB hits within one request.
"""
from __future__ import annotations

import frappe
from frappe.utils import flt, getdate, nowdate

# python-dateutil for accurate year fractions (avoids 365-day drift)
try:
    from dateutil.relativedelta import relativedelta  # type: ignore
    _DATEUTIL = True
except ImportError:
    _DATEUTIL = False


# ── Settings ──────────────────────────────────────────────────────────────────

def get_settings():
    """Return the HR Benefit Settings singleton (or None if DocType absent)."""
    if not frappe.db.exists("DocType", "HR Benefit Settings"):
        return None
    return frappe.get_single("HR Benefit Settings")


# ── Service date / years ──────────────────────────────────────────────────────

def get_service_start_date(employee_doc, profile=None):
    """
    Determine the service start date based on profile or global settings.

    Priority:
      1. Profile.service_start_basis
      2. HR Benefit Settings.default_service_start_basis
      3. Fallback → Date of Joining
    """
    settings = get_settings()
    mode = (
        (profile.service_start_basis if profile else None)
        or (getattr(settings, "default_service_start_basis", None) if settings else None)
        or "Date of Joining"
    )

    tenure_reset = employee_doc.get("tenure_reset_date")

    if mode == "Tenure Reset Date" and tenure_reset:
        return getdate(tenure_reset)
    if mode == "Tenure Reset Date if Available" and tenure_reset:
        return getdate(tenure_reset)

    doj = employee_doc.get("date_of_joining")
    if not doj:
        frappe.throw(
            frappe._("Employee {0} has no Date of Joining set.").format(
                employee_doc.get("name") or employee_doc.get("employee_name", "")
            )
        )
    return getdate(doj)


def get_service_years(employee_doc, profile=None, as_of_date=None) -> float:
    """
    Return fractional service years with leap-year accuracy.

    Uses dateutil.relativedelta when available; falls back to days/365.25.
    Returns 0.0 if start_date is in the future or employee has no DOJ.
    """
    try:
        start_date = get_service_start_date(employee_doc, profile)
    except Exception:
        return 0.0

    end_date = getdate(as_of_date or nowdate())

    if not start_date or end_date < start_date:
        return 0.0

    if _DATEUTIL:
        rd = relativedelta(end_date, start_date)
        # Full years + fractional month + fractional day within that month
        days_in_partial_month = 30  # approximate
        fraction = (rd.months + rd.days / days_in_partial_month) / 12.0
        return round(rd.years + fraction, 4)
    else:
        return round((end_date - start_date).days / 365.25, 4)


# ── Profile resolution (with request-level cache) ─────────────────────────────

_CACHE_KEY = "alphax_benefit_profile_cache"


def _get_cache() -> dict:
    if not hasattr(frappe.local, _CACHE_KEY):
        setattr(frappe.local, _CACHE_KEY, {})
    return getattr(frappe.local, _CACHE_KEY)


def resolve_benefit_profile(employee: str, company: str | None = None):
    """
    Resolve the active HR Benefit Profile for an employee.

    Hierarchy (first match wins):
      1. Employee-level profile
      2. Grade-level profile
      3. Company-level profile

    Returns (HRBenefitProfile doc | None, level str | None).
    Results are cached per request to avoid repeated DB hits when both
    leave and EOSB are calculated for the same employee in one request cycle.
    """
    cache = _get_cache()
    cache_key = f"{employee}:{company or ''}"
    if cache_key in cache:
        return cache[cache_key]

    emp = frappe.get_doc("Employee", employee)
    company = company or emp.company
    grade = emp.get("grade")

    checks = [
        ("Employee", {"employee": employee}),
        ("Grade",    {"grade": grade} if grade else None),
        ("Company",  {"company": company}),
    ]

    result = (None, None)
    for level, extra in checks:
        if not extra:
            continue
        filters = {"is_active": 1, "assignment_level": level}
        filters.update(extra)
        names = frappe.get_all(
            "HR Benefit Profile",
            filters=filters,
            pluck="name",
            order_by="modified desc",
            limit=1,
        )
        if names:
            result = (frappe.get_doc("HR Benefit Profile", names[0]), level)
            break

    cache[cache_key] = result
    return result


# ── Leave entitlement ─────────────────────────────────────────────────────────

def _match_slab(slabs, years: float) -> float:
    """
    Single-pass slab lookup. Returns the annual_leave_days for the matching
    slab. Uses a clean match-and-break approach — no dual-branch ambiguity.

    Slabs are expected sorted by from_year ascending (caller's responsibility).
    The last open-ended slab (to_year empty / None) matches ≥ from_year.
    """
    for row in slabs:
        from_year = flt(row.from_year)
        to_year_raw = row.to_year
        to_year = flt(to_year_raw) if to_year_raw not in (None, "", 0) else None

        if to_year is None:
            # Open-ended final slab
            if years >= from_year:
                return flt(row.annual_leave_days)
        else:
            if from_year <= years < to_year:
                return flt(row.annual_leave_days)

    return 0.0


def get_leave_entitlement(employee: str, as_of_date=None) -> dict:
    """
    Return leave entitlement details for an employee.

    Result keys:
      days, profile, source, service_years, service_start_date
    """
    emp = frappe.get_doc("Employee", employee)
    profile, source = resolve_benefit_profile(employee, emp.company)
    years = get_service_years(emp, profile=profile, as_of_date=as_of_date)
    start_date = get_service_start_date(emp, profile)

    if not profile:
        return {
            "days": 0,
            "profile": None,
            "source": None,
            "service_years": years,
            "service_start_date": start_date,
            "warning": "No active HR Benefit Profile found for this employee.",
        }

    sorted_slabs = sorted(profile.service_slabs, key=lambda d: flt(d.from_year))
    days = _match_slab(sorted_slabs, years)

    return {
        "days": days,
        "profile": profile.name,
        "source": source,
        "service_years": years,
        "service_start_date": start_date,
        "warning": None,
    }


# ── Salary component helpers ──────────────────────────────────────────────────

def _get_salary_component_amount(salary_slip, component_name: str | None) -> float:
    if not salary_slip or not component_name:
        return 0.0
    return sum(
        flt(row.amount)
        for row in (salary_slip.get("earnings") or [])
        if row.salary_component == component_name
    )


def get_daily_salary_amount(monthly_amount: float, settings=None) -> float:
    working_days = flt(
        getattr(settings, "default_working_days_per_month", 30) if settings else 30
    ) or 30
    return flt(monthly_amount) / working_days


def _resolve_base_salary(profile, salary_slip, settings, use_housing_flag: str) -> tuple[float, float, float]:
    """
    Return (basic, housing, base) based on profile component mappings.

    use_housing_flag: profile field name controlling whether housing is included.
    """
    basic_comp   = profile.basic_salary_component or (
        settings.default_basic_salary_component if settings else None
    )
    housing_comp = profile.housing_allowance_component or (
        settings.default_housing_allowance_component if settings else None
    )

    basic   = _get_salary_component_amount(salary_slip, basic_comp)
    housing = _get_salary_component_amount(salary_slip, housing_comp)
    include_housing = bool(getattr(profile, use_housing_flag, False))
    base = basic + (housing if include_housing else 0.0)
    return basic, housing, base


# ── EOSB amount (KSA Labour Law Art. 84) ─────────────────────────────────────

def get_eosb_amount(employee: str, salary_slip=None, as_of_date=None) -> dict:
    """
    Calculate End of Service Benefit (EOSB) per KSA Labour Law Art. 84.

    Rules:
      - < min_service_years  → 0
      - min_service to half_limit → (base / 2) × years        [half-month/year]
      - > half_limit          → (base/2 × half_limit) + base × (years − half_limit)

    Fractional years are preserved throughout (handled by get_service_years).
    """
    emp = frappe.get_doc("Employee", employee)
    profile, source = resolve_benefit_profile(employee, emp.company)
    settings = get_settings()
    years = get_service_years(emp, profile=profile, as_of_date=as_of_date)

    if not profile:
        return {
            "amount": 0.0, "source": None, "service_years": years,
            "note": "No active HR Benefit Profile found.",
            "base_salary_used": 0.0, "basic_used": 0.0, "housing_used": 0.0,
        }

    basic, housing, base = _resolve_base_salary(
        profile, salary_slip, settings, "eosb_include_housing_allowance"
    )

    if not base:
        return {
            "amount": 0.0, "source": source, "service_years": years,
            "note": "EOSB base salary is zero — check salary component mapping in HR Benefit Profile.",
            "base_salary_used": 0.0, "basic_used": basic, "housing_used": housing,
        }

    min_years  = flt(profile.eosb_min_service_years  or (getattr(settings, "default_eosb_min_service_years",  2) if settings else 2) or 2)
    half_limit = flt(profile.eosb_half_month_limit_years or (getattr(settings, "default_eosb_half_month_limit_years", 5) if settings else 5) or 5)

    if years < min_years:
        amount = 0.0
        note = (
            f"Service years ({years:.2f}) is below the minimum ({min_years}) — "
            "EOSB not granted under current policy."
        )
    elif years <= half_limit:
        amount = (base / 2.0) * years
        note = (
            f"Half-month salary per year for {years:.2f} years "
            f"(below the {half_limit}-year full-month threshold)."
        )
    else:
        half_portion = (base / 2.0) * half_limit
        full_portion = base * (years - half_limit)
        amount = half_portion + full_portion
        note = (
            f"Half-month salary × {half_limit} years + "
            f"full-month salary × {years - half_limit:.2f} years "
            f"(Art. 84 two-tier formula)."
        )

    return {
        "amount": round(amount, 2),
        "source": source,
        "service_years": years,
        "note": note,
        "base_salary_used": round(base, 2),
        "basic_used": round(basic, 2),
        "housing_used": round(housing, 2),
    }


# ── Leave encashment ──────────────────────────────────────────────────────────

def get_leave_encashment_amount(
    employee: str,
    leave_days: float,
    salary_slip=None,
    as_of_date=None,
) -> dict:
    """
    Calculate leave encashment amount.

    Uses a SEPARATE housing-inclusion flag (encashment_include_housing_allowance)
    distinct from the EOSB flag, because KSA law may treat the bases differently.
    The cap is profile.max_leave_encashment_days (0 = no cap).
    """
    emp = frappe.get_doc("Employee", employee)
    profile, source = resolve_benefit_profile(employee, emp.company)
    settings = get_settings()

    if not profile or not flt(leave_days):
        return {
            "amount": 0.0, "source": source,
            "note": "No leave encashment calculated (no profile or zero leave days).",
            "effective_days": 0.0, "daily_rate": 0.0,
        }

    if not profile.enable_leave_encashment:
        return {
            "amount": 0.0, "source": source,
            "note": "Leave encashment is disabled in the active benefit profile.",
            "effective_days": 0.0, "daily_rate": 0.0,
        }

    _basic, _housing, monthly = _resolve_base_salary(
        profile, salary_slip, settings, "encashment_include_housing_allowance"
    )

    daily = get_daily_salary_amount(monthly, settings)
    cap   = flt(profile.max_leave_encashment_days or 0)
    effective_days = min(flt(leave_days), cap) if cap else flt(leave_days)
    amount = round(daily * effective_days, 2)

    note = (
        f"Daily rate (SAR {round(daily, 2)}) × {effective_days} days"
        + (f" (capped from {leave_days} days)" if cap and flt(leave_days) > cap else "")
        + "."
    )

    return {
        "amount": amount,
        "source": source,
        "note": note,
        "effective_days": effective_days,
        "daily_rate": round(daily, 2),
        "base_salary_used": round(monthly, 2),
    }
