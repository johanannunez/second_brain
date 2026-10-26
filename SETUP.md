# One-time setup

This Phase 0 guide prepares the accounts and GitHub Actions secrets for the system described in [docs/BUILD.md](docs/BUILD.md). Do not put secret values in this repository, issues, logs, or chat. Use GitHub's repository **Settings → Secrets and variables → Actions** for workflow credentials. Keep a separate record of which account each Google refresh token belongs to.

## 1. Create Google OAuth credentials

1. In [Google Cloud Console](https://console.cloud.google.com/), create a project for this system.
2. Enable the Gmail API, Google Calendar API, and Google Drive API in **APIs & Services → Library**.
3. Configure the OAuth consent screen / Google Auth Platform. Use **Internal** only if both Google accounts are in the same Google Workspace organization. Otherwise use **External** and publish the app to **In production** for personal use. The supplied build brief flags a seven-day refresh-token expiry for External apps in **Testing** when non-basic scopes such as Gmail or Calendar are requested. This environment could not independently verify that rule against [Google's current OAuth documentation](https://developers.google.com/identity/protocols/oauth2), because the running network policy does not allow `developers.google.com`. Confirm the current rule before relying on long-lived tokens; the two accounts need separate refresh tokens either way.
4. Add only the scopes the system needs: Gmail read/modify for reading mail, creating drafts and managing `SB/` labels; Calendar read and event management for the allowed busy flags and `SB:` blocks; and Drive read-only for backfill. Google may display an unverified-app warning for personal use. Do not submit the app for verification unless the user population or requested scopes require it.
5. Create an OAuth client of type **Desktop app** and download its client JSON to a private directory outside the repository. Do not commit that file.
6. On your own computer, install the helper dependency in a dedicated virtual environment, then authorize each account separately:

   ```sh
   python3 -m venv "$HOME/.venvs/second-brain-auth"
   "$HOME/.venvs/second-brain-auth/bin/python" -m pip install google-auth-oauthlib==1.2.2
   "$HOME/.venvs/second-brain-auth/bin/python" scripts/google_auth.py --account parcel --client-secrets /private/path/client-secret.json
   "$HOME/.venvs/second-brain-auth/bin/python" scripts/google_auth.py --account personal --client-secrets /private/path/client-secret.json
   ```

   Sign in as `hello@theparcelco.com` for `parcel` and `jo@johanannunez.com` for `personal`. The helper writes each refresh token to a mode-0600 JSON file under `~/.config/second-brain/`, never to the repository or terminal. Add each token to the corresponding GitHub Actions secret using a local secure editor or your password manager. Do not paste it into chat.

## 2. Create provider credentials

Create the integrations listed below only when ready to enable the corresponding worker. Give each credential the narrowest available access. For read-only sources, use read-only scopes. Slack's bot should only DM Jo. The future apply job receives write credentials; the model job must receive only `OPENAI_API_KEY`.

| Provider | One-time action |
| --- | --- |
| Hospitable | Create a personal access token with the API access needed for the read-only collect operations. |
| Quo (formerly OpenPhone) | Create an API key for the business line; sending remains approval-gated. |
| Turno | Obtain the API v2 secret key and partner ID. |
| Todoist | Revoke and replace the old token that was exposed in a prompt, then keep the new token only in GitHub Actions secrets. |
| Slack | Create a workspace app and bot token with only the scopes needed to DM Jo. Record Jo's Slack user ID separately. |
| PriceLabs (optional) | Create a customer API key for the optional nightly-price lookup. |
| Notion (optional) | Create an integration token and share only the backfill pages with that integration. |
| OpenAI | Create an API key dedicated to `codex-action`; API usage is billed separately from ChatGPT. |

## 3. Add GitHub Actions secrets

In the private `johanannunez/second_brain` repository, open **Settings → Secrets and variables → Actions → New repository secret**. Add these names exactly; enter values directly in GitHub's secure form.

Required when the related workflows are implemented:

```text
OPENAI_API_KEY
GOOGLE_OAUTH_CLIENT_ID
GOOGLE_OAUTH_CLIENT_SECRET
GOOGLE_REFRESH_TOKEN_PARCEL
GOOGLE_REFRESH_TOKEN_PERSONAL
HOSPITABLE_API_TOKEN
QUO_API_KEY
TURNO_SECRET_KEY
TURNO_PARTNER_ID
TODOIST_API_TOKEN
SLACK_BOT_TOKEN
SLACK_JO_USER_ID
```

Optional integrations:

```text
PRICELABS_API_KEY
NOTION_TOKEN
```

Keep the refresh token for each account paired with the matching account name. Do not add real values to `.env.example`; it documents names only. The workers and their credential separation are not implemented in Phase 0.

## 4. Cost planning

Costs depend on the GitHub account plan, runner duration, model, prompt/data size, and retry volume. The following is a planning estimate, not a quote:

- **GitHub Actions:** budget roughly 1,000–2,000 Linux runner minutes per month for five short scheduled workers, checks on a modest number of pull requests, and occasional manual runs. This assumes each worker's three jobs total about 4–7 runner minutes and does not include unusually large backfills. Check the repository owner's current included-minute allowance and overage rate in GitHub billing. If minutes are billed at $0.008/minute, 1,000–2,000 billable minutes would be $8–$16 before included minutes or other discounts.
- **OpenAI API:** reserve an initial **$25–$100/month** cap for the five workers, then measure actual usage from the API billing dashboard during dry runs. This is a conservative operating budget, not a guaranteed forecast; large inboxes, long histories, repeated runs, or a higher-priced model can exceed it. Set an API project budget/alert before enabling schedules. The codex-action job gets the API key and incurs API charges; it does not use a ChatGPT subscription quota.
- **Other providers:** this estimate excludes any paid Hospitable, Quo, Turno, Todoist, Slack, Google Workspace, Vercel, or Supabase plan and any optional PriceLabs or Notion charges.

## 5. Local safety

- Keep downloaded OAuth client JSON, refresh-token files, and local environment files outside the repository.
- Never put credentials in commits, Actions artifacts, issues, prompts, or logs.
- Rotate any token previously exposed in a prompt before use.
- Scheduled workers are not ready to enable until the later phases implement and test collection, redaction, action validation, dry runs, and approval enforcement.
