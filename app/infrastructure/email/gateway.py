from __future__ import annotations

import smtplib
from email.message import EmailMessage

from app.configuration.settings import Settings
from app.domain.exceptions.core import ExternalServiceUnavailable


class SMTPEmailGateway:
    def __init__(self, settings: Settings):
        self.settings = settings

    def send(self, *, recipients: list[str], subject: str, text: str, html: str) -> str | None:
        if not self.settings.mail_enabled:
            return None
        if not self.settings.mail_host or not self.settings.mail_from:
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
