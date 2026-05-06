import hashlib
import json
import logging
import re
from typing import Any

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

from config import Config


LOGGER = logging.getLogger(__name__)

FIELD_HEADER_ALIASES: dict[str, set[str]] = {
    "submitted_at": {
        "timestamp",
        "отметка времени",
        "время заполнения",
    },
    "client_name": {
        "ваше имя",
        "имя",
        "имя клиента",
        "client name",
        "name",
    },
    "brand_name": {
        "название бренда",
        "бренд",
        "brand",
        "brand name",
    },
    "shooting_location": {
        "место съемки",
        "место съёмки",
        "локация съемки",
        "локация съёмки",
        "location",
    },
    "shooting_city": {
        "город, если выбран другой город",
        "город если выбран другой город",
        "город для съемки",
        "город для съёмки",
        "город",
    },
    "contact": {
        "контакт для связи (телефон или ник в тг)",
        "контакт для связи",
        "телефон или ник в тг",
        "контакт",
        "contact",
    },
    "shooting_date_period": {
        "дата/период съемки",
        "дата/период съёмки",
        "дата съемки",
        "дата съёмки",
        "период съемки",
        "период съёмки",
    },
    "comment": {
        "комментарий / описание задачи",
        "комментарий/описание задачи",
        "комментарий",
        "описание задачи",
        "comment",
    },
}


class GoogleSheetsClient:
    def __init__(self, config: Config):
        self.config = config
        self._service = None

    def _get_service(self):
        if self._service is None:
            credentials = Credentials.from_service_account_file(
                self.config.google_service_account_file,
                scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
            )
            self._service = build("sheets", "v4", credentials=credentials, cache_discovery=False)
        return self._service

    @staticmethod
    def _normalize_header(value: str) -> str:
        text = str(value or "").strip().lower().replace("ё", "е")
        text = re.sub(r"\s+", " ", text)
        text = re.sub(r"\s*/\s*", "/", text)
        return text

    @staticmethod
    def _sheet_range(sheet_tab: str) -> str:
        escaped = sheet_tab.replace("'", "''")
        return f"'{escaped}'"

    @staticmethod
    def _find_column(headers: list[str], candidates: set[str]) -> int | None:
        normalized_candidates = {GoogleSheetsClient._normalize_header(item) for item in candidates}
        for index, header in enumerate(headers):
            if GoogleSheetsClient._normalize_header(header) in normalized_candidates:
                return index
        return None

    @staticmethod
    def _find_columns(headers: list[str]) -> dict[str, int | None]:
        return {
            field_name: GoogleSheetsClient._find_column(headers, aliases)
            for field_name, aliases in FIELD_HEADER_ALIASES.items()
        }

    @staticmethod
    def _cell(row: list[Any], index: int | None) -> str | None:
        if index is None or index >= len(row):
            return None
        value = row[index]
        if value is None:
            return None
        value = str(value).strip()
        return value or None

    @staticmethod
    def _raw_payload(headers: list[str], row: list[Any]) -> dict[str, str]:
        payload = {}
        width = max(len(headers), len(row))
        for index in range(width):
            header = headers[index].strip() if index < len(headers) and headers[index].strip() else ""
            key = header or f"Column {index + 1}"
            value = row[index] if index < len(row) else ""
            payload[key] = "" if value is None else str(value)
        return payload

    @staticmethod
    def _external_id(sheet_id: str, sheet_tab: str, row_number: int, raw_payload: str) -> str:
        source = f"{sheet_id}:{sheet_tab}:{row_number}:{raw_payload}"
        return hashlib.sha256(source.encode("utf-8")).hexdigest()

    def fetch_leads(self) -> list[dict[str, Any]]:
        service = self._get_service()
        result = (
            service.spreadsheets()
            .values()
            .get(
                spreadsheetId=self.config.google_sheet_id,
                range=self._sheet_range(self.config.google_sheet_tab),
            )
            .execute()
        )
        values = result.get("values", [])
        if not values:
            LOGGER.info("Google Sheet is empty")
            return []

        headers = [str(item) for item in values[0]]
        field_indexes = self._find_columns(headers)

        leads = []
        for row_number, row in enumerate(values[1:], start=2):
            if not any(str(cell).strip() for cell in row):
                continue

            payload = self._raw_payload(headers, row)
            raw_payload = json.dumps(payload, ensure_ascii=False, sort_keys=True)
            field_values = {
                field_name: self._cell(row, index)
                for field_name, index in field_indexes.items()
            }

            leads.append(
                {
                    "source": "google_sheets",
                    "sheet_id": self.config.google_sheet_id,
                    "sheet_tab": self.config.google_sheet_tab,
                    "row_number": row_number,
                    "external_id": self._external_id(
                        self.config.google_sheet_id,
                        self.config.google_sheet_tab,
                        row_number,
                        raw_payload,
                    ),
                    "brand_name": field_values.get("brand_name"),
                    "submitted_at": field_values.get("submitted_at"),
                    "client_name": field_values.get("client_name"),
                    "shooting_location": field_values.get("shooting_location"),
                    "shooting_city": field_values.get("shooting_city"),
                    "contact": field_values.get("contact"),
                    "shooting_date_period": field_values.get("shooting_date_period"),
                    "comment": field_values.get("comment"),
                    "raw_payload": raw_payload,
                }
            )

        return leads
