# Code rules for sb/

- Python 3.12. httpx for HTTP, pydantic for models, pytest, ruff.
- Secrets come only from environment variables. Never log a secret or a raw message body.
- Each client in sb/clients/ exposes only the reads and allowlisted writes in docs/BUILD.md section 3. A new write method needs Jo's sign-off in the PR description.
- Every external call has a timeout, one retry with backoff on 429 or 5xx, and an error message the run summary can show.
- Tests never touch the network. Use recorded fixtures with fake data.
- redact.py runs on everything collect produces. Its tests include door codes, lockbox codes, wifi passwords, card numbers and API keys inside realistic message text.
- apply.py rejects unknown action types, writes outside a worker's allowed paths, deletions, and edits to AGENTS.md, CLAUDE.md, workers/, sb/, schemas/ or .github/.
