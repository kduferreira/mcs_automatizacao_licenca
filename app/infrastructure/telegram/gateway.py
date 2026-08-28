from __future__ import annotations

import json
from urllib.error import URLError
from urllib.request import Request, urlopen

from app.configuration.settings import Settings
from app.domain.exceptions.core import ExternalServiceUnavailable


class TelegramGateway:
    max_message_length = 4096

    def __init__(self, settings: Settings):
        self.settings = settings

    @property
    def enabled(self) -> bool:
        return bool(self.settings.telegram_enabled and self.settings.telegram_bot_token)

    def configured_for(self, chat_id: str | None = None) -> bool:
        return self.enabled and bool(chat_id or self.settings.telegram_chat_id)

    def send_summary(self, message: str, chat_id: str | None = None) -> bool:
        if not self.settings.telegram_enabled:
            return False
        target_chat_id = chat_id or self.settings.telegram_chat_id
        if not self.configured_for(target_chat_id):
            raise ExternalServiceUnavailable("Telegram não configurado")
        try:
            for part in self._message_parts(message):
                payload = json.dumps(
                    {
                        "chat_id": target_chat_id,
                        "text": part,
                        "disable_web_page_preview": True,
                    }
                ).encode()
                request = Request(
                    f"https://api.telegram.org/bot{self.settings.telegram_bot_token.get_secret_value()}/sendMessage",
                    data=payload,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urlopen(request, timeout=self.settings.request_timeout_seconds) as response:
                    if response.status >= 300:
                        raise ExternalServiceUnavailable("falha ao enviar resumo pelo Telegram")
                    body = json.loads(response.read().decode())
                    if not body.get("ok"):
                        raise ExternalServiceUnavailable("falha ao enviar resumo pelo Telegram")
            return True
        except (OSError, ValueError, URLError) as error:
            raise ExternalServiceUnavailable("falha ao enviar resumo pelo Telegram") from error

    @classmethod
    def _message_parts(cls, message: str) -> list[str]:
        """Preserva o texto e separa lotes grandes no limite do Telegram."""
        if len(message) <= cls.max_message_length:
            return [message]
        parts: list[str] = []
        current = ""
        for line in message.splitlines(keepends=True):
            if len(current) + len(line) <= cls.max_message_length:
                current += line
                continue
            if current:
                parts.append(current)
                current = ""
            while len(line) > cls.max_message_length:
                parts.append(line[: cls.max_message_length])
                line = line[cls.max_message_length :]
            current = line
        if current:
            parts.append(current)
        return parts
