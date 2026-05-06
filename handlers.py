import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from brand_router import find_booker_for_brand, find_exact_brand_rule, normalize_brand
from database import Database
from notifications import NotificationService


LOGGER = logging.getLogger(__name__)


ADD_BRAND_RULE_HELP = (
    "Чтобы закрепить бренд за букером, отправьте команду:\n\n"
    "<code>/add_brand_rule &lt;бренд&gt; &lt;telegram_id&gt; &lt;имя&gt;</code>\n\n"
    "Пример:\n"
    "<code>/add_brand_rule Lime 123456789 Анна</code>"
)

TEST_BRAND_ROUTE_HELP = (
    "Чтобы проверить, к кому относится бренд, отправьте:\n\n"
    "<code>/test_brand_route &lt;бренд&gt;</code>\n\n"
    "Пример:\n"
    "<code>/test_brand_route Lime</code>"
)


def _start_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📋 Закрепления брендов",
                    callback_data="show_brand_rules",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="➕ Как добавить бренд",
                    callback_data="show_add_brand_rule_help",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🔍 Как проверить бренд",
                    callback_data="show_test_brand_route_help",
                ),
            ],
        ]
    )


def _user_label(message_or_callback: Message | CallbackQuery) -> str:
    user = message_or_callback.from_user
    if user is None:
        return "unknown"
    if user.username:
        return f"@{user.username}"
    return str(user.id)


def _booker_display(user_id: int, username: str | None, full_name: str | None) -> str:
    if full_name:
        if username:
            return f"{full_name} (@{username})"
        return f"{full_name} ({user_id})"
    if username:
        return f"@{username}"
    return str(user_id)


def _assignment_label(assignment: dict | None) -> str | None:
    if not assignment:
        return None

    booker_id = int(assignment["booker_telegram_id"])
    username = assignment.get("booker_username")
    full_name = assignment.get("booker_name")
    return _booker_display(booker_id, username, full_name)


def _booker_line(rule: dict) -> str:
    return f"• {_brand_rule_display(rule)}"


def _brand_rule_display(rule: dict) -> str:
    booker = NotificationService.format_booker_label(
        rule["booker_telegram_id"],
        rule.get("booker_name"),
    )
    return f"{rule['brand_pattern']} → {booker}"


def _brand_rules_text(database: Database) -> str:
    rules = database.list_active_brand_rules()
    if not rules:
        return "Пока нет активных закреплений брендов."

    lines = ["📋 Закрепления брендов", ""]
    lines.extend(_booker_line(rule) for rule in rules)
    return "\n".join(lines)


async def _send_callback_message(
    callback: CallbackQuery,
    text: str,
    *,
    parse_mode: str | None = None,
) -> None:
    await callback.answer()
    if callback.message:
        await callback.message.answer(text, parse_mode=parse_mode)


def _parse_lead_id(data: str | None) -> int | None:
    if not data or ":" not in data:
        return None
    try:
        return int(data.split(":", 1)[1])
    except ValueError:
        return None


def _save_brand_assignment(
    database: Database,
    brand_name: str | None,
    booker_telegram_id: int,
    booker_label: str,
) -> int | None:
    normalized_brand = normalize_brand(brand_name)
    if not normalized_brand:
        return None

    exact_rule = find_exact_brand_rule(normalized_brand, database.list_active_brand_rules())
    if exact_rule:
        rule_id = int(exact_rule["id"])
        database.update_brand_rule(rule_id, normalized_brand, booker_telegram_id, booker_label)
    else:
        rule_id = database.add_brand_rule(normalized_brand, booker_telegram_id, booker_label)

    LOGGER.info(
        "Brand assigned to booker: brand=%r normalized_brand=%r booker_id=%s rule_id=%s",
        brand_name,
        normalized_brand,
        booker_telegram_id,
        rule_id,
    )
    return rule_id


