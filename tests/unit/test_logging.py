import json
import logging

from orange_einvoice.observability.logging import JsonFormatter


def test_json_formatter_whitelists_safe_diagnostic_fields() -> None:
    record = logging.LogRecord(
        name="orange_einvoice.orange.client",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="orange_otp_submit_clicked",
        args=(),
        exc_info=None,
    )
    record.field_count = 1
    record.waited_ms = 250
    record.otp = "123456"
    record.password = "secret"
    record.cookie = "session-value"

    payload = json.loads(JsonFormatter().format(record))

    assert payload["event"] == "orange_otp_submit_clicked"
    assert payload["field_count"] == 1
    assert payload["waited_ms"] == 250
    assert "123456" not in json.dumps(payload)
    assert "secret" not in json.dumps(payload)
    assert "session-value" not in json.dumps(payload)
