"""POST /report/send (system_3 #8739): system_3 emails the operator a report
through the monitor's one configured mailbox. The three constraints from the
channel decision (c53666 on #8712): one fixed recipient and no caller-supplied
address, a size cap, auth from system_3 only."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from app import config

TOKEN = "s3-test-token-0123456789"
OK = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def send_enabled():
    with patch.object(config, "REPORT_SEND_TOKEN", TOKEN), patch("app.routes.config.email_enabled", return_value=True):
        yield


@pytest.fixture
def send_email_mock():
    with patch("app.routes.send_email", new_callable=AsyncMock, return_value=True) as m:
        yield m


def test_disabled_when_token_unset(client, send_email_mock):
    with patch.object(config, "REPORT_SEND_TOKEN", ""):
        resp = client.post("/report/send", json={"subject": "s", "body": "b"}, headers=OK)
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "send_disabled"
    send_email_mock.assert_not_called()


def test_missing_and_wrong_token_are_refused_alike(client, send_enabled, send_email_mock):
    missing = client.post("/report/send", json={"subject": "s", "body": "b"})
    wrong = client.post("/report/send", json={"subject": "s", "body": "b"}, headers={"Authorization": "Bearer nope"})
    basic = client.post("/report/send", json={"subject": "s", "body": "b"}, headers={"Authorization": f"Basic {TOKEN}"})
    for resp in (missing, wrong, basic):
        assert resp.status_code == 401
        assert resp.json() == {"error": {"code": "unauthorized", "message": "A valid system_3 bearer token is required"}}
    send_email_mock.assert_not_called()


def test_caller_supplied_recipient_is_refused(client, send_enabled, send_email_mock):
    resp = client.post("/report/send", json={"subject": "s", "body": "b", "to": "x@example.com"}, headers=OK)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "unknown_field"
    assert "to" in resp.json()["error"]["message"]
    send_email_mock.assert_not_called()


def test_over_cap_request_is_refused_before_parsing(client, send_enabled, send_email_mock):
    big = {"subject": "s", "body": "x" * (config.REPORT_SEND_MAX_REQUEST_BYTES + 10)}
    resp = client.post("/report/send", json=big, headers=OK)
    assert resp.status_code == 413
    assert resp.json()["error"]["code"] == "too_large"
    send_email_mock.assert_not_called()


def test_over_cap_fields_are_refused(client, send_enabled, send_email_mock):
    body_big = {"subject": "s", "body": "x" * (config.REPORT_SEND_MAX_BODY_BYTES + 1)}
    subject_big = {"subject": "s" * (config.REPORT_SEND_MAX_SUBJECT_CHARS + 1), "body": "b"}
    html_big = {"subject": "s", "body": "b", "html": "<p>" + "x" * config.REPORT_SEND_MAX_HTML_BYTES}
    for payload in (body_big, subject_big, html_big):
        resp = client.post("/report/send", json=payload, headers=OK)
        assert resp.status_code == 413, payload.keys()
        assert resp.json()["error"]["code"] == "too_large"
    send_email_mock.assert_not_called()


def test_malformed_bodies_are_refused(client, send_enabled, send_email_mock):
    not_json = client.post("/report/send", content=b"not json", headers={**OK, "Content-Type": "application/json"})
    assert not_json.status_code == 400
    a_list = client.post("/report/send", json=["subject"], headers=OK)
    assert a_list.status_code == 400
    empty_subject = client.post("/report/send", json={"subject": "  ", "body": "b"}, headers=OK)
    assert empty_subject.status_code == 422
    multiline_subject = client.post("/report/send", json={"subject": "s\nBcc: x@example.com", "body": "b"}, headers=OK)
    assert multiline_subject.status_code == 422
    html_not_str = client.post("/report/send", json={"subject": "s", "body": "b", "html": 5}, headers=OK)
    assert html_not_str.status_code == 422
    send_email_mock.assert_not_called()


def test_email_not_configured_is_503(client, send_email_mock):
    with patch.object(config, "REPORT_SEND_TOKEN", TOKEN), patch("app.routes.config.email_enabled", return_value=False):
        resp = client.post("/report/send", json={"subject": "s", "body": "b"}, headers=OK)
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "email_not_configured"
    send_email_mock.assert_not_called()


def test_happy_path_sends_to_the_fixed_recipient_only(client, send_enabled, send_email_mock):
    payload = {"subject": "Weekly report 2026-W43", "body": "Plain text", "html": "<p>Plain text</p>"}
    resp = client.post("/report/send", json=payload, headers=OK)
    assert resp.status_code == 202
    assert resp.json() == {"sent": True}
    send_email_mock.assert_awaited_once_with("Weekly report 2026-W43", "Plain text", html="<p>Plain text</p>")
    # The sender takes no recipient: the address is ALERT_EMAIL_TO inside send_email.
    assert "to" not in send_email_mock.call_args.kwargs


def test_smtp_failure_is_502(client, send_enabled):
    with patch("app.routes.send_email", new_callable=AsyncMock, return_value=False):
        resp = client.post("/report/send", json={"subject": "s", "body": "b"}, headers=OK)
    assert resp.status_code == 502
    assert resp.json()["error"]["code"] == "send_failed"


def test_request_cap_is_the_configured_value():
    assert config.REPORT_SEND_MAX_REQUEST_BYTES == 64 * 1024
    assert json.dumps({"subject": "s", "body": "b"}).encode()  # the smallest valid request is far under it
