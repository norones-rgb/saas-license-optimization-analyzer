# Five minute demonstration

1. Explain the difference between assigned seats, review candidates, seat value, and a bill reduction.
2. Open `sample_data/accounts.csv`. Show Jira's disabled and inactive accounts, the protected leave exception, and the enabled account with missing activity evidence.
3. Open `sample_data/pricing.json`. The sample prices are fictional. Jira is flexible monthly with a four-seat minimum; Confluence is committed-term.
4. Run the README command using the fixed date `2026-11-02` and a new output directory.
5. Open the dashboard: 11 assigned seats, 5 candidates, $52 candidate monthly seat value, $24 potential monthly bill reduction.
6. Explain the Jira calculation: six assigned seats minus three candidates leaves three assignments, but a four-seat minimum only allows two billable seats to disappear. Two × $12 = $24.
7. Explain why the committed Confluence plan produces $0 current-term reduction despite two candidates.
8. Copy the pricing configuration to a temporary file, change Jira's minimum to zero, and rerun into a different folder. Potential reduction becomes $36 per month. The candidates do not change; only the pricing scenario does.
9. Run `py -m unittest discover -s tests -v` (or use `python3`) and explain why a disabled and stale account is counted only once.
10. State the limits: read-only CSV analysis, synthetic demonstration, owner approval required, no actual savings or live tenant integration claimed.
