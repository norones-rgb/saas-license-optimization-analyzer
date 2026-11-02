"""Read-only SaaS license review and configurable scenario modeling."""

import argparse
from collections import Counter
import csv
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import html
import json
import os
from pathlib import Path
import shutil
import tempfile

FIELDS = {"product", "account_id", "enabled", "licensed", "last_active", "exception_reason"}


def money(value):
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def read_accounts(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = reader.fieldnames or []
        if len(headers) != len(set(headers)) or not FIELDS.issubset(headers):
            raise ValueError("CSV requires unique columns: " + ", ".join(sorted(FIELDS)))
        rows = []
        for number, raw in enumerate(reader, 2):
            if None in raw or any(value is None for value in raw.values()):
                raise ValueError(f"Malformed CSV row {number}")
            rows.append({key: value.strip() for key, value in raw.items()})
        return rows


def validate_config(config):
    if not isinstance(config, dict):
        raise ValueError("Pricing configuration must be a JSON object")
    if config.get("currency") != "USD":
        raise ValueError("This version supports USD only; no currency conversion is performed")
    threshold = config.get("inactive_days")
    if type(threshold) is not int or threshold < 1:
        raise ValueError("inactive_days must be a positive integer")
    products = config.get("products")
    if not isinstance(products, dict) or not products:
        raise ValueError("At least one product pricing configuration is required")
    result = {}
    for name, settings in products.items():
        if not name or not isinstance(settings, dict):
            raise ValueError("Product names and pricing objects are required")
        if settings.get("billing_mode") not in {"monthly_flexible", "committed_term"}:
            raise ValueError(f"{name}: unsupported billing_mode")
        minimum = settings.get("minimum_billable_seats")
        if type(minimum) is not int or minimum < 0:
            raise ValueError(f"{name}: minimum_billable_seats must be a nonnegative integer")
        try:
            # Strings preserve exact decimal values in configuration files.
            price = Decimal(str(settings["monthly_seat_price"]))
        except (KeyError, InvalidOperation, ValueError) as exc:
            raise ValueError(f"{name}: invalid monthly_seat_price") from exc
        if not price.is_finite() or price < 0:
            raise ValueError(f"{name}: price must be finite and nonnegative")
        result[name] = dict(settings, price=price)
    return threshold, result


def analyze(accounts, config, as_of):
    threshold, products = validate_config(config)
    if not accounts:
        raise ValueError("Empty account export; cannot establish a licensing baseline")
    seen = set()
    review = []
    counts = {name: Counter() for name in products}
    observed = set()
    for row in sorted(accounts, key=lambda row: (row["product"], row["account_id"])):
        name, account_id = row["product"], row["account_id"]
        if name not in products or not account_id:
            raise ValueError("Each account needs a configured product and a nonempty account_id")
        if (name, account_id) in seen:
            raise ValueError("Duplicate account_id within product; refusing to double-count seats")
        seen.add((name, account_id))
        observed.add(name)
        flags = {}
        for key in ("enabled", "licensed"):
            value = row[key].lower()
            if value not in {"true", "false"}:
                raise ValueError(f"{account_id}: {key} must be true or false")
            flags[key] = value == "true"
        try:
            last_active = date.fromisoformat(row["last_active"]) if row["last_active"] else None
        except ValueError as exc:
            raise ValueError(f"{account_id}: last_active must be YYYY-MM-DD or empty") from exc
        if last_active and last_active > as_of:
            raise ValueError(f"{account_id}: last_active is later than the assessment")
        c = counts[name]
        c["exported_accounts"] += 1
        if not flags["licensed"]:
            continue
        c["assigned_seats"] += 1
        age = (as_of - last_active).days if last_active else None
        reasons = []
        if not flags["enabled"]:
            reasons.append("DISABLED_LICENSED")
        if age is not None and age > threshold:
            reasons.append("INACTIVE_LICENSED")
        exception = row["exception_reason"]
        if exception:
            classification = "EXEMPT_RETAIN"
            c["exempt_seats"] += 1
        elif reasons:
            classification = "REVIEW_CANDIDATE"
            c["review_candidates"] += 1
        elif age is None:
            classification = "MISSING_ACTIVITY_EVIDENCE"
            c["missing_activity_seats"] += 1
        else:
            classification = "RETAIN"
        review.append({"product": name, "account_id": account_id,
                       "classification": classification, "reasons": reasons,
                       "days_inactive": age, "exception_reason": exception,
                       "action": "Owner approval required before any license change" if classification == "REVIEW_CANDIDATE" else "Retain or investigate evidence; no automatic change"})
    missing = set(products) - observed
    if missing:
        raise ValueError("Configured products missing from export: " + ", ".join(sorted(missing)))
    summaries = []
    for name in sorted(products):
        pricing = products[name]
        c = counts[name]
        seats, candidates = c["assigned_seats"], c["review_candidates"]
        minimum, price = pricing["minimum_billable_seats"], pricing["price"]
        before = max(seats, minimum)
        after = max(seats - candidates, minimum)
        flexible = pricing["billing_mode"] == "monthly_flexible"
        savings = Decimal(before - after) * price if flexible else Decimal(0)
        summaries.append({"product": name, "billing_mode": pricing["billing_mode"],
                          **{key: c[key] for key in ("exported_accounts", "assigned_seats", "review_candidates", "exempt_seats", "missing_activity_seats")},
                          "minimum_billable_seats": minimum, "monthly_seat_price_usd": money(price),
                          "modeled_billable_seats_before": before,
                          "modeled_billable_seats_after_approval": after if flexible else before,
                          "modeled_monthly_baseline_usd": money(Decimal(before) * price),
                          "candidate_monthly_seat_value_usd": money(Decimal(candidates) * price),
                          "potential_monthly_bill_reduction_usd": money(savings),
                          "annualized_run_rate_reduction_usd": money(savings * 12)})
    total = lambda key: money(sum((Decimal(p[key]) for p in summaries), Decimal(0)))
    return {"assessment_date": as_of.isoformat(), "currency": "USD", "inactive_days": threshold,
            "scenario": "All review candidates approved and removed; pricing assumptions hold",
            "assigned_seats": sum(p["assigned_seats"] for p in summaries),
            "review_candidates": sum(p["review_candidates"] for p in summaries),
            "candidate_monthly_seat_value_usd": total("candidate_monthly_seat_value_usd"),
            "potential_monthly_bill_reduction_usd": total("potential_monthly_bill_reduction_usd"),
            "annualized_run_rate_reduction_usd": total("annualized_run_rate_reduction_usd"),
            "products": summaries, "review_register": review}


def safe_csv(value):
    value = str(value)
    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value


def dashboard(report):
    esc = lambda value: html.escape(str(value), quote=True)
    products = "".join("<tr>" + "".join(f"<td>{esc(p[key])}</td>" for key in
        ("product", "billing_mode", "assigned_seats", "review_candidates", "candidate_monthly_seat_value_usd", "potential_monthly_bill_reduction_usd")) + "</tr>" for p in report["products"])
    reviews = "".join("<tr>" + "".join(f"<td>{esc(value)}</td>" for value in
        (r["product"], r["account_id"], r["classification"], ", ".join(r["reasons"]), r["days_inactive"] if r["days_inactive"] is not None else "Unknown", r["exception_reason"], r["action"])) + "</tr>" for r in report["review_register"])
    def header(labels):
        return "<thead><tr>" + "".join(f'<th scope="col">{label}</th>' for label in labels) + "</tr></thead>"
    return f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'"><title>SaaS License Review</title>
<style>body{{font:16px/1.5 system-ui,sans-serif;margin:0;padding:32px;background:#f6f4ef;color:#202b3b}}main{{max-width:1400px;margin:auto}}h1{{font-size:36px;margin-bottom:8px}}.muted{{color:#526175}}.metrics{{display:flex;gap:16px;flex-wrap:wrap;margin:26px 0}}.metric{{background:white;border:1px solid #d7d8d4;padding:18px;border-radius:8px;flex:1;min-width:190px}}strong{{display:block;font-size:30px}}table{{width:100%;border-collapse:collapse;background:white;font-size:14px}}td,th{{border:1px solid #d7d8d4;text-align:left;padding:12px;vertical-align:top;overflow-wrap:anywhere}}th{{background:#e8eae6}}.scroll{{overflow-x:auto}}section{{margin-top:30px}}footer{{margin-top:26px}}</style>
<main><p class="muted">SAAS LICENSE ANALYZER · READ ONLY</p><h1>SaaS License Review</h1><p>Assessment {esc(report['assessment_date'])} · Inactive means more than {report['inactive_days']} days · Configured pricing scenario</p>
<p>Scenario: all flagged candidates pass owner review and are removed. Amounts use configured prices; they do not establish vendor quotes or realized savings.</p>
<div class="metrics"><div class="metric">Assigned seats<strong>{report['assigned_seats']}</strong></div><div class="metric">Review candidates<strong>{report['review_candidates']}</strong></div><div class="metric">Candidate seat value per month<strong>${report['candidate_monthly_seat_value_usd']}</strong></div><div class="metric">Potential bill reduction per month<strong>${report['potential_monthly_bill_reduction_usd']}</strong></div></div>
<section><h2>Pricing scenarios</h2><p>Committed-term seats can be reallocated, but this model assumes no bill reduction during the commitment. Monthly minimums limit flexible-plan reductions. Annualized run-rate reduction: ${report['annualized_run_rate_reduction_usd']}; this is not first-year realized savings.</p><div class="scroll"><table><caption>USD monthly scenario by product</caption>{header(['Product','Billing assumption','Assigned','Candidates','Candidate seat value','Potential bill reduction'])}<tbody>{products}</tbody></table></div></section>
<section><h2>License review register</h2><p>Exempt seats are excluded from reclaim candidates. Missing activity alone does not establish inactivity.</p><div class="scroll"><table>{header(['Product','Account','Classification','Reasons','Days inactive','Exception','Action'])}<tbody>{reviews}</tbody></table></div></section>
<footer class="muted">No access or license changes are performed. Exports must contain one row per account per product and complete assigned-seat inventories. Pricing models are simplified and do not include taxes, tiered rates, credits, discounts, contract renewal dates, or notice periods. Validate the actual subscription before action.</footer></main></html>'''


def write_report(report, output):
    output = Path(output)
    if output.exists():
        raise ValueError("Output already exists; choose a new directory")
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".licenses-", dir=output.parent))
    try:
        (stage / "analysis.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        (stage / "dashboard.html").write_text(dashboard(report), encoding="utf-8")
        with (stage / "review_register.csv").open("w", newline="", encoding="utf-8") as handle:
            fields = ["product", "account_id", "classification", "reasons", "days_inactive", "exception_reason", "action"]
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for raw in report["review_register"]:
                row = dict(raw, reasons="; ".join(raw["reasons"]), days_inactive=raw["days_inactive"] if raw["days_inactive"] is not None else "")
                writer.writerow({key: safe_csv(value) for key, value in row.items()})
        if output.exists():
            raise ValueError("Output appeared during processing; choose a new directory")
        os.rename(stage, output)
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--accounts", type=Path, required=True)
    parser.add_argument("--pricing", type=Path, required=True)
    parser.add_argument("--as-of", type=date.fromisoformat, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = analyze(read_accounts(args.accounts), json.loads(args.pricing.read_text(encoding="utf-8")), args.as_of)
        write_report(report, args.output)
    except (ValueError, OSError, UnicodeError, csv.Error, TypeError) as exc:
        parser.exit(2, f"Analysis error: {exc}\n")
    print(f"Assigned seats: {report['assigned_seats']}; review candidates: {report['review_candidates']}")
    print(f"Potential monthly bill reduction: USD {report['potential_monthly_bill_reduction_usd']} (scenario only)")
    print(f"Reports: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
