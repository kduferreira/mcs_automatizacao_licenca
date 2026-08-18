from __future__ import annotations

import base64
import json

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.configuration.settings import Settings
from app.domain.exceptions.core import ExternalServiceUnavailable
from app.infrastructure.database.models import Company

SCOPE = ["https://www.googleapis.com/auth/spreadsheets"]


class GoogleSheetsGateway:
    def __init__(self, settings: Settings):
        raw = settings.google_service_account_json
        if raw is None and settings.google_service_account_json_base64 is not None:
            raw = base64.b64decode(
                settings.google_service_account_json_base64.get_secret_value()
            ).decode()
        if raw is None:
            raise ExternalServiceUnavailable("credencial Google não configurada")
        info = json.loads(raw.get_secret_value())
        credentials = Credentials.from_service_account_info(info, scopes=SCOPE)
        self.client = build("sheets", "v4", credentials=credentials, cache_discovery=False)
        self.max_retries = settings.google_api_max_retries

    @retry(
        retry=retry_if_exception_type(HttpError),
        wait=wait_exponential(min=1, max=15),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def read_main_sheet(self, company: Company) -> list[list[object]]:
        try:
            response = (
                self.client.spreadsheets()
                .values()
                .get(spreadsheetId=company.spreadsheet_id, range=f"'{company.main_sheet_name}'")
                .execute()
            )
            return response.get("values", [])
        except HttpError as error:
            raise ExternalServiceUnavailable(
                f"falha ao ler planilha da empresa {company.code}"
            ) from error

    def batch_update(self, company: Company, values: list[dict[str, object]]) -> None:
        if not values:
            return
        try:
            self.client.spreadsheets().values().batchUpdate(
                spreadsheetId=company.spreadsheet_id,
                body={"valueInputOption": "USER_ENTERED", "data": values},
            ).execute()
        except HttpError as error:
            raise ExternalServiceUnavailable(
                f"falha ao atualizar planilha da empresa {company.code}"
            ) from error

    def append_rows(self, company: Company, sheet_name: str, rows: list[list[object]]) -> None:
        if not rows:
            return
        self.client.spreadsheets().values().append(
            spreadsheetId=company.spreadsheet_id,
            range=f"'{sheet_name}'!A1",
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body={"values": rows},
        ).execute()

    def ensure_sheet(self, company: Company, sheet_name: str, headers: list[str]) -> None:
        metadata = self.client.spreadsheets().get(spreadsheetId=company.spreadsheet_id).execute()
        existing = {sheet["properties"]["title"] for sheet in metadata.get("sheets", [])}
        if sheet_name not in existing:
            self.client.spreadsheets().batchUpdate(
                spreadsheetId=company.spreadsheet_id,
                body={"requests": [{"addSheet": {"properties": {"title": sheet_name}}}]},
            ).execute()
            self.append_rows(company, sheet_name, [headers])
