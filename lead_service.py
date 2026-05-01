import logging

from brand_router import find_booker_for_brand
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

    async def poll_once(self) -> None:
        sheet_leads = self.google_sheets_client.fetch_leads()
        inserted_count = 0

        for sheet_lead in sheet_leads:
            lead_id = self.database.insert_form_lead(sheet_lead)
            if lead_id is None:
                continue

            inserted_count += 1
            lead = self.database.get_lead(lead_id)
            if lead is None:
                LOGGER.error("Inserted lead cannot be loaded: lead_id=%s", lead_id)
                continue

            booker = find_booker_for_brand(lead.get("brand_name") or "")
            await self.notification_service.send_lead_notifications(lead, booker)

        if inserted_count:
            LOGGER.info("Processed new Google Sheet leads: %s", inserted_count)
