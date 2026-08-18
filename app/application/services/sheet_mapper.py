from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.domain.rules.normalization import normalize_header

AUTOMATION_HEADERS = [
    "ID_AUTOMACAO",
    "ULTIMA_VERIFICACAO",
    "ITEM_MAIS_PROXIMO",
    "PROXIMO_VENCIMENTO",
    "DIAS_RESTANTES",
    "STATUS_GERAL",
    "ULTIMO_AVISO",
    "DATA_ULTIMO_AVISO",
    "RESULTADO_ULTIMO_ENVIO",
    "QTD_ERROS_AUTOMACAO",
    "DETALHE_ULTIMO_ERRO",
]


@dataclass(frozen=True)
class MappedRow:
    row_number: int
    values: dict[str, object]
    automation_id: str


class SheetMapper:
    def __init__(self, values: list[list[object]]):
        if not values:
            raise ValueError("aba principal vazia")
        self.original_headers = [str(value).strip() for value in values[0]]
        self.headers = {
            normalize_header(header): index
            for index, header in enumerate(self.original_headers)
            if header
        }
        self.rows = values[1:]

    def ensure_automation_headers(self) -> list[str]:
        return [
            header for header in AUTOMATION_HEADERS if normalize_header(header) not in self.headers
        ]

    def require(self, *headers: str) -> None:
        missing = [header for header in headers if normalize_header(header) not in self.headers]
        if missing:
            raise ValueError(f"cabeçalhos obrigatórios ausentes: {', '.join(missing)}")

    def mapped_rows(self) -> list[MappedRow]:
        automation_column = self.headers.get("ID_AUTOMACAO")
        result: list[MappedRow] = []
        for offset, row in enumerate(self.rows, start=2):
            mapped = {
                header: row[index] if index < len(row) else None
                for header, index in self.headers.items()
            }
            if not any(str(value or "").strip() for value in mapped.values()):
                continue
            identifier = (
                str(row[automation_column]).strip()
                if automation_column is not None and automation_column < len(row)
                else ""
            )
            result.append(MappedRow(offset, mapped, identifier or str(uuid.uuid4())))
        return result
