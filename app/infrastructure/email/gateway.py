from __future__ import annotations

import json
import smtplib
from email.message import EmailMessage
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.configuration.settings import Settings
from app.domain.exceptions.core import ExternalServiceUnavailable


class SMTPEmailGateway:
    def __init__(self, settings: Settings):
        self.settings = settings

    def send(self, *, recipients: list[str], subject: str, text: str, html: str) -> str | None:
        if not self.settings.mail_enabled:
            return None
        if not self.settings.mail_from:
            raise ExternalServiceUnavailable("remetente de e-mail não configurado")
        if self.settings.mail_provider == "brevo":
            return self._send_with_brevo(recipients=recipients, subject=subject, html=html)
        if not self.settings.mail_host:
            raise ExternalServiceUnavailable("SMTP não configurado")
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = self.settings.mail_from
        message["To"] = ", ".join(recipients)
        message.set_content(text)
        message.add_alternative(html, subtype="html")
        try:
            with smtplib.SMTP(self.settings.mail_host, self.settings.mail_port, timeout=30) as smtp:
                if self.settings.mail_use_tls:
                    smtp.starttls()
                if self.settings.mail_username and self.settings.mail_password:
                    smtp.login(
                        self.settings.mail_username, self.settings.mail_password.get_secret_value()
                    )
                smtp.send_message(message)
            return message["Message-ID"]
        except (OSError, smtplib.SMTPException) as error:
            raise ExternalServiceUnavailable("falha ao enviar e-mail") from error

    def _send_with_brevo(self, *, recipients: list[str], subject: str, html: str) -> str:
        if self.settings.brevo_api_key is None:
            raise ExternalServiceUnavailable("Brevo não configurado")
        payload = json.dumps(
            {
                "sender": {"name": self.settings.app_name, "email": self.settings.mail_from},
                "to": [{"email": recipient} for recipient in recipients],
                "subject": subject,
                "htmlContent": html,
            }
        ).encode("utf-8")
        request = Request(
            "https://api.brevo.com/v3/smtp/email",
            data=payload,
            headers={
                "accept": "application/json",
                "api-key": self.settings.brevo_api_key.get_secret_value(),
                "content-type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.settings.request_timeout_seconds) as response:
                if response.status >= 300:
                    raise ExternalServiceUnavailable("falha ao enviar e-mail pelo Brevo")
                body = json.loads(response.read().decode("utf-8"))
                message_id = body.get("messageId")
                if not message_id:
                    raise ExternalServiceUnavailable("Brevo não confirmou o envio do e-mail")
                return str(message_id)
        except HTTPError as error:
            response_body = error.read().decode("utf-8", errors="replace")
            raise ExternalServiceUnavailable(
                self._brevo_http_error(error.code, response_body)
            ) from error
        except (URLError, OSError, ValueError) as error:
            raise ExternalServiceUnavailable("não foi possível conectar ao Brevo") from error

    @staticmethod
    def _brevo_http_error(status: int, response_body: str) -> str:
        try:
            provider_message = str(json.loads(response_body).get("message", "")).strip()
        except (TypeError, ValueError):
            provider_message = ""
        normalized_message = provider_message.casefold()
        if "ip" in normalized_message and "authoriz" in normalized_message:
            return "Brevo bloqueou o IP de origem da automação"
        messages = {
            400: "Brevo recusou o envio: confirme o remetente e os e-mails informados",
            401: "chave de API do Brevo inválida ou ausente",
            403: "chave de API do Brevo sem permissão para envio",
            429: "limite diário de envios do Brevo atingido",
        }
        message = messages.get(status, f"Brevo recusou o envio (HTTP {status})")
        if provider_message:
            return f"{message}: {provider_message[:180]}"
        return message
