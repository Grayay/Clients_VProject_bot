import logging
from typing import Any

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from config import Config
from database import Database


LOGGER = logging.getLogger(__name__)


class NotificationService:
    def __init__(self, bot: Bot, config: Config, database: Database):
        self.bot = bot
        self.config = config
        self.database = database

    @staticmethod
    def _keyboard(lead_id: int) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Взять в работу",
                        callback_data=f"lead_take:{lead_id}",
                    ),
                    InlineKeyboardButton(
                        text="Закрыть",
                        callback_data=f"lead_close:{lead_id}",
                    ),
                ]
            ]
        )

    @staticmethod
    def _value(value: Any) -> str:
        value = "" if value is None else str(value).strip()
        return value or "не указано"

    @staticmethod
    def _booker_label(booker: dict[str, Any] | None) -> str:
        if not booker:
            return "не найден"

        booker_id = str(booker["booker_telegram_id"])
        booker_name = str(booker.get("booker_name") or "").strip()
        if booker_name:
            return f"{booker_name} / {booker_id}"
        return booker_id

    def _common_message_text(self, lead: dict[str, Any], booker: dict[str, Any] | None) -> str:
        return (
            "🆕 Новая заявка от клиента\n\n"
            f"Бренд: {self._value(lead.get('brand_name'))}\n"
            f"Время заполнения: {self._value(lead.get('submitted_at'))}\n\n"
            f"Ответственный букер: {self._booker_label(booker)}\n"
            "Источник: Google Form"
        )

    def _personal_message_text(self, lead: dict[str, Any]) -> str:
        return (
            "🆕 Новая заявка по вашему бренду\n\n"
            f"Бренд: {self._value(lead.get('brand_name'))}\n"
            f"Время заполнения: {self._value(lead.get('submitted_at'))}\n\n"
            "Источник: Google Form"
        )

    async def send_lead_notifications(self, lead: dict[str, Any], booker: dict[str, Any] | None) -> None:
        lead_id = int(lead["id"])
        keyboard = self._keyboard(lead_id)
        common_message_id = None
        personal_message_id = None

        try:
            common_message = await self.bot.send_message(
                chat_id=self.config.leads_notify_chat_id,
                text=self._common_message_text(lead, booker),
                reply_markup=keyboard,
            )
            common_message_id = common_message.message_id
        except Exception:
            LOGGER.exception("Failed to send common lead notification: lead_id=%s", lead_id)

        routing_status = "not_matched"
        responsible_id = None
        responsible_name = None

        if booker:
            responsible_id = int(booker["booker_telegram_id"])
            responsible_name = booker.get("booker_name")
            routing_status = "matched"

            try:
                personal_message = await self.bot.send_message(
                    chat_id=responsible_id,
                    text=self._personal_message_text(lead),
                    reply_markup=keyboard,
                )
                personal_message_id = personal_message.message_id
            except Exception:
                routing_status = "personal_send_failed"
                LOGGER.exception(
                    "Failed to send personal lead notification: lead_id=%s booker_id=%s",
                    lead_id,
                    responsible_id,
                )

        self.database.update_lead_routing(
            lead_id,
            responsible_booker_telegram_id=responsible_id,
            responsible_booker_name=responsible_name,
            common_chat_message_id=common_message_id,
            personal_message_id=personal_message_id,
            routing_status=routing_status,
        )
