import asyncio
import logging

from aiogram import Bot, Dispatcher

from config import load_config
from database import Database
from google_sheets_client import GoogleSheetsClient
from handlers import build_router
from lead_service import LeadService
from notifications import NotificationService


LOGGER = logging.getLogger(__name__)


async def leads_polling_loop(lead_service: LeadService, interval_seconds: int) -> None:
    while True:
        try:
            await lead_service.poll_once()
        except asyncio.CancelledError:
            raise
        except Exception:
            LOGGER.exception("Lead polling iteration failed")

        await asyncio.sleep(interval_seconds)


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

    config = load_config()
    database = Database(config.database_path)
    database.init()

    bot = Bot(token=config.bot_token)
    dispatcher = Dispatcher()
    dispatcher.include_router(build_router(database))

    google_sheets_client = GoogleSheetsClient(config)
    notification_service = NotificationService(bot, config, database)
    lead_service = LeadService(database, google_sheets_client, notification_service)
    polling_task = asyncio.create_task(
        leads_polling_loop(lead_service, config.leads_poll_interval_seconds)
    )

    try:
        LOGGER.info("Bot started")
        await dispatcher.start_polling(bot, allowed_updates=dispatcher.resolve_used_update_types())
    finally:
        polling_task.cancel()
        try:
            await polling_task
        except asyncio.CancelledError:
            pass
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
