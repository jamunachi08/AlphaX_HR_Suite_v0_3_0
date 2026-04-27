"""
tests/test_policy.py
======================
Unit tests for alphax_hr_leave_payroll.utils.policy

Run with:
    bench --site your-site run-tests --app alphax_hr_leave_payroll

Or standalone (mock frappe):
    python -m pytest tests/test_policy.py -v
"""
from __future__ import annotations

import sys
import types
import unittest
from datetime import date
from unittest.mock import MagicMock, patch


# ── Minimal frappe mock so tests run without a Frappe site ────────────────────

def _build_frappe_mock():
    frappe = types.ModuleType("frappe")
    frappe.utils = types.ModuleType("frappe.utils")
    frappe.utils.flt = lambda v, precision=None: float(v or 0)
    frappe.utils.getdate = lambda v: (
        v if isinstance(v, date) else date.fromisoformat(str(v)) if v else None
    )
    frappe.utils.nowdate = lambda: "2025-01-01"
    frappe.local = MagicMock()
    frappe._ = lambda s, *a, **kw: s
    frappe.throw = lambda msg, *a, **kw: (_ for _ in ()).throw(ValueError(msg))
    frappe.db = MagicMock()
    frappe.db.exists = MagicMock(return_value=False)
    frappe.get_doc = MagicMock()
    frappe.get_all = MagicMock(return_value=[])
    frappe.get_single = MagicMock(return_value=None)
    frappe.log_error = MagicMock()
    frappe.msgprint = MagicMock()
    return frappe


_frappe = _build_frappe_mock()
sys.modules.setdefault("frappe", _frappe)
sys.modules.setdefault("frappe.utils", _frappe.utils)
sys.modules.setdefault("frappe.model", types.ModuleType("frappe.model"))
sys.modules.setdefault("frappe.model.document", types.ModuleType("frappe.model.document"))


# ── Import the module under test ──────────────────────────────────────────────

from alphax_hr_leave_payroll.utils import policy  # noqa: E402


# ── Helper factories ──────────────────────────────────────────────────────────

def _emp(doj="2018-01-01", tenure_reset=None):
    e = MagicMock()
    e.get = lambda k, default=None: {
        "date_of_joining": doj,
        "tenure_reset_date": tenure_reset,
        "name": "EMP-0001",
    }.get(k, default)
    e.company = "Test Co"
    e.name = "EMP-0001"
    return e


def _slab(from_year, to_year, days):
    s = MagicMock()
    s.from_year = from_year
    s.to_year = to_year
    s.annual_leave_days = days
    return s


def _profile(slabs, min_yrs=2, half_limit=5, include_housing=False,
             encash_housing=False, encash_enabled=True, max_encash=0):
    p = MagicMock()
    p.service_slabs = slabs
    p.service_start_basis = "Date of Joining"
    p.eosb_min_service_years = min_yrs
    p.eosb_half_month_limit_years = half_limit
    p.eosb_include_housing_allowance = include_housing
    p.encashment_include_housing_allowance = encash_housing
    p.enable_leave_encashment = encash_enabled
    p.max_leave_encashment_days = max_encash
    p.basic_salary_component = "Basic"
    p.housing_allowance_component = "Housing"
    p.name = "Test Profile"
    return p


# ── Service year tests ────────────────────────────────────────────────────────

