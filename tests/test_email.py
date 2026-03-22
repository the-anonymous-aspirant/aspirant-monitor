import pytest
from unittest.mock import patch, AsyncMock

from app.email import send_email


@pytest.mark.asyncio
class TestSendEmail:
    @patch("app.email.email_enabled", return_value=False)
    async def test_skips_when_not_configured(self, _):
        result = await send_email("Test", "Body")
        assert result is False

    @patch("app.email.email_enabled", return_value=True)
    @patch("app.email.aiosmtplib.send", new_callable=AsyncMock)
    async def test_sends_email_successfully(self, mock_send, _):
        result = await send_email("Test Subject", "Test Body")
        assert result is True
        mock_send.assert_called_once()

    @patch("app.email.email_enabled", return_value=True)
    @patch("app.email.aiosmtplib.send", new_callable=AsyncMock, side_effect=Exception("SMTP error"))
    async def test_returns_false_on_smtp_failure(self, mock_send, _):
        result = await send_email("Test Subject", "Test Body")
        assert result is False
