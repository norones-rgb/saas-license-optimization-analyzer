import copy
from datetime import date, timedelta
import json
from pathlib import Path
import tempfile
import unittest

from analyzer import analyze, dashboard, main, read_accounts, safe_csv, write_report

AS_OF = date(2026, 11, 2)


class LicenseAnalyzerTests(unittest.TestCase):
    def config(self, **changes):
        product = dict(monthly_seat_price="12.00", billing_mode="monthly_flexible", minimum_billable_seats=0)
        product.update(changes)
        return dict(currency="USD", inactive_days=90, products={"Jira": product})

    def row(self, **changes):
        row = dict(product="Jira", account_id="a1", enabled="true", licensed="true", last_active="2026-11-01", exception_reason="")
        row.update(changes)
        return row

    def test_active_licensed_retained(self):
        r = analyze([self.row()], self.config(), AS_OF)
        self.assertEqual(r["assigned_seats"], 1)
        self.assertEqual(r["review_candidates"], 0)
        self.assertEqual(r["potential_monthly_bill_reduction_usd"], "0.00")

    def test_disabled_and_stale_count_once(self):
        r = analyze([self.row(enabled="false", last_active="2026-01-01")], self.config(), AS_OF)
        self.assertEqual(r["review_candidates"], 1)
        self.assertEqual(len(r["review_register"][0]["reasons"]), 2)
        self.assertEqual(r["potential_monthly_bill_reduction_usd"], "12.00")

    def test_boundary_is_strictly_more_than_threshold(self):
        for age, count in ((90, 0), (91, 1)):
            row = self.row(last_active=(AS_OF - timedelta(days=age)).isoformat())
            self.assertEqual(analyze([row], self.config(), AS_OF)["review_candidates"], count)

    def test_missing_activity_does_not_prove_inactivity(self):
        r = analyze([self.row(last_active="")], self.config(), AS_OF)
        self.assertEqual(r["review_candidates"], 0)
        self.assertEqual(r["review_register"][0]["classification"], "MISSING_ACTIVITY_EVIDENCE")

    def test_exception_protects_disabled_or_stale_seat(self):
        r = analyze([self.row(enabled="false", last_active="2026-01-01", exception_reason="Approved exception")], self.config(), AS_OF)
        self.assertEqual(r["review_candidates"], 0)
        self.assertEqual(r["products"][0]["exempt_seats"], 1)

    def test_unlicensed_is_not_a_reclamation_candidate(self):
        r = analyze([self.row(licensed="false", enabled="false")], self.config(), AS_OF)
        self.assertEqual(r["assigned_seats"], 0)
        self.assertEqual(r["review_register"], [])

    def test_minimum_seats_limit_cash_reduction(self):
        rows = [self.row(account_id=str(i), enabled="false" if i < 3 else "true") for i in range(6)]
        r = analyze(rows, self.config(minimum_billable_seats=4), AS_OF)
        self.assertEqual(r["candidate_monthly_seat_value_usd"], "36.00")
        self.assertEqual(r["potential_monthly_bill_reduction_usd"], "24.00")
        self.assertEqual(r["annualized_run_rate_reduction_usd"], "288.00")

    def test_committed_term_has_no_in_term_bill_reduction(self):
        r = analyze([self.row(enabled="false")], self.config(billing_mode="committed_term"), AS_OF)
        self.assertEqual(r["candidate_monthly_seat_value_usd"], "12.00")
        self.assertEqual(r["potential_monthly_bill_reduction_usd"], "0.00")
        self.assertEqual(r["products"][0]["modeled_billable_seats_after_approval"], 1)

    def test_below_minimum_has_no_cash_reduction(self):
        r = analyze([self.row(enabled="false")], self.config(minimum_billable_seats=10), AS_OF)
        self.assertEqual(r["potential_monthly_bill_reduction_usd"], "0.00")

    def test_decimal_calculation(self):
        rows = [self.row(account_id=str(i), enabled="false") for i in range(3)]
        r = analyze(rows, self.config(monthly_seat_price="0.10"), AS_OF)
        self.assertEqual(r["potential_monthly_bill_reduction_usd"], "0.30")

    def test_reject_duplicate_accounts_and_missing_product_exports(self):
        with self.assertRaises(ValueError):
            analyze([self.row(), self.row()], self.config(), AS_OF)
        config = self.config()
        config["products"]["Confluence"] = copy.deepcopy(config["products"]["Jira"])
        with self.assertRaises(ValueError):
            analyze([self.row()], config, AS_OF)
        with self.assertRaises(ValueError):
            analyze([], self.config(), AS_OF)

    def test_invalid_account_values(self):
        for change in (dict(enabled="yes"), dict(licensed="1"), dict(account_id=""), dict(product="Unknown"), dict(last_active="2027-01-01"), dict(last_active="bad")):
            with self.subTest(change=change), self.assertRaises(ValueError):
                analyze([self.row(**change)], self.config(), AS_OF)

    def test_invalid_configuration(self):
        for change in (dict(monthly_seat_price="NaN"), dict(monthly_seat_price="Infinity"), dict(monthly_seat_price="-1"), dict(billing_mode="tiered"), dict(minimum_billable_seats=-1), dict(minimum_billable_seats=True)):
            with self.subTest(change=change), self.assertRaises(ValueError):
                analyze([self.row()], self.config(**change), AS_OF)
        for config in ([], {}, dict(self.config(), currency="EUR"), dict(self.config(), inactive_days=0)):
            with self.assertRaises(ValueError):
                analyze([self.row()], config, AS_OF)

    def test_reproducible_and_does_not_mutate_inputs(self):
        rows = [self.row(account_id="b", enabled="false"), self.row(account_id="a")]
        before = copy.deepcopy(rows)
        self.assertEqual(analyze(rows, self.config(), AS_OF), analyze(list(reversed(rows)), self.config(), AS_OF))
        self.assertEqual(rows, before)

    def test_output_escaping_and_preservation(self):
        r = analyze([self.row(account_id="=1+1", exception_reason="<script>alert(1)</script>")], self.config(), AS_OF)
        self.assertNotIn("<script>", dashboard(r))
        self.assertIn("&lt;script&gt;", dashboard(r))
        self.assertEqual(safe_csv(" =1+1"), "' =1+1")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report"
            write_report(r, path)
            self.assertIn("'=1+1", (path / "review_register.csv").read_text())
            with self.assertRaises(ValueError):
                write_report(r, path)

    def test_csv_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "input.csv"
            for content in ("wrong\nx\n", "product,product\nJira,Jira\n", "product,account_id,enabled,licensed,last_active,exception_reason\nJira,a1,true,true\n"):
                path.write_text(content)
                with self.assertRaises(ValueError):
                    read_accounts(path)

    def test_synthetic_demo_end_to_end(self):
        root = Path(__file__).resolve().parents[1]
        account = root / "sample_data/accounts.csv"
        pricing = root / "sample_data/pricing.json"
        before = (account.read_bytes(), pricing.read_bytes())
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "demo"
            self.assertEqual(main(["--accounts", str(account), "--pricing", str(pricing), "--as-of", str(AS_OF), "--output", str(output)]), 0)
            report = json.loads((output / "analysis.json").read_text())
            self.assertEqual(report["assigned_seats"], 11)
            self.assertEqual(report["review_candidates"], 5)
            self.assertEqual(report["candidate_monthly_seat_value_usd"], "52.00")
            self.assertEqual(report["potential_monthly_bill_reduction_usd"], "24.00")
            self.assertEqual(len(list(output.iterdir())), 3)
        self.assertEqual(before, (account.read_bytes(), pricing.read_bytes()))


if __name__ == "__main__":
    unittest.main()