class TestGetServiceYears(unittest.TestCase):

    def test_zero_when_no_doj(self):
        emp = _emp(doj=None)
        # Should return 0.0 gracefully without raising
        result = policy.get_service_years(emp, as_of_date="2025-01-01")
        self.assertEqual(result, 0.0)

    def test_zero_when_future_doj(self):
        emp = _emp(doj="2030-01-01")
        result = policy.get_service_years(emp, as_of_date="2025-01-01")
        self.assertEqual(result, 0.0)

    def test_exactly_five_years(self):
        emp = _emp(doj="2020-01-01")
        result = policy.get_service_years(emp, as_of_date="2025-01-01")
        self.assertAlmostEqual(result, 5.0, delta=0.05)

    def test_tenure_reset_overrides_doj(self):
        emp = _emp(doj="2010-01-01", tenure_reset="2022-01-01")
        profile = MagicMock()
        profile.service_start_basis = "Tenure Reset Date if Available"
        result = policy.get_service_years(emp, profile=profile, as_of_date="2025-01-01")
        # Should be ~3 years from 2022, not 15 from 2010
        self.assertAlmostEqual(result, 3.0, delta=0.1)

    def test_fractional_years(self):
        emp = _emp(doj="2022-07-01")
        result = policy.get_service_years(emp, as_of_date="2025-01-01")
        # 2.5 years approximately
        self.assertGreater(result, 2.4)
        self.assertLess(result, 2.6)


# ── Slab matching tests ───────────────────────────────────────────────────────

class TestMatchSlab(unittest.TestCase):

    KSA_SLABS = [
        _slab(0, 3, 21),
        _slab(3, 5, 30),
        _slab(5, None, 35),
    ]

    def test_slab_0_to_3(self):
        self.assertEqual(policy._match_slab(self.KSA_SLABS, 0.0), 21)
        self.assertEqual(policy._match_slab(self.KSA_SLABS, 1.5), 21)
        self.assertEqual(policy._match_slab(self.KSA_SLABS, 2.99), 21)

    def test_slab_boundary_exactly_3(self):
        # At exactly 3 years → must fall into [3,5) slab
        self.assertEqual(policy._match_slab(self.KSA_SLABS, 3.0), 30)

    def test_slab_3_to_5(self):
        self.assertEqual(policy._match_slab(self.KSA_SLABS, 4.0), 30)
        self.assertEqual(policy._match_slab(self.KSA_SLABS, 4.99), 30)

    def test_slab_boundary_exactly_5(self):
        # At exactly 5 years → must fall into open-ended [5,∞) slab
        self.assertEqual(policy._match_slab(self.KSA_SLABS, 5.0), 35)

    def test_slab_above_5(self):
        self.assertEqual(policy._match_slab(self.KSA_SLABS, 10.0), 35)
        self.assertEqual(policy._match_slab(self.KSA_SLABS, 30.0), 35)

    def test_no_match_returns_zero(self):
        slabs = [_slab(5, 10, 35)]  # gap: no slab for < 5 years
        self.assertEqual(policy._match_slab(slabs, 2.0), 0.0)

    def test_single_open_slab(self):
        slabs = [_slab(0, None, 21)]
        self.assertEqual(policy._match_slab(slabs, 0.0), 21)
        self.assertEqual(policy._match_slab(slabs, 100.0), 21)

    def test_no_double_match_on_boundary(self):
        """Critical regression: verify single-pass — boundary value hits exactly one slab."""
        hit_count = [0]
        orig = policy._match_slab

        slabs = self.KSA_SLABS
        # Simulate 3.0 years — must return exactly 30 (second slab), not 21 (first)
        result = policy._match_slab(slabs, 3.0)
        self.assertEqual(result, 30, "Boundary 3.0 must match [3,5) slab (30 days)")


# ── EOSB calculation tests ────────────────────────────────────────────────────

