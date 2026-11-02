# SaaS License Optimization Analyzer

A read-only Python tool for reviewing Jira and Confluence license allocation and modeling potential savings under explicit pricing assumptions.

Independent portfolio project by Ibrahima Aw, with AI-assisted implementation. All bundled accounts and prices are synthetic. The project demonstrates license review, data analysis, dashboard reporting, input validation, and cost modeling. It does not document a company deployment or actual savings.

## Why this exists

Removing three assigned licenses does not necessarily reduce a bill by three times the seat price. Minimum seat commitments and subscription terms can limit the reduction, even when the licenses are reasonable candidates for reassignment.

The analyzer identifies review candidates, protects documented exceptions, and separates **candidate seat value** from **potential bill reduction**. It never changes application access or licenses.

## Run the demo

Requires Python 3.10 or newer. No dependencies, API keys, installation step, or SaaS tenant access is required.

From this project folder on Windows:

```powershell
py analyzer.py --accounts sample_data/accounts.csv --pricing sample_data/pricing.json --as-of 2026-11-02 --output reports/demo
py -m unittest discover -s tests -v
```

Use `python3` instead of `py` on macOS or Linux. Open `reports/demo/dashboard.html` in your browser. A prebuilt synthetic report is also available at `demo_output/dashboard.html`.

Choose a new output directory for each run. Existing outputs are not overwritten.

## Demo results

| Product | Assigned seats | Candidates | Candidate monthly seat value | Potential monthly bill reduction |
| --- | ---: | ---: | ---: | ---: |
| Jira | 6 | 3 | $36.00 | $24.00 |
| Confluence | 5 | 2 | $16.00 | $0.00 |
| Total | 11 | 5 | $52.00 | $24.00 |

Jira uses a fictional $12 monthly seat price and a four-seat billing minimum. Removing all three candidates reduces assigned seats from six to three, but modeled billed seats only fall from six to four.

Confluence uses a fictional $8 monthly-equivalent seat price with a committed-term assumption. Two candidates have $16 in monthly seat value, but the model assumes no current-term bill reduction. Those seats may support reassignment or a future renewal discussion.

The total annualized run-rate reduction is $288, calculated as $24 × 12. It is not a forecast of first-year realized savings and does not account for approval dates, renewal timing, or notice periods.

## Review logic

Only licensed accounts are included in the review register.

| Classification | Logic | Savings scenario |
| --- | --- | --- |
| `REVIEW_CANDIDATE` | Disabled or last active more than the threshold, with no exception | Included once per account, even when both reasons apply |
| `EXEMPT_RETAIN` | Nonempty documented exception reason | Excluded from candidates even if disabled or inactive |
| `MISSING_ACTIVITY_EVIDENCE` | Enabled account with no activity date and no exception | Excluded; missing data does not prove inactivity |
| `RETAIN` | Remaining licensed accounts | Excluded |

Exceptions are accepted as supplied; the tool does not verify approval or expiry. Review candidates still require owner approval and validated activity evidence before action.

## Input format

The CSV requires all six columns:

```csv
product,account_id,enabled,licensed,last_active,exception_reason
Jira,jira-001,true,true,2026-10-30,
```

- One row per account per product; duplicate keys fail validation.
- Product names must exactly match pricing configuration keys, including case.
- `enabled` and `licensed` must be `true` or `false`, ignoring case.
- `last_active` must be `YYYY-MM-DD` or empty. Dates after `--as-of` fail validation.
- Each product configured for the assessment must appear in the export. Use a scoped pricing file if a product is deliberately excluded.
- Complete assigned-seat inventory is required for a meaningful modeled baseline. The tool cannot detect silently omitted rows.
- The same account identifier may appear once in each different product.
- Extra columns are accepted but not included in reports.

## Pricing configuration

`sample_data/pricing.json` contains example assumptions, not real Atlassian pricing.

```json
{
  "currency": "USD",
  "inactive_days": 90,
  "products": {
    "Jira": {
      "monthly_seat_price": "12.00",
      "billing_mode": "monthly_flexible",
      "minimum_billable_seats": 4
    }
  }
}
```

Use quoted decimal strings for prices. Monetary calculations use Python `Decimal`; displayed results round to cents after calculation. Only USD is supported; no exchange rates are fetched.

### Flexible monthly model

```text
billable_before = max(assigned_seats, minimum_billable_seats)
billable_after = max(assigned_seats - review_candidates, minimum_billable_seats)
potential_monthly_bill_reduction = (billable_before - billable_after) × monthly_seat_price
```

The scenario assumes every candidate is approved and removed and the configured monthly pricing can adjust accordingly. Verify notice periods and contract terms separately.

### Committed-term model

`committed_term` holds modeled billable seats unchanged and reports zero current-term reduction. Candidate seat value remains visible. Set `minimum_billable_seats` to the relevant committed-seat floor for the scenario; this is a simplified model, not an invoice calculator.

## Outputs

| File | Purpose |
| --- | --- |
| `dashboard.html` | Standalone HTML summary, product comparisons, and review register |
| `review_register.csv` | Review classifications, reasons, activity age, exceptions, and suggested action |
| `analysis.json` | Structured assumptions, per-product results, totals, and review records |

The HTML loads no external resources and uses no JavaScript. Exported strings are escaped in HTML, and spreadsheet formula prefixes are neutralized in CSV. Input files remain unchanged. Output folders are staged before publication and never intentionally overwritten; this local workflow is intended for a single operator.

## Tests

```powershell
py -m unittest discover -s tests -v
```

Coverage includes disabled and stale accounts, deduplication of candidate reasons, exact inactivity boundaries, protected exceptions, unknown activity, billing floors, committed terms, exact decimal calculation, malformed exports, deterministic output, report escaping, and the complete synthetic demo.

## Scope and limitations

This is a local portfolio prototype. It has no Jira, Confluence, Okta, or ServiceNow API integration, and it does not remediate access. It has no authentication or encryption at rest. Reports contain supplied account identifiers.

It does not model real Atlassian tiered pricing, annual volume tiers, discounts, taxes, refunds, credits, renewal dates, or changes in plan features. Input flags are trusted. A candidate is not proof of misuse or a guaranteed reclaimable seat. The tool neither verifies exception approval nor independently validates export completeness. Keep public examples synthetic.

## Related project

[Application Access Reconciler](https://github.com/norones-rgb/application-access-reconciler) focuses on authoritative identity matching and access review. This analyzer adds license-specific classification and configurable billing scenarios.

See [DEMO.md](docs/DEMO.md) for a walkthrough and [INTERVIEW.md](docs/INTERVIEW.md) for design discussion. Understand the implementation before presenting or maintaining it.

## License

MIT. See [LICENSE](LICENSE).
