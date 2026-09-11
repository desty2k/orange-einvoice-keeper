"""Centralized, intentionally conservative Orange UI selectors.

Verify these against the current Orange portal before first production use.  Accessibility
roles and labels are preferred; fallback CSS selectors prevent DOM details leaking elsewhere.
"""

EMAIL_INPUT = 'input[type="email"]'
PASSWORD_INPUT = 'input[type="password"]'
SUBMIT_BUTTON = 'button[type="submit"]'
OTP_INPUT = 'input[autocomplete="one-time-code"], input[name*="otp" i], input[name*="code" i]'
OTP_MARKERS = ("kod jednorazowy", "kod sms", "verification code", "two-factor")
INVALID_CREDENTIAL_MARKERS = ("nieprawidłowe", "invalid credentials", "incorrect password")
DASHBOARD_MARKERS = ("wyloguj", "moje konto", "dashboard")
NEXT_LOGIN_MARKERS = ("następne logowanie", "next login", "zaloguj się do")