class TestGetEOSBAmount(unittest.TestCase):

    def _run(self, years_str, doj, base_salary, min_yrs=2, half_limit=5):
        """Helper: mock profile + slip and call get_eosb_amount."""
        slabs = [_slab(0, None, 21)]
        prof = _profile(slabs, min_yrs=min_yrs, half_limit=half_limit)

        slip = MagicMock()
        slip.get = lambda k, default=None: [] if k == "earnings" else default

        # Patch salary component resolution to return fixed base
        with patch.object(policy, "resolve_benefit_profile", return_value=(prof, "Company")), \
             patch.object(policy, "get_service_years", return_value=float(years_str)), \
             patch.object(policy, "get_settings", return_value=None), \
             patch.object(policy, "_get_salary_component_amount",
                          side_effect=lambda slip, comp: base_salary if comp == "Basic" else 0.0):
            emp = _emp(doj=doj)
            with patch("frappe.get_doc", return_value=emp):
                return policy.get_eosb_amount("EMP-0001", salary_slip=slip, as_of_date="2025-01-01")

    def test_below_minimum_service(self):
        result = self._run("1.5", "2023-07-01", 10000)
        self.assertEqual(result["amount"], 0.0)
        self.assertIn("below the minimum", result["note"])

    def test_half_month_tier_at_2_years(self):
        # 2 years × (10000/2) = 10000
        result = self._run("2.0", "2023-01-01", 10000)
        self.assertAlmostEqual(result["amount"], 10000.0, delta=1)

    def test_half_month_tier_at_4_years(self):
        # 4 × 5000 = 20000
        result = self._run("4.0", "2021-01-01", 10000)
        self.assertAlmostEqual(result["amount"], 20000.0, delta=1)

    def test_boundary_exactly_5_years(self):
        # At half_limit=5: still half-month formula → 5 × 5000 = 25000
        result = self._run("5.0", "2020-01-01", 10000)
        self.assertAlmostEqual(result["amount"], 25000.0, delta=1)

    def test_full_month_tier_above_5_years(self):
        # 5 × 5000 (half) + 2 × 10000 (full) = 25000 + 20000 = 45000
        result = self._run("7.0", "2018-01-01", 10000)
        self.assertAlmostEqual(result["amount"], 45000.0, delta=1)

    def test_zero_salary_returns_zero(self):
        result = self._run("5.0", "2020-01-01", 0)
        self.assertEqual(result["amount"], 0.0)
        self.assertIn("zero", result["note"].lower())

    def test_no_profile_returns_zero(self):
        with patch.object(policy, "resolve_benefit_profile", return_value=(None, None)), \
             patch.object(policy, "get_service_years", return_value=5.0), \
             patch.object(policy, "get_settings", return_value=None):
            emp = _emp()
            with patch("frappe.get_doc", return_value=emp):
                result = policy.get_eosb_amount("EMP-0001")
        self.assertEqual(result["amount"], 0.0)

    def test_fractional_years_prorated(self):
        # 2.5 years × 5000 = 12500
        result = self._run("2.5", "2022-07-01", 10000)
        self.assertAlmostEqual(result["amount"], 12500.0, delta=5)


# ── Leave encashment tests ────────────────────────────────────────────────────

class TestGetLeaveEncashmentAmount(unittest.TestCase):

    def _run(self, leave_days, monthly_salary, max_cap=0, encash_enabled=True):
        prof = _profile([], encash_enabled=encash_enabled, max_encash=max_cap)
        settings = MagicMock()
        settings.default_working_days_per_month = 30

        with patch.object(policy, "resolve_benefit_profile", return_value=(prof, "Company")), \
             patch.object(policy, "get_settings", return_value=settings), \
             patch.object(policy, "_get_salary_component_amount",
                          side_effect=lambda s, c: monthly_salary if c == "Basic" else 0.0):
            emp = _emp()
            with patch("frappe.get_doc", return_value=emp):
                return policy.get_leave_encashment_amount(
                    "EMP-0001", leave_days, as_of_date="2025-01-01"
                )

    def test_basic_encashment(self):
        # 30 days salary / 30 days × 10 leave days = 10 days salary = 10000/30×10
        result = self._run(10, 30000)
        self.assertAlmostEqual(result["amount"], 10000.0, delta=1)

    def test_cap_applied(self):
        # Request 40 days, cap at 30 → should compute for 30 days
        result = self._run(40, 30000, max_cap=30)
        self.assertAlmostEqual(result["amount"], 30000.0, delta=1)
        self.assertEqual(result["effective_days"], 30.0)

    def test_zero_leave_days(self):
        result = self._run(0, 30000)
        self.assertEqual(result["amount"], 0.0)

    def test_encashment_disabled(self):
        result = self._run(10, 30000, encash_enabled=False)
        self.assertEqual(result["amount"], 0.0)
        self.assertIn("disabled", result["note"].lower())

    def test_no_cap_allows_any_days(self):
        result = self._run(90, 30000, max_cap=0)
        self.assertAlmostEqual(result["amount"], 90000.0, delta=1)


