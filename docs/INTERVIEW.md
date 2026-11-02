# Interview discussion

## Project explanation

“This independent, AI-assisted project models SaaS license optimization from exported data. It creates review candidates without changing access and separates their seat value from the bill reduction the pricing model would allow. I used synthetic Jira and Confluence data so the example is reproducible and contains no employer information.”

## Design questions

| Question | Explain |
| --- | --- |
| Why not reclaim every inactive seat? | The last-active field may have incomplete coverage, and the account may have an approved business exception. |
| What if an account is both disabled and inactive? | It has both reason codes but counts as one candidate, avoiding double-counted savings. |
| Why does a missing activity date not create a candidate? | Missing telemetry does not establish inactivity. |
| Why do commitments matter? | Reassigning seats can create operational value without reducing the current bill. |
| Why use Decimal? | Monetary calculations need predictable decimal arithmetic rather than binary floating-point approximations. |
| What assumptions are necessary? | Complete exports, valid license flags, correct pricing model, all candidates approved, and subscription terms that permit the modeled reduction. |
| What would you add next? | Expiring exceptions, approval evidence, tiered billing, vendor export adapters, input hashes, and measured before-and-after invoices. |

## Practice before an interview

- Trace one record through `analyze()` from licensed status to classification and the pricing summary.
- Predict the result of changing the seat minimum before running the example.
- Add a synthetic protected account and explain why its flags remain visible but its seat is excluded from candidates.
- Explain why the annualized run-rate reduction is not realized first-year savings.

## Résumé wording after familiarization

**SaaS License Optimization Analyzer | Python, data analysis, HTML dashboards**

Developed an AI-assisted license review tool for synthetic Jira and Confluence exports, with exception handling, configurable pricing scenarios, and dashboard reporting that distinguishes candidate seat value from potential bill reduction.

Add the repository URL only after publication. The sample figures are demonstration results and must not be presented as employer savings.
