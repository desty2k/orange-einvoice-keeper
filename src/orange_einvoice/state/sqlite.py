from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from orange_einvoice.config import AccountSettings
from orange_einvoice.models import AccountState, AccountStatus


class SQLiteStateRepository:
    """Small SQLite persistence layer; timestamps are stored as UTC ISO-8601 strings."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.connection: sqlite3.Connection | None = None

    def open(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.database_path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS accounts (
              account_name TEXT PRIMARY KEY,
              status TEXT NOT NULL,
              last_attempt_at TEXT,
              last_success_at TEXT,
              next_required_login TEXT,
              next_attempt_at TEXT,
              consecutive_failures INTEGER NOT NULL DEFAULT 0,
              last_error TEXT,
              updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS account_events (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              account_name TEXT NOT NULL REFERENCES accounts(account_name),
              event_type TEXT NOT NULL,
              timestamp TEXT NOT NULL,
              details TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_accounts_next_attempt ON accounts(next_attempt_at);
            """
        )
        self.connection.commit()

    def close(self) -> None:
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    def reconcile(self, accounts: Iterable[AccountSettings], now: datetime) -> None:
        connection = self._connection()
        configured = {account.name: account for account in accounts}
        with connection:
            for account in configured.values():
                row = connection.execute(
                    "SELECT account_name FROM accounts WHERE account_name = ?", (account.name,)
                ).fetchone()
                if row is None:
                    self._upsert(
                        account.name,
                        AccountStatus.NEW if account.enabled else AccountStatus.DISABLED,
                        next_attempt_at=now if account.enabled else None,
                        updated_at=now,
                    )
                    self.add_event(account.name, "ACCOUNT_CREATED", now)
                elif not account.enabled:
                    self._upsert(account.name, AccountStatus.DISABLED, updated_at=now)
                elif (existing := self.get(account.name)) is not None and existing.status is AccountStatus.DISABLED:
                    self._upsert(
                        account.name, AccountStatus.READY, next_attempt_at=now, updated_at=now
                    )
            for row in connection.execute("SELECT account_name FROM accounts"):
                if row["account_name"] not in configured:
                    self._upsert(row["account_name"], AccountStatus.DISABLED, updated_at=now)


    def cap_success_schedules(self, interval_days: int, now: datetime) -> None:
        """Bring successful accounts forward to the configured periodic verification cadence."""
        interval = timedelta(days=interval_days)
        for state in self.all():
            if state.status is not AccountStatus.SUCCESS or state.last_success_at is None:
                continue
            weekly_attempt = state.last_success_at + interval
            if state.next_attempt_at is not None and state.next_attempt_at <= weekly_attempt:
                continue
            updated = replace(state, next_attempt_at=weekly_attempt, updated_at=now)
            self.update(updated, "SUCCESS_CHECK_RESCHEDULED")
    def get(self, account_name: str) -> AccountState | None:
        row = self._connection().execute(
            "SELECT * FROM accounts WHERE account_name = ?", (account_name,)
        ).fetchone()
        return self._to_state(row) if row else None

    def due_accounts(self, now: datetime) -> list[AccountState]:
        rows = self._connection().execute(
            "SELECT * FROM accounts WHERE status != ? AND next_attempt_at IS NOT NULL "
            "AND next_attempt_at <= ? ORDER BY next_attempt_at, account_name",
            (AccountStatus.DISABLED.value, _encode(now)),
        ).fetchall()
        return [self._to_state(row) for row in rows]

    def next_attempt(self) -> datetime | None:
        row = self._connection().execute(
            "SELECT next_attempt_at FROM accounts WHERE status != ? AND next_attempt_at IS NOT NULL "
            "ORDER BY next_attempt_at LIMIT 1",
            (AccountStatus.DISABLED.value,),
        ).fetchone()
        return _decode_datetime(row["next_attempt_at"]) if row else None

    def update(self, state: AccountState, event_type: str, details: str | None = None) -> None:
        with self._connection():
            self._upsert(
                state.account_name, state.status, state.last_attempt_at, state.last_success_at,
                state.next_required_login, state.next_attempt_at, state.consecutive_failures,
                state.last_error, state.updated_at,
            )
            self.add_event(state.account_name, event_type, state.updated_at, details)

    def add_event(self, account_name: str, event_type: str, timestamp: datetime, details: str | None = None) -> None:
        self._connection().execute(
            "INSERT INTO account_events(account_name, event_type, timestamp, details) VALUES (?, ?, ?, ?)",
            (account_name, event_type, _encode(timestamp), details),
        )

    def all(self) -> list[AccountState]:
        return [self._to_state(row) for row in self._connection().execute("SELECT * FROM accounts ORDER BY account_name")]

    def _upsert(
        self,
        account_name: str,
        status: AccountStatus,
        last_attempt_at: datetime | None = None,
        last_success_at: datetime | None = None,
        next_required_login: date | None = None,
        next_attempt_at: datetime | None = None,
        consecutive_failures: int = 0,
        last_error: str | None = None,
        updated_at: datetime | None = None,
    ) -> None:
        self._connection().execute(
            """INSERT INTO accounts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(account_name) DO UPDATE SET status=excluded.status,
               last_attempt_at=COALESCE(excluded.last_attempt_at, accounts.last_attempt_at),
               last_success_at=COALESCE(excluded.last_success_at, accounts.last_success_at),
               next_required_login=excluded.next_required_login, next_attempt_at=excluded.next_attempt_at,
               consecutive_failures=excluded.consecutive_failures, last_error=excluded.last_error,
               updated_at=excluded.updated_at""",
            (account_name, status.value, _encode(last_attempt_at), _encode(last_success_at),
             next_required_login.isoformat() if next_required_login else None, _encode(next_attempt_at),
             consecutive_failures, last_error, _encode(updated_at or datetime.now(UTC))),
        )

    def _connection(self) -> sqlite3.Connection:
        if self.connection is None:
            raise RuntimeError("repository is not open")
        return self.connection

    @staticmethod
    def _to_state(row: sqlite3.Row) -> AccountState:
        updated_at = _decode_datetime(row["updated_at"])
        if updated_at is None:
            raise RuntimeError("database invariant violated: accounts.updated_at is NULL")
        return AccountState(
            row["account_name"],
            AccountStatus(row["status"]),
            _decode_datetime(row["last_attempt_at"]),
            _decode_datetime(row["last_success_at"]),
            date.fromisoformat(row["next_required_login"])
            if row["next_required_login"]
            else None,
            _decode_datetime(row["next_attempt_at"]),
            row["consecutive_failures"],
            row["last_error"],
            updated_at,
        )


def _encode(value: datetime | None) -> str | None:
    return value.astimezone(UTC).isoformat() if value else None


def _decode_datetime(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None
