"""T5-06 / T5-08 / T5-11 — alert copy builders + wording policy.

The wording policy test is the critical one: it fails loudly if any
banned phrase (see `BANNED_PHRASES`) ever lands in a builder output.
That keeps the "never say 'хулгайч'" rule from rotting as we add
new channels / severities / languages.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SHOPLIFT = ROOT / "shoplift_detector"
if str(SHOPLIFT) not in sys.path:
    sys.path.insert(0, str(SHOPLIFT))

os.environ.setdefault("SECRET_KEY", "test-secret-copy")

from app.services.alert_copy import (  # noqa: E402
    BANNED_PHRASES,
    DISCLAIMER_EN,
    DISCLAIMER_MN,
    build_email_bodies,
    build_email_subject,
    build_fcm_payload,
    build_sms_body,
    severity_header,
)


# ---------------------------------------------------------------------------
# Headers
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("severity,lang,expected_fragment", [
    ("red", "mn", "Яаралтай"),
    ("orange", "mn", "Анхаарах"),
    ("yellow", "mn", "Хянаж"),
    ("red", "en", "Urgent"),
    ("orange", "en", "Review"),
    ("yellow", "en", "Watching"),
])
def test_severity_header_language(severity, lang, expected_fragment):
    assert expected_fragment in severity_header(severity, lang)


# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------

def test_email_subject_has_store_name_and_severity():
    s = build_email_subject(store_name="Номин", severity="red", language="mn")
    assert "Номин" in s
    assert "Яаралтай" in s


def test_email_bodies_include_context_and_disclaimer_mn():
    text, html = build_email_bodies(
        store_name="Номин",
        camera_name="Main door",
        reason="Бараа авах",
        score=87.4,
        severity="red",
        language="mn",
    )
    assert "Номин" in text and "Main door" in text and "Бараа авах" in text
    assert "87" in text  # score rounded
    assert DISCLAIMER_MN in text
    assert "87" in html
    assert "Номин" in html


def test_email_inline_snapshot_cid_when_supplied():
    _text, html = build_email_bodies(
        store_name="S", camera_name="C", reason="R", score=None,
        severity="orange", language="en", snapshot_cid="snap-1",
    )
    assert 'cid:snap-1' in html
    assert DISCLAIMER_EN in html


def test_email_html_omits_image_when_no_cid():
    _text, html = build_email_bodies(
        store_name="S", camera_name="C", reason="R", score=None,
        severity="orange", language="en",
    )
    assert "cid:" not in html


# ---------------------------------------------------------------------------
# SMS
# ---------------------------------------------------------------------------

def test_sms_body_mentions_store_and_header():
    body = build_sms_body(store_name="Номин", severity="red")
    assert "Номин" in body
    assert "Яаралтай" in body


def test_sms_body_single_segment():
    """GSM-7 SMS caps single-segment at 160 chars. Going over costs
    the tenant real money; guard against creep."""
    body = build_sms_body(store_name="Номин супермаркет ХХК", severity="red")
    assert len(body) <= 160


# ---------------------------------------------------------------------------
# FCM
# ---------------------------------------------------------------------------

def test_fcm_payload_shape():
    p = build_fcm_payload(
        store_name="Номин", camera_name="Main",
        severity="red", alert_id=42, language="mn",
    )
    assert p["notification"]["title"].startswith("Номин")
    assert p["notification"]["body"] == "Main"
    assert p["data"]["alert_id"] == "42"
    assert p["data"]["severity"] == "red"


# ---------------------------------------------------------------------------
# T5-11 — wording policy
# ---------------------------------------------------------------------------

def _all_copy_outputs() -> list[str]:
    """Exercise every builder with every severity × language combo
    and return the concatenated strings. Any banned phrase lurking
    in a template will surface here."""
    out: list[str] = []
    for severity in ("yellow", "orange", "red"):
        for lang in ("mn", "en"):
            out.append(severity_header(severity, lang))
            out.append(build_email_subject(
                store_name="S", severity=severity, language=lang
            ))
            text, html = build_email_bodies(
                store_name="S", camera_name="C", reason="барааг зөөх",
                score=99.9, severity=severity, language=lang,
            )
            out.extend([text, html])
            if severity == "red":
                out.append(build_sms_body(store_name="S", severity=severity))
            fcm = build_fcm_payload(
                store_name="S", camera_name="C",
                severity=severity, alert_id=1, language=lang,
            )
            out.extend([fcm["notification"]["title"], fcm["notification"]["body"]])
    return out


@pytest.mark.parametrize("banned", BANNED_PHRASES)
def test_no_builder_output_contains_banned_wording(banned):
    """T5-11 — hard guarantee across every copy surface."""
    lower = banned.lower()
    for text in _all_copy_outputs():
        assert lower not in text.lower(), (
            f"banned phrase {banned!r} leaked into alert copy: {text!r}"
        )


def test_disclaimer_present_in_both_languages():
    """Policy requires the legal disclaimer on every email, both
    languages. Spot-check one severity — the property test above
    covers the matrix."""
    text_mn, html_mn = build_email_bodies(
        store_name="S", camera_name="C", reason="R", score=None,
        severity="red", language="mn",
    )
    text_en, html_en = build_email_bodies(
        store_name="S", camera_name="C", reason="R", score=None,
        severity="red", language="en",
    )
    assert DISCLAIMER_MN in text_mn and DISCLAIMER_MN in html_mn
    assert DISCLAIMER_EN in text_en and DISCLAIMER_EN in html_en
