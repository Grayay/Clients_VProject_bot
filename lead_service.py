import logging

from brand_router import find_bookers_for_brand
from database import Database
from google_sheets_client import GoogleSheetsClient
from notifications import NotificationService


LOGGER = logging.getLogger(__name__)


class LeadService:
    def __init__(
        self,
        database: Database,
        google_sheets_client: GoogleSheetsClient,
        notification_service: NotificationService,
    ):
        self.database = database
        self.google_sheets_client = google_sheets_client
        self.notification_service = notification_service

    @staticmethod
    def _stored_booker_for_lead(lead: dict) -> list[dict]:
        booker_id = lead.get("assigned_booker_id") or lead.get("responsible_booker_telegram_id")
        if not booker_id:
            return []

        return [
            {
                "booker_telegram_id": int(booker_id),
                "booker_name": lead.get("assigned_booker_name") or lead.get("responsible_booker_name"),
            }
        ]

    def _bookers_for_lead(self, lead: dict) -> list[dict]:
        return find_bookers_for_brand(lead.get("brand_name") or "") or self._stored_booker_for_lead(lead)

    async def poll_once(self) -> None:
        sheet_leads = self.google_sheets_client.fetch_leads()
        inserted_count = 0
        processed_lead_ids: set[int] = set()

        for sheet_lead in sheet_leads:
            lead_id = self.database.insert_form_lead(sheet_lead)
            if lead_id is None:
                continue

            inserted_count += 1
            processed_lead_ids.add(lead_id)
            lead = self.database.get_lead(lead_id)
            if lead is None:
                LOGGER.error("Inserted lead cannot be loaded: lead_id=%s", lead_id)
                continue

            bookers = self._bookers_for_lead(lead)
            await self.notification_service.send_lead_notifications(lead, bookers)

        await self.retry_pending_notifications(exclude_lead_ids=processed_lead_ids)

        if inserted_count:
            LOGGER.info("Processed new Google Sheet leads: %s", inserted_count)

    async def retry_pending_notifications(self, exclude_lead_ids: set[int] | None = None) -> None:
        exclude_lead_ids = exclude_lead_ids or set()
        retry_leads = self.database.list_leads_needing_notification_retry()
        retried_count = 0

        for lead in retry_leads:
            lead_id = int(lead["id"])
            if lead_id in exclude_lead_ids:
                continue

            bookers = self._bookers_for_lead(lead)
            await self.notification_service.send_lead_notifications(lead, bookers)
            retried_count += 1

        if retried_count:
            LOGGER.info("Retried pending lead notifications: %s", retried_count)
