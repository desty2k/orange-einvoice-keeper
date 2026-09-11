# Orange e-Invoice Keeper

A small Docker service that keeps one or more Orange portal profiles alive by scheduling a login before the portal's reported e-invoice deadline. Python remains running; Playwright Chromium is started only during an account operation and uses a separate persistent profile for each account.

> **Before use:** Orange frequently changes its login UI and its terms may constrain automation. Verify `ORANGE_LOGIN_URL` and the centralized selectors in `src/orange_einvoice/orange/selectors.py` against the current portal. This project detects OTP; it does not bypass it.

## Quick start

The default `compose.yaml` runs the latest public GHCR image. Copy it with `.env.example` (or clone the repository), then configure your local credentials:

```bash
cp .env.example .env
# Edit ORANGE_ACCOUNTS; .env is gitignored and passwords are never written to SQLite.
docker compose pull
docker compose up -d
docker compose exec orange-einvoice orange-einvoice status
```

To build and run your local checkout instead, use the developer configuration explicitly:

```bash
docker compose -f compose.local.yaml up -d --build
docker compose -f compose.local.yaml exec orange-einvoice orange-einvoice status
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

`bootstrap` initially attempts normal sign-in. If OTP is detected, it prompts and submits the code on that same live Playwright page and browser context—without a login-page reload. `run-once [ACCOUNT]` is useful to validate a profile. The normal `run` command reconciles config/state at startup, processes overdue/new accounts, then uses interruptible sleeps until the earliest durable `next_attempt_at`.

## Configuration

Settings are parsed once from `ORANGE_*` environment variables with `pydantic-settings`. `ORANGE_ACCOUNTS` is a JSON list and must contain unique safe names:

```env
ORANGE_ACCOUNTS=[{"name":"home","email":"me@example.com","password":"secret"},{"name":"mobile","email":"other@example.com","password":"secret2","enabled":true}]
```

Key settings: `ORANGE_LOGIN_ADVANCE_DAYS` (default `7`), `ORANGE_SUCCESS_CHECK_INTERVAL_DAYS` (`7`; successful accounts verify/login weekly, or earlier when Orange’s deadline requires it), `ORANGE_RETRY_DELAY_HOURS` (`6`), `ORANGE_OTP_RETRY_DELAY_HOURS` (`24`), `ORANGE_INVALID_CREDENTIALS_RETRY_DELAY_HOURS` (`168`), `ORANGE_TIMEZONE`, `ORANGE_BROWSER_HEADLESS`, `ORANGE_WEBHOOK_URL`, `ORANGE_FAILURE_ARTIFACT_RETENTION` (`5`) and `ORANGE_SAVE_FAILURE_HTML` (default false; HTML may contain personal data).

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

## Container releases

GitHub Actions publishes `ghcr.io/desty2k/orange-einvoice-keeper` from `main` when commits since the latest `vX.Y.Z` tag follow Conventional Commits: `feat` creates a minor release, `fix` or `perf` a patch release, and `type!` or `BREAKING CHANGE:` a major release. Each release publishes immutable `vX.Y.Z` plus `X.Y`, `X`, and `latest` image tags, then creates the matching immutable Git tag. Commits without a release signal do not publish an image. The default `compose.yaml` uses `ghcr.io/desty2k/orange-einvoice-keeper:latest`; use a `vX.Y.Z` tag in a copied Compose file when you require an immutable deployment version.
