"""Demo-safe SMS confirmations via Textbelt (US endpoint)."""
import json
import logging
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

log = logging.getLogger(__name__)

TEXTBELT_URL = "https://textbelt.com/text"
TIMEOUT_S = 4
MAX_LEN = 600
_URL_RE = re.compile(r"(https?://|www\.|\b[\w-]+\.(com|net|org|io|ly|co|me|app|dev|ai|us)\b)", re.I)
_TRANSIENT_ERROR = re.compile(
    r"try again later|temporarily unavailable|rate limit|too many requests", re.I
)


def _is_plain(message):
    if not isinstance(message, str) or not message.strip() or len(message) > MAX_LEN:
        return False
    if _URL_RE.search(message):
        return False
    return all(c.isprintable() or c in "\n" for c in message)


def send_confirmation(phone, message) -> bool:
    """Send SMS only to the configured demo number. Returns True if Textbelt accepts."""
    key = os.environ.get("TEXTBELT_KEY", "").strip()
    demo_to = os.environ.get("DEMO_SMS_TO", "").strip()
    if not key or not demo_to:
        log.info("sms: preview mode (not configured)")
        return False
    if not isinstance(phone, str) or phone != demo_to:
        log.info("sms: blocked (recipient not allowlisted)")
        return False
    if not _is_plain(message):
        log.info("sms: blocked (message not URL-free plaintext)")
        return False

    data = urllib.parse.urlencode({"phone": phone, "message": message, "key": key}).encode()
    req = urllib.request.Request(TEXTBELT_URL, data=data, method="POST")
    for attempt in (1, 2):
        status = 200
        try:
            try:
                with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
                    result = json.load(resp)
            except urllib.error.HTTPError as exc:
                status = exc.code
                with exc:
                    result = json.load(exc)
        except (OSError, ValueError) as exc:
            log.warning("sms: Textbelt request failed (HTTP %d, %s)", status, type(exc).__name__)
            return False

        if not isinstance(result, dict):
            log.warning("sms: unexpected Textbelt response (HTTP %d)", status)
            return False
        if result.get("success") is True:
            text_id = str(result.get("textId", ""))
            log.info("sms: Textbelt accepted (textId=%s)", text_id if text_id.isdecimal() else "unavailable")
            return True

        error = str(result.get("error") or "No error detail returned")
        for value in (key, phone, phone.removeprefix("+1"), message):
            error = error.replace(value, "[redacted]")
            error = error.replace(urllib.parse.quote_plus(value), "[redacted]")
        log.warning("sms: Textbelt rejected attempt %d (HTTP %d): %s",
                    attempt, status, " ".join(error.split())[:300])
        # Retry only when Textbelt explicitly confirms it rejected the send.
        if attempt == 2 or result.get("success") is not False:
            return False
        if status != 429 and not _TRANSIENT_ERROR.search(error):
            return False
        time.sleep(0.5)
    return False