# ── Profile resolution tests ──────────────────────────────────────────────────

class TestResolveBenefitProfile(unittest.TestCase):

    def test_employee_level_takes_priority(self):
        emp = _emp()
        emp.grade = "G1"

        def fake_get_all(doctype, filters=None, pluck=None, order_by=None, limit=None):
            if filters.get("assignment_level") == "Employee":
                return ["EMP-PROF"]
            return []

        with patch("frappe.get_doc", return_value=emp), \
             patch("frappe.get_all", side_effect=fake_get_all):
            # get_doc is called twice: once for emp, once for profile
            frappe_mock = sys.modules["frappe"]
            call_count = [0]

            def get_doc_side(doctype, name=None):
                if doctype == "Employee":
                    return emp
                prof = MagicMock()
                prof.name = name
                return prof

            with patch.object(sys.modules["frappe"], "get_doc", side_effect=get_doc_side):
                profile, level = policy.resolve_benefit_profile("EMP-0001", "Test Co")

            self.assertEqual(level, "Employee")

    def test_falls_back_to_company(self):
        emp = _emp()
        emp.grade = None

        def fake_get_all(doctype, filters=None, pluck=None, order_by=None, limit=None):
            if filters.get("assignment_level") == "Company":
                return ["CO-PROF"]
            return []

        def get_doc_side(doctype, name=None):
            if doctype == "Employee":
                return emp
            prof = MagicMock()
            prof.name = name
            return prof

        with patch.object(sys.modules["frappe"], "get_doc", side_effect=get_doc_side), \
             patch("frappe.get_all", side_effect=fake_get_all):
            # Clear cache first
            if hasattr(sys.modules["frappe"].local, policy._CACHE_KEY):
                delattr(sys.modules["frappe"].local, policy._CACHE_KEY)
            sys.modules["frappe"].local = MagicMock()

            profile, level = policy.resolve_benefit_profile("EMP-0001", "Test Co")

        self.assertEqual(level, "Company")

    def test_no_profile_returns_none(self):
        emp = _emp()
        emp.grade = None

        with patch.object(sys.modules["frappe"], "get_doc", return_value=emp), \
             patch("frappe.get_all", return_value=[]):
            sys.modules["frappe"].local = MagicMock()
            profile, level = policy.resolve_benefit_profile("EMP-0001", "Test Co")

        self.assertIsNone(profile)
        self.assertIsNone(level)


# ── Daily salary tests ────────────────────────────────────────────────────────

class TestGetDailySalaryAmount(unittest.TestCase):

    def test_standard_30_days(self):
        settings = MagicMock()
        settings.default_working_days_per_month = 30
        result = policy.get_daily_salary_amount(30000, settings)
        self.assertAlmostEqual(result, 1000.0, delta=0.01)

    def test_no_settings_defaults_to_30(self):
        result = policy.get_daily_salary_amount(30000, None)
        self.assertAlmostEqual(result, 1000.0, delta=0.01)

    def test_zero_working_days_defaults_to_30(self):
        settings = MagicMock()
        settings.default_working_days_per_month = 0
        result = policy.get_daily_salary_amount(30000, settings)
        self.assertAlmostEqual(result, 1000.0, delta=0.01)


if __name__ == "__main__":
    unittest.main(verbosity=2)
