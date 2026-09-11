from __future__ import annotations

import asyncio
import getpass

import typer

from orange_einvoice.application import Application, status_json
from orange_einvoice.config import Settings
from orange_einvoice.observability import configure_logging

app = typer.Typer(no_args_is_help=True, add_completion=False)


def settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # required fields come from ORANGE_* environment


@app.command()
def run() -> None:
    """Run the persistent, interruptible state-driven scheduler."""
    configure_logging()
    asyncio.run(Application(settings()).run())


@app.command("run-once")
def run_once(account: str | None = typer.Argument(None)) -> None:
    """Process enabled accounts once, without entering the scheduler."""
    configure_logging()
    asyncio.run(Application(settings()).run_once(account))


@app.command()
def bootstrap(account: str, otp: str | None = typer.Option(None, help="One-time code; omit to enter it interactively")) -> None:
    """Run an interactive profile bootstrap; the OTP is never stored or logged."""
    configure_logging()
    result = asyncio.run(Application(settings()).bootstrap(account, otp))
    if result.status.value == "otp_required" and otp is None:
        code = getpass.getpass("Orange OTP (empty to leave pending): ").strip()
        if code:
            result = asyncio.run(Application(settings()).bootstrap(account, code))
    typer.echo(f"{account}: {result.status.value}")


@app.command()
def status() -> None:
    """Print persisted account state; passwords, OTPs, and cookies are never included."""
    typer.echo(status_json(settings()))


if __name__ == "__main__":
    app()