def build_router(database: Database, notification_service: NotificationService) -> Router:
    router = Router()

    @router.message(CommandStart())
    async def start(message: Message) -> None:
        await message.answer(
            "Бот заявок клиентов\n\n"
            "Что можно сделать:\n"
            "• посмотреть закрепления брендов;\n"
            "• добавить бренд к букеру;\n"
            "• проверить, к кому относится бренд.",
            reply_markup=_start_keyboard(),
        )

    @router.message(Command("brand_rules"))
    async def brand_rules(message: Message) -> None:
        await message.answer(_brand_rules_text(database))

    @router.message(Command("add_brand_rule"))
    async def add_brand_rule(message: Message, command: CommandObject) -> None:
        args = (command.args or "").strip()
        parts = args.split(maxsplit=2)
        if len(parts) < 2:
            await message.answer(
                "Формат: /add_brand_rule <brand_pattern> <booker_telegram_id> <booker_name optional>"
            )
            return

        brand_pattern = parts[0].strip()
        try:
            booker_telegram_id = int(parts[1])
        except ValueError:
            await message.answer("booker_telegram_id должен быть числом.")
            return

        normalized_brand = normalize_brand(brand_pattern)
        if not normalized_brand:
            await message.answer("brand_pattern не должен быть пустым.")
            return

        booker_name = parts[2].strip() if len(parts) > 2 and parts[2].strip() else None
        rule_id = database.add_brand_rule(normalized_brand, booker_telegram_id, booker_name)
        await message.answer(f"Правило добавлено: id={rule_id}")

    @router.message(Command("test_brand_route"))
    async def test_brand_route(message: Message, command: CommandObject) -> None:
        brand_name = (command.args or "").strip()
        if not brand_name:
            await message.answer("Формат: /test_brand_route <brand_name>")
            return

        booker = find_booker_for_brand(brand_name)
        if not booker:
            await message.answer("not matched")
            return

        await message.answer(f"matched: {_brand_rule_display(booker)}")

    @router.callback_query(F.data == "show_brand_rules")
    async def show_brand_rules(callback: CallbackQuery) -> None:
        await _send_callback_message(callback, _brand_rules_text(database))

    @router.callback_query(F.data == "show_add_brand_rule_help")
    async def show_add_brand_rule_help(callback: CallbackQuery) -> None:
        await _send_callback_message(callback, ADD_BRAND_RULE_HELP, parse_mode="HTML")

    @router.callback_query(F.data == "show_test_brand_route_help")
    async def show_test_brand_route_help(callback: CallbackQuery) -> None:
        await _send_callback_message(callback, TEST_BRAND_ROUTE_HELP, parse_mode="HTML")

    @router.callback_query(F.data.startswith("take_lead:"))
    @router.callback_query(F.data.startswith("lead_take:"))
    async def lead_take(callback: CallbackQuery) -> None:
        lead_id = _parse_lead_id(callback.data)
        if lead_id is None:
            await callback.answer("Некорректная заявка.", show_alert=True)
            return

        user = callback.from_user
        username = user.username
        full_name = user.full_name
        label = _booker_display(user.id, username, full_name)

        assigned, assignment = database.assign_lead(lead_id, user.id, username, full_name)

        if assignment is None:
            await callback.answer("Заявка не найдена.", show_alert=True)
            return

        if not assigned:
            assigned_to = _assignment_label(assignment)
            existing_booker_id = int(assignment["booker_telegram_id"])
            answer = (
                "Заявка уже закреплена за вами"
                if existing_booker_id == user.id
                else "Заявка уже закреплена за букером"
            )
            if assigned_to:
                answer = f"{answer}: {assigned_to}"
            await callback.answer(answer, show_alert=True)
            return

        LOGGER.info("Lead assigned: lead_id=%s booker_id=%s booker=%s", lead_id, user.id, label)

        lead = database.get_lead(lead_id)
        if lead is not None:
            _save_brand_assignment(database, lead.get("brand_name"), user.id, label)
            personal_message_id = await notification_service.send_personal_lead(lead, user.id)
            database.update_lead_routing(
                lead_id,
                responsible_booker_telegram_id=user.id,
                responsible_booker_name=label,
                common_chat_message_id=lead.get("common_chat_message_id"),
                personal_message_id=personal_message_id,
                routing_status="assigned",
                common_notification_status=lead.get("common_notification_status"),
                personal_notification_status="sent" if personal_message_id is not None else "failed",
                assigned_booker_id=user.id,
                assigned_booker_name=label,
                last_error=None if personal_message_id is not None else "personal notification failed after assignment",
            )

        await callback.answer("Заявка взята в работу.")
        await notification_service.announce_lead_assignment(
            lead or {"id": lead_id, "common_chat_message_id": None},
            label,
        )

    @router.callback_query(F.data.startswith("lead_close:"))
    async def lead_close(callback: CallbackQuery) -> None:
        lead_id = _parse_lead_id(callback.data)
        if lead_id is None:
            await callback.answer("Некорректная заявка.", show_alert=True)
            return

        label = _user_label(callback)
        updated = database.close_lead(lead_id)

        if not updated:
            await callback.answer("Заявка не найдена.", show_alert=True)
            return

        await callback.answer("Заявка закрыта.")
        if callback.message:
            await callback.message.answer(f"Заявка #{lead_id} закрыта: {label}")

    return router
