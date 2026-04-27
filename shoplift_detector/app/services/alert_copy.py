"""Alert-facing copy — Mongolian + English (T5-06, T5-08, T5-11).

Single source of truth for the user-visible wording of every alert
channel. Centralising this serves two goals:

1. **Wording policy (T5-11).** Product guidelines forbid "Хулгайч" /
   "Гэмт хэрэгтэн" in any customer-facing text. Every string that
   describes an alert flows through here; a lint test
   (`tests/test_alert_copy_guidelines.py`) asserts no banned token
   leaks in.
2. **Localisation.** Email + SMS + FCM all need the same facts in two
   languages. Keeping the builders here prevents drift — the email
   subject and the SMS body always agree on what the alert is about.

The builders are deliberately pure: no DB, no I/O. Callers pre-fetch
the alert + store context and pass dicts in.
"""

from __future__ import annotations

from typing import Literal

Language = Literal["mn", "en"]

# Phrases that must never reach a customer-facing surface. Matches
# are case-insensitive. Adding a new banned phrase here is picked up
# by the lint test automatically — no test edit required.
#
# The short forms ("хулгай", "theft") cover Mongolian stem + English
# noun so headers like "Яаралтай: хулгайн магадлал өндөр" also fail
# the policy check. Product guideline (T5-11): describe *behaviour*
# to the user, never the *person* and never the *act*. "Анхаарах
# хэрэгтэй" is the canonical replacement.
BANNED_PHRASES: tuple[str, ...] = (
    "Хулгайч",
    "Гэмт хэрэгтэн",
    "хулгай",
    "criminal",
    "thief",
    "theft",
)

# Legal disclaimer appended to every outbound alert message. The
# product guidelines require this on every channel so a customer who
# only sees the SMS still gets the "this is an assist, not a verdict"
# framing.
DISCLAIMER_MN = (
    "AI нь зөвхөн сэжигтэй зан үйлийг тэмдэглэдэг бөгөөд хүний "
    "шалгалт шаардлагатай. Алдаа гарах магадлалтай."
)
DISCLAIMER_EN = (
    "AI flags suspicious behaviour only — human review required. "
    "False positives possible."
)


_SEVERITY_HEADERS: dict[str, dict[str, str]] = {
    "red": {
        "mn": "Яаралтай: анхаарах хэрэгтэй",
        "en": "Urgent: review required",
    },
    "orange": {
        "mn": "Анхаарах хэрэгтэй",
        "en": "Review recommended",
    },
    "yellow": {
        "mn": "Хянаж байна",
        "en": "Watching",
    },
    # green never reaches a channel — but keep the key so lookups are
    # total.
    "green": {
        "mn": "Хэвийн",
        "en": "Normal",
    },
}


def severity_header(severity: str, language: Language = "mn") -> str:
    return _SEVERITY_HEADERS.get(severity, _SEVERITY_HEADERS["orange"])[language]


def build_email_subject(*, store_name: str, severity: str, language: Language) -> str:
    header = severity_header(severity, language)
    if language == "en":
        return f"[{store_name}] {header}"
    return f"[{store_name}] {header}"


def build_email_bodies(
    *,
    store_name: str,
    camera_name: str,
    reason: str,
    score: float | None,
    severity: str,
    language: Language,
    snapshot_cid: str | None = None,
) -> tuple[str, str]:
    """Return (text_body, html_body).

    Inline snapshot: when `snapshot_cid` is supplied the HTML body
    references `cid:{snapshot_cid}` so a MIME/Resend attachment can
    resolve it. When None the HTML just omits the image.
    """
    header = severity_header(severity, language)
    score_line = (
        (f"Score: {score:.0f}" if score is not None else "")
        if language == "en"
        else (f"Магадлал: {score:.0f}" if score is not None else "")
    )

    if language == "en":
        text_body = (
            f"{header}\n\n"
            f"Store: {store_name}\n"
            f"Camera: {camera_name}\n"
            f"Reason: {reason}\n"
            f"{score_line}\n\n"
            f"— {DISCLAIMER_EN}"
        )
        img_html = (
            f'<img src="cid:{snapshot_cid}" alt="snapshot" '
            f'style="max-width:480px;border-radius:8px;"/>'
            if snapshot_cid
            else ""
        )
        html_body = (
            f"<div style=\"font-family:sans-serif\">"
            f"<h2 style=\"color:#b91c1c\">{header}</h2>"
            f"<p><b>Store:</b> {store_name}<br/>"
            f"<b>Camera:</b> {camera_name}<br/>"
            f"<b>Reason:</b> {reason}<br/>"
            f"{score_line}</p>"
            f"{img_html}"
            f"<hr style=\"border:0;border-top:1px solid #e5e7eb;margin:16px 0\"/>"
            f"<p style=\"color:#6b7280;font-size:12px\">{DISCLAIMER_EN}</p>"
            f"</div>"
        )
        return text_body, html_body

    # Mongolian
    text_body = (
        f"{header}\n\n"
        f"Дэлгүүр: {store_name}\n"
        f"Камер: {camera_name}\n"
        f"Шалтгаан: {reason}\n"
        f"{score_line}\n\n"
        f"— {DISCLAIMER_MN}"
    )
    img_html = (
        f'<img src="cid:{snapshot_cid}" alt="зураг" '
        f'style="max-width:480px;border-radius:8px;"/>'
        if snapshot_cid
        else ""
    )
    html_body = (
        f"<div style=\"font-family:sans-serif\">"
        f"<h2 style=\"color:#b91c1c\">{header}</h2>"
        f"<p><b>Дэлгүүр:</b> {store_name}<br/>"
        f"<b>Камер:</b> {camera_name}<br/>"
        f"<b>Шалтгаан:</b> {reason}<br/>"
        f"{score_line}</p>"
        f"{img_html}"
        f"<hr style=\"border:0;border-top:1px solid #e5e7eb;margin:16px 0\"/>"
        f"<p style=\"color:#6b7280;font-size:12px\">{DISCLAIMER_MN}</p>"
        f"</div>"
    )
    return text_body, html_body


def build_sms_body(*, store_name: str, severity: str) -> str:
    """Single-segment SMS body (<=160 chars). No snapshot, no verbose
    reason — SMS is for "check your app NOW" signalling on RED only."""
    header = severity_header(severity, "mn")
    # Intentionally concise: 160-char GSM-7 budget is tight and Twilio
    # bills per segment. Drop the disclaimer on SMS by design — it's
    # enforced via the app UX, not this one-line nudge.
    return f"[{store_name}] {header}. Апп-аар шалгана уу."


def build_fcm_payload(
    *,
    store_name: str,
    camera_name: str,
    severity: str,
    alert_id: int,
    language: Language = "mn",
) -> dict:
    """FCM data-message payload. Kept data-only (not notification) so
    the mobile app can render a consistent UI across iOS/Android."""
    header = severity_header(severity, language)
    return {
        "notification": {
            "title": f"{store_name}: {header}",
            "body": camera_name,
        },
        "data": {
            "alert_id": str(alert_id),
            "store_name": store_name,
            "camera_name": camera_name,
            "severity": severity,
        },
    }


__all__ = [
    "BANNED_PHRASES",
    "DISCLAIMER_EN",
    "DISCLAIMER_MN",
    "Language",
    "build_email_bodies",
    "build_email_subject",
    "build_fcm_payload",
    "build_sms_body",
    "severity_header",
]
