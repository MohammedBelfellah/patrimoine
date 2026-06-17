import base64
import json
import logging
from email.utils import parseaddr
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend


logger = logging.getLogger(__name__)


class BrevoApiEmailBackend(BaseEmailBackend):
    """Send Django EmailMessage objects through Brevo's HTTPS API."""

    def __init__(self, fail_silently=False, **kwargs):
        super().__init__(fail_silently=fail_silently)
        self.api_key = getattr(settings, "BREVO_API_KEY", "")
        self.api_url = getattr(settings, "BREVO_API_URL", "https://api.brevo.com/v3/smtp/email")
        self.timeout = getattr(settings, "BREVO_API_TIMEOUT", 15)

    def send_messages(self, email_messages):
        if not email_messages:
            return 0

        sent_count = 0
        for message in email_messages:
            try:
                self._send_message(message)
            except Exception:
                logger.exception("Brevo API email send failed")
                if not self.fail_silently:
                    raise
            else:
                sent_count += 1
        return sent_count

    def _send_message(self, message):
        if not self.api_key:
            raise RuntimeError("BREVO_API_KEY is required when using BrevoApiEmailBackend")

        payload = self._build_payload(message)
        request = Request(
            self.api_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "api-key": self.api_key,
                "User-Agent": "GeoPatrimoineHub/1.0",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                response.read()
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Brevo API rejected email: HTTP {exc.code} {body}") from exc
        except URLError as exc:
            raise RuntimeError(f"Brevo API connection failed: {exc}") from exc

    def _build_payload(self, message):
        sender_name, sender_email = parseaddr(message.from_email or settings.DEFAULT_FROM_EMAIL)
        if not sender_email:
            _, sender_email = parseaddr(settings.DEFAULT_FROM_EMAIL)

        payload = {
            "sender": {"email": sender_email},
            "to": self._addresses(message.to),
            "subject": message.subject,
        }
        if sender_name:
            payload["sender"]["name"] = sender_name

        html_content = None
        for content, mimetype in getattr(message, "alternatives", []):
            if mimetype == "text/html":
                html_content = content
                break

        if getattr(message, "content_subtype", "") == "html":
            payload["htmlContent"] = message.body
        else:
            payload["textContent"] = message.body or ""
            if html_content:
                payload["htmlContent"] = html_content

        if message.cc:
            payload["cc"] = self._addresses(message.cc)
        if message.bcc:
            payload["bcc"] = self._addresses(message.bcc)
        if message.reply_to:
            reply_name, reply_email = parseaddr(message.reply_to[0])
            payload["replyTo"] = {"email": reply_email}
            if reply_name:
                payload["replyTo"]["name"] = reply_name

        attachments = self._attachments(message)
        if attachments:
            payload["attachment"] = attachments

        return payload

    def _addresses(self, addresses):
        parsed = []
        for address in addresses:
            name, email = parseaddr(address)
            if not email:
                continue
            item = {"email": email}
            if name:
                item["name"] = name
            parsed.append(item)
        return parsed

    def _attachments(self, message):
        attachments = []
        for attachment in getattr(message, "attachments", []):
            filename, content, mimetype = attachment
            if isinstance(content, str):
                content = content.encode("utf-8")
            item = {
                "name": filename,
                "content": base64.b64encode(content).decode("ascii"),
            }
            if mimetype:
                item["type"] = mimetype
            attachments.append(item)
        return attachments
