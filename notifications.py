import json
import logging
import re
from typing import Any

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from config import Config
from database import Database


LOGGER = logging.getLogger(__name__)


SKIPPED_PAYLOAD_HEADERS = {
    "название бренда",
    "бренд",
    "brand",
    "brand name",
    "отметка времени",
    "timestamp",
    "время заполнения",
    "source",
    "sheet_id",
    "sheet_tab",
    "row_number",
    "external_id",
    "raw_payload",
}


class NotificationService:
    def __init__(self, bot: Bot, config: Config, database: Database):
        self.bot = bot
        self.config = config
        self.database = database

    @staticmethod
    def _lead_keyboard(lead_id: int) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Взять в работу",
                        callback_data=f"lead_take:{lead_id}",
                    ),
                ],
            ]
        )

    @staticmethod
    def _clean_value(value: Any) -> str | None:
        value = "" if value is None else str(value).strip()
        return value or None

    @staticmethod
    def _value(value: Any) -> str:
        return NotificationService._clean_value(value) or "не указано"

    @staticmethod
    def _extract_username(value: str | None) -> str | None:
        if not value:
            return None
        match = re.search(r"@[A-Za-z0-9_]{3,32}", value)
        return match.group(0) if match else None

    @staticmethod
    def _clean_booker_name(value: str | None, username: str | None, booker_id: str) -> str | None:
        name = NotificationService._clean_value(value)
        if not name:
            return None

        if username:
            name = name.replace(username, " ")
        name = name.replace(booker_id, " ")
        name = re.sub(r"[\(\)\[\],;/]+", " ", name)
        name = re.sub(r"\s+", " ", name).strip()
        return name or None

    @staticmethod
    def format_booker_label(booker_id: int | str, booker_name: str | None = None) -> str:
        booker_id_text = str(booker_id)
        username = NotificationService._extract_username(booker_name)
        clean_name = NotificationService._clean_booker_name(booker_name, username, booker_id_text)

        if username:
            return username
        if clean_name:
            return clean_name
        return booker_id_text

    @staticmethod
    def _as_booker_list(bookers: dict[str, Any] | list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        if bookers is None:
            return []
        if isinstance(bookers, dict):
            return [bookers]
        return [booker for booker in bookers if booker]

    @staticmethod
    def _booker_label(bookers: dict[str, Any] | list[dict[str, Any]] | None) -> str:
        booker_list = NotificationService._as_booker_list(bookers)
        if not booker_list:
            return "не найден"

        return ", ".join(
            NotificationService.format_booker_label(
                booker["booker_telegram_id"],
                booker.get("booker_name"),
            )
            for booker in booker_list
        )

    @staticmethod
    def _normalize_payload_key(value: str) -> str:
        text = str(value or "").strip().lower().replace("ё", "е")
        text = re.sub(r"\s+", " ", text)
        return text

    @staticmethod
    def _is_skipped_payload_key(key: str) -> bool:
        normalized_key = NotificationService._normalize_payload_key(key)
        normalized_skipped = {
            NotificationService._normalize_payload_key(item)
            for item in SKIPPED_PAYLOAD_HEADERS
        }
        return normalized_key in normalized_skipped or normalized_key.startswith("_")

    @staticmethod
    def _payload_lines(lead: dict[str, Any]) -> list[str]:
        raw_payload = lead.get("raw_payload")
        if not raw_payload:
            return NotificationService._fallback_payload_lines(lead)

        try:
            payload = json.loads(str(raw_payload))
        except (TypeError, ValueError):
            return NotificationService._fallback_payload_lines(lead)

        if not isinstance(payload, dict):
            return NotificationService._fallback_payload_lines(lead)

        lines = []
        for key, value in payload.items():
            clean_value = NotificationService._clean_value(value)
            if not clean_value or NotificationService._is_skipped_payload_key(str(key)):
                continue
            lines.append(f"{key}: {clean_value}")

        return lines or ["Дополнительные данные не указаны."]

    @staticmethod
    def _fallback_payload_lines(lead: dict[str, Any]) -> list[str]:
        lines = []
        for label, key in (
            ("Ваше имя", "client_name"),
            ("Место съемки", "shooting_location"),
            ("Город", "shooting_city"),
            ("Контакт для связи", "contact"),
            ("Дата/период съемки", "shooting_date_period"),
            ("Комментарий / описание задачи", "comment"),
        ):
            value = NotificationService._clean_value(lead.get(key))
            if value:
                lines.append(f"{label}: {value}")
        return lines or ["Дополнительные данные не указаны."]

    @staticmethod
    def _truncate(text: str, limit: int = 3900) -> str:
        if len(text) <= limit:
            return text
        return text[: limit - 3].rstrip() + "..."

    @staticmethod
    def _error_text(error: Exception) -> str:
        text = f"{type(error).__name__}: {error}".strip()
        return (text or type(error).__name__)[:1000]

    def _common_message_text(
        self,
        lead: dict[str, Any],
        bookers: dict[str, Any] | list[dict[str, Any]] | None,
    ) -> str:
        lines = [
            "🆕 Новая заявка от клиента",
            "",
            f"Бренд: {self._value(lead.get('brand_name'))}",
            f"Ответственный букер: {self._booker_label(bookers)}",
            "",
            "Данные заявки:",
            *self._payload_lines(lead),
        ]
        return self._truncate("\n".join(lines))

    def _personal_message_text(self, lead: dict[str, Any]) -> str:
        return self._truncate(
            "\n".join(
                [
                    "🆕 Новая заявка по вашему бренду",
                    "",
                    f"Бренд: {self._value(lead.get('brand_name'))}",
                    "",
                    "Данные заявки:",
                    *self._payload_lines(lead),
                ]
            )
        )

    async def _send_personal_message(
        self,
        lead: dict[str, Any],
        booker_telegram_id: int,
        reply_markup: InlineKeyboardMarkup | None = None,
    ) -> tuple[int | None, str | None]:
        lead_id = int(lead["id"])
        try:
            personal_message = await self.bot.send_message(
                chat_id=booker_telegram_id,
                text=self._personal_message_text(lead),
                reply_markup=reply_markup,
            )
        except Exception as error:
            error_text = self._error_text(error)
            LOGGER.warning(
                "Personal lead notification failed: lead_id=%s booker_id=%s error=%s",
                lead_id,
                booker_telegram_id,
                error_text,
                exc_info=True,
            )
            return None, error_text

        LOGGER.info(
            "Personal lead notification sent: lead_id=%s booker_id=%s message_id=%s",
            lead_id,
            booker_telegram_id,
            personal_message.message_id,
        )
        return personal_message.message_id, None

    async def send_personal_lead(
        self,
        lead: dict[str, Any],
        booker_telegram_id: int,
        reply_markup: InlineKeyboardMarkup | None = None,
    ) -> int | None:
        if reply_markup is None:
            reply_markup = self._lead_keyboard(int(lead["id"]))

        message_id, _ = await self._send_personal_message(
            lead,
            booker_telegram_id,
            reply_markup=reply_markup,
        )
        return message_id

    async def announce_lead_assignment(self, lead: dict[str, Any], booker_label: str) -> None:
        lead_id = int(lead["id"])
        common_message_id = lead.get("common_chat_message_id")
        try:
            await self.bot.send_message(
                chat_id=self.config.leads_notify_chat_id,
                text=f"В работе: {booker_label}",
                reply_to_message_id=int(common_message_id) if common_message_id else None,
                allow_sending_without_reply=True,
            )
        except Exception:
            LOGGER.warning(
                "Failed to announce lead assignment: lead_id=%s booker=%s",
                lead_id,
                booker_label,
                exc_info=True,
            )

    async def send_lead_notifications(
        self,
        lead: dict[str, Any],
        bookers: dict[str, Any] | list[dict[str, Any]] | None,
    ) -> None:
        lead_id = int(lead["id"])
        booker_list = self._as_booker_list(bookers)
        common_message_id = lead.get("common_chat_message_id")
        personal_message_id = lead.get("personal_message_id")
        common_status = str(lead.get("common_notification_status") or "pending")
        personal_status = str(lead.get("personal_notification_status") or "not_needed")
        last_errors = []

        if common_message_id or common_status == "sent":
            common_status = "sent"
        else:
            try:
                common_message = await self.bot.send_message(
                    chat_id=self.config.leads_notify_chat_id,
                    text=self._common_message_text(lead, booker_list),
                    reply_markup=self._lead_keyboard(lead_id),
                )
                common_message_id = common_message.message_id
                common_status = "sent"
            except Exception as error:
                common_status = "failed"
                error_text = self._error_text(error)
                last_errors.append(f"common: {error_text}")
                LOGGER.exception(
                    "Failed to send common lead notification: lead_id=%s error=%s",
                    lead_id,
                    error_text,
                )

        responsible_id = None
        responsible_name = None
        first_personal_message_id = personal_message_id
        personal_failures = 0
        personal_sent = 0

        if booker_list:
            first_booker = booker_list[0]
            responsible_id = int(first_booker["booker_telegram_id"])
            responsible_name = first_booker.get("booker_name")

            for booker in booker_list:
                booker_id = int(booker["booker_telegram_id"])
                existing_delivery = self.database.get_lead_personal_notification(lead_id, booker_id)
                if existing_delivery and (
                    existing_delivery.get("message_id") or existing_delivery.get("status") == "sent"
                ):
                    personal_sent += 1
                    if first_personal_message_id is None and existing_delivery.get("message_id"):
                        first_personal_message_id = existing_delivery.get("message_id")
                    continue

                message_id, personal_error = await self._send_personal_message(
                    lead,
                    booker_id,
                    reply_markup=self._lead_keyboard(lead_id),
                )
                if message_id is None:
                    personal_failures += 1
                    self.database.upsert_lead_personal_notification(
                        lead_id,
                        booker_id,
                        message_id=None,
                        status="failed",
                        last_error=personal_error,
                    )
                    if personal_error:
                        last_errors.append(f"personal {booker_id}: {personal_error}")
                else:
                    personal_sent += 1
                    first_personal_message_id = first_personal_message_id or message_id
                    self.database.upsert_lead_personal_notification(
                        lead_id,
                        booker_id,
                        message_id=message_id,
                        status="sent",
                    )

            personal_status = "pending" if personal_sent and personal_failures else "failed" if personal_failures else "sent"
        else:
            personal_status = "not_needed"

        routing_status = "matched" if booker_list else "not_matched"
        if lead.get("routing_status") == "assigned":
            routing_status = "assigned"

        self.database.update_lead_routing(
            lead_id,
            responsible_booker_telegram_id=responsible_id,
            responsible_booker_name=responsible_name,
            common_chat_message_id=int(common_message_id) if common_message_id else None,
            personal_message_id=int(first_personal_message_id) if first_personal_message_id else None,
            routing_status=routing_status,
            common_notification_status=common_status,
            personal_notification_status=personal_status,
            last_error="; ".join(last_errors) if last_errors else None,
        )
