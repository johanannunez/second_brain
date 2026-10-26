# Provider client coverage

Clients in this directory use only fake transports in tests. Live provider calls are not run during the build.

- `google.py` implements the scoped Google OAuth token refresh and Gmail, Calendar, and Drive operations used by the brief. Confirm the current Google OAuth testing-token rule and API routes before configuring credentials.
- `todoist.py` implements the v1 projects, tasks, and completion-date reads with cursor pagination.
- `turno.py` implements the documented v2 projects and unresolved-problems reads, including pagination and required headers.
- `hospitable.py` enforces one reservation-thread fetch per run and the specified 30-second retry after HTTP 429. Route and other resource methods remain unimplemented until verified against the current public API.
- Quo, PriceLabs, Notion, GitHub README, and QuickBooks resource routes are not implemented yet. The task brief does not specify their endpoints, and the current running network policy cannot reach their documentation. They must be checked against current public docs before adding routes.

No client exposes smart-lock, reservation, pricing, owner-statement, payment, deletion, or message-send methods. Quo and Hospitable outbound messages are represented only as approval-outbox actions; actual sending belongs in the separate approval workflow after the provider routes are verified.
