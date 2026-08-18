from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, timedelta


def normalize_header(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "").encode("ASCII", "ignore").decode()
    return re.sub(r"[^A-Z0-9]+", "_", text.upper()).strip("_")


def parse_sheet_date(value: object) -> date | None:
    if value is None or str(value).strip() == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if value < 1 or value > 100000:
            raise ValueError("serial de data fora do intervalo aceito")
        return date(1899, 12, 30) + timedelta(days=float(value))
    raw = str(value).strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    raise ValueError("data inválida; formatos aceitos: dd/MM/yyyy, yyyy-MM-dd ou serial")


def mask_email(value: str | None) -> str | None:
    if not value or "@" not in value:
        return None
    local, domain = value.split("@", 1)
    return f"{local[:1]}***@{domain}"
