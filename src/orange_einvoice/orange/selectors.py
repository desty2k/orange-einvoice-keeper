"""Centralized, intentionally conservative Orange UI selectors.

Verify these against the current Orange portal before first production use.  Accessibility
roles and labels are preferred; fallback CSS selectors prevent DOM details leaking elsewhere.
"""

# Observed on 2026-09-11: Orange first asks for an email address or phone number.
# It is intentionally a text input, not input[type=email].
IDENTIFIER_INPUT = (
    'input[type="email"], input[placeholder*="e-mail" i], '
    'input[placeholder*="telefon" i]'
)
PASSWORD_INPUT = 'input[type="password"]'
SUBMIT_BUTTON = 'button[type="submit"]'
OTP_INPUT = (
    # Observed on the live Orange OTP screen on 2026-09-11:
    # input#otp_input[name="otp_input"] with placeholder "Kod z SMS-a".
    'input[autocomplete="one-time-code"], '
    'input[name*="otp" i], '
    'input[name*="code" i], '
    'input[data-testid*="otp" i], '
    'input[data-testid*="code" i], '
    'input[inputmode="numeric"][maxlength="1"], '
    'input[inputmode="numeric"][maxlength="6"]'
)
OTP_MARKERS = (
    "kod jednorazowy",
    "kod sms",
    "kod z sms",
    "kod weryfikacyjny",
    "kod potwierdzający",
    "kod potwierdzajacy",
    "kod autoryzacyjny",
    "wpisz kod",
    "podaj kod",
    "wprowadź kod",
    "wprowadz kod",
    "potwierdź logowanie",
    "potwierdz logowanie",
    "verification code",
    "two-factor",
)
INVALID_CREDENTIAL_MARKERS = ("nieprawidłowe", "invalid credentials", "incorrect password")
DASHBOARD_MARKERS = ("wyloguj", "moje konto", "dashboard")
NEXT_LOGIN_MARKERS = ("następne logowanie", "next login", "zaloguj się do")
