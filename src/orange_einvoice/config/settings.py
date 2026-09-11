from __future__ import annotations

from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, EmailStr, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AccountSettings(BaseModel):
    name: Annotated[str, Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")]
    email: EmailStr
    password: SecretStr
    enabled: bool = True


class Settings(BaseSettings):
    """Immutable process configuration, loaded once from ORANGE_* variables."""

    model_config = SettingsConfigDict(env_prefix="ORANGE_", frozen=True, extra="ignore")

    accounts: list[AccountSettings]
    data_dir: Path = Path("/data")
    timezone: str = "Europe/Warsaw"
    login_advance_days: Annotated[int, Field(ge=0, le=60)] = 7
    retry_delay_hours: Annotated[int, Field(ge=1, le=168)] = 6
    otp_retry_delay_hours: Annotated[int, Field(ge=1, le=720)] = 24
    invalid_credentials_retry_delay_hours: Annotated[int, Field(ge=24, le=8760)] = 168
    browser_headless: bool = True
    browser_timeout_ms: Annotated[int, Field(ge=1_000, le=180_000)] = 30_000
    startup_jitter_seconds: Annotated[int, Field(ge=0, le=3_600)] = 120
    schedule_window_start_hour: Annotated[int, Field(ge=0, le=23)] = 3
    schedule_window_hours: Annotated[int, Field(ge=1, le=12)] = 3
    max_concurrency: Annotated[int, Field(ge=1, le=1)] = 1
    login_url: str = "https://www.orange.pl/zaloguj"
    webhook_url: str | None = None
    failure_artifact_retention: Annotated[int, Field(ge=0, le=100)] = 5
    save_failure_html: bool = False
    health_host: str = "0.0.0.0"
    health_port: Annotated[int, Field(ge=1, le=65535)] = 8080

    @field_validator("accounts")
    @classmethod
    def unique_account_names(cls, accounts: list[AccountSettings]) -> list[AccountSettings]:
        if not accounts:
            raise ValueError("at least one account is required")
        names = [account.name for account in accounts]
        if len(names) != len(set(names)):
            raise ValueError("account names must be unique")
        return accounts
