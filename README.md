# Orange e-Invoice Keeper

A small Docker service that keeps one or more Orange portal profiles alive by scheduling a login before the portal's reported e-invoice deadline. Python remains running; Playwright Chromium is started only during an account operation and uses a separate persistent profile for each account.

> **Before use:** Orange frequently changes its login UI and its terms may constrain automation. Verify `ORANGE_LOGIN_URL` and the centralized selectors in `src/orange_einvoice/orange/selectors.py` against the current portal. This project detects OTP; it does not bypass it.

## Quick start

```bash
cp .env.example .env
# Edit ORANGE_ACCOUNTS; .env is gitignored and passwords are never written to SQLite.
docker compose up -d --build
docker compose exec orange-einvoice orange-einvoice status
```

Persistent data lives only in the `orange-data` volume:

```text
/data/state.db                 # schedules/events only; never secrets
/data/browser/<account-name>/  # isolated Chromium profile/cookies
/data/artifacts/<account>/     # screenshots/metadata on unexpected failures
```

For interactive trusted-device/OTP setup, use a headed container with a display-capable Docker setup, or run the image manually with `ORANGE_BROWSER_HEADLESS=false`:

```bash
docker compose run --rm -it orange-einvoice bootstrap home
# Once Orange asks for OTP, the CLI prompts without echoing or persisting the code.
```

`bootstrap` initially attempts normal sign-in. If OTP is detected, it prompts and re-runs using the same persistent account profile. `run-once [ACCOUNT]` is useful to validate a profile. The normal `run` command reconciles config/state at startup, processes overdue/new accounts, then uses interruptible sleeps until the earliest durable `next_attempt_at`.

## Configuration

Settings are parsed once from `ORANGE_*` environment variables with `pydantic-settings`. `ORANGE_ACCOUNTS` is a JSON list and must contain unique safe names:

```env
ORANGE_ACCOUNTS=[{"name":"home","email":"me@example.com","password":"secret"},{"name":"mobile","email":"other@example.com","password":"secret2","enabled":true}]
```

Key settings: `ORANGE_LOGIN_ADVANCE_DAYS` (default `7`), `ORANGE_FALLBACK_LOGIN_INTERVAL_DAYS` (`25`, used only when Orange does not expose a deadline), `ORANGE_RETRY_DELAY_HOURS` (`6`), `ORANGE_OTP_RETRY_DELAY_HOURS` (`24`), `ORANGE_INVALID_CREDENTIALS_RETRY_DELAY_HOURS` (`168`), `ORANGE_TIMEZONE`, `ORANGE_BROWSER_HEADLESS`, `ORANGE_WEBHOOK_URL`, `ORANGE_FAILURE_ARTIFACT_RETENTION` (`5`) and `ORANGE_SAVE_FAILURE_HTML` (default false; HTML may contain personal data).

A successful result is scheduled at the Orange deadline minus the advance days, inside a deterministic per-account 03:00–06:00 local-time window. Unknown deadlines use normal retry scheduling. Temporary errors back off from 6 h to a capped 24 h; OTP and invalid credentials use deliberate slower schedules.

## Operations and security

```bash
orange-einvoice run
orange-einvoice bootstrap ACCOUNT [--otp CODE]
orange-einvoice run-once [ACCOUNT]
orange-einvoice status
```

`status` is both an operator command and Docker health check: it reports `healthy` when all enabled accounts are success/ready, `degraded` when an account needs recovery, and exits non-zero only if the application cannot load state. Logs are JSON and identify accounts by configured name only. Passwords are held in `SecretStr` runtime configuration; OTPs, passwords, and cookies are not logged or copied into `state.db`.

The notification adapter posts `{event, account, detail}` to `ORANGE_WEBHOOK_URL` for non-success outcomes. It deliberately does not send a notification for every successful monthly login.

## Development

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
ruff check .
mypy src
pytest
```

The tests cover parsing, configuration, durable reconciliation, scheduling, and state transitions without calling Orange or launching Chromium. Real account logins must never run in CI.
