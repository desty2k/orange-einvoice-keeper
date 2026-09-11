from datetime import date

from orange_einvoice.models import LoginStatus
from orange_einvoice.orange.parser import classify_page, parse_next_required_login


def test_classifies_otp_before_dashboard_text() -> None:
    assert classify_page("Podaj kod SMS, aby kontynuować. Moje konto") is LoginStatus.OTP_REQUIRED


def test_parses_deadline_near_supported_marker() -> None:
    assert parse_next_required_login("Następne logowanie należy wykonać do 08.10.2026.") == date(2026, 10, 8)


def test_ignores_dates_without_deadline_context() -> None:
    assert parse_next_required_login("Dzisiaj jest 08.10.2026") is None
