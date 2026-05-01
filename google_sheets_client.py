import hashlib
import json
import logging
from typing import Any

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

from config import Config


LOGGER = logging.getLogger(__name__)

TIMESTAMP_HEADERS = {
    "timestamp",
    "отметка времени",
    "время заполнения",
}

BRAND_HEADERS = {
    "название бренда",
    "бренд",
    "brand",
    "brand name",
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
        return str(value or "").strip().lower().replace("ё", "е")

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
        timestamp_index = self._find_column(headers, TIMESTAMP_HEADERS)
        brand_index = self._find_column(headers, BRAND_HEADERS)
        if brand_index is None:
            brand_index = 1 if len(headers) > 1 else 0

        leads = []
        for row_number, row in enumerate(values[1:], start=2):
            if not any(str(cell).strip() for cell in row):
                continue

            payload = self._raw_payload(headers, row)
            raw_payload = json.dumps(payload, ensure_ascii=False, sort_keys=True)
            brand_name = self._cell(row, brand_index)
            submitted_at = self._cell(row, timestamp_index)

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
                    "brand_name": brand_name,
                    "submitted_at": submitted_at,
                    "raw_payload": raw_payload,
                }
            )

        return leads
