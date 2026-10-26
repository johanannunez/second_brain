# Worker: monthly close

Runs on the 1st at 8:00 AM Central, covering the month that just ended. Read AGENTS.md, workers/STYLE.md and sops/owner-statements-and-payments.md first. data.json is your only source of facts.

## Prepare; never publish
- Owner statements: for each owner in Hospitable, whether a statement exists for the month, whether it's still a draft, and anything that looks off (missing payouts, refunds, cleaning fees with no turnover). Never publish a statement or mark it paid.
- Invoices: VRBO and direct bookings that still need an invoice.
- Books: if QuickBooks data is in data.json, business-level totals and the items the accountant will ask about. No account numbers, and no owner-level amounts copied into the repo; link to the statement in Hospitable instead.
- Money alerts from the month that still need action.
- A checklist for Jo, in the order he should work it.

## Outputs
- monthly/{yyyy-mm}-close.md and one notify.
- Allowed actions: todoist_create, notify.
- Allowed paths: monthly/.
