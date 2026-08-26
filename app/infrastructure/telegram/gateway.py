from __future__ import annotations

import json
from urllib.error import URLError
from urllib.request import Request, urlopen

from app.configuration.settings import Settings
from app.domain.exceptions.core import ExternalServiceUnavailable


class TelegramGateway:
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
        payload = json.dumps(
            {
                "chat_id": target_chat_id,
                "text": message[:4096],
                "disable_web_page_preview": True,
            }
        ).encode()
        request = Request(
            f"https://api.telegram.org/bot{self.settings.telegram_bot_token.get_secret_value()}/sendMessage",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.settings.request_timeout_seconds) as response:
                if response.status >= 300:
                    raise ExternalServiceUnavailable("falha ao enviar resumo pelo Telegram")
                body = json.loads(response.read().decode())
                if not body.get("ok"):
                    raise ExternalServiceUnavailable("falha ao enviar resumo pelo Telegram")
            return True
        except (OSError, ValueError, URLError) as error:
            raise ExternalServiceUnavailable("falha ao enviar resumo pelo Telegram") from error
