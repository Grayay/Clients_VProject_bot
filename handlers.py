import logging
from datetime import datetime

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)

from brand_router import find_booker_for_brand, find_bookers_in_rules, normalize_brand
from database import Database
from notifications import NotificationService


LOGGER = logging.getLogger(__name__)


RESPONSIBILITY_BUTTON_TEXT = "📋 Посмотреть ответственных"

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


def _start_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=RESPONSIBILITY_BUTTON_TEXT)],
        ],
        resize_keyboard=True,
    )


def _responsible_history_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="За последний месяц",
                    callback_data="responsible_history:month",
                ),
                InlineKeyboardButton(
                    text="За всё время",
                    callback_data="responsible_history:all",
                ),
            ],
        ]
    )


def _take_confirmation_keyboard(lead_id: int, user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Всё равно взять",
                    callback_data=f"lead_take_force:{lead_id}:{user_id}",
                ),
                InlineKeyboardButton(
                    text="Не брать",
                    callback_data=f"lead_take_cancel:{lead_id}:{user_id}",
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
        return "Пока нет ответственных брендов."

    lines = ["📋 Ответственность по брендам", ""]
    lines.extend(_booker_line(rule) for rule in rules)
    return "\n".join(lines)


def _history_booker_label(row: dict) -> str:
    username = str(row.get("booker_username") or "").strip()
    if username:
        return username if username.startswith("@") else f"@{username}"

    name = str(row.get("booker_name") or "").strip()
    if name:
        extracted_username = NotificationService._extract_username(name)
        if extracted_username:
            return extracted_username
        return (
            NotificationService._clean_booker_name(
                name,
                username=None,
                booker_id=str(row.get("booker_telegram_id") or ""),
            )
            or name
        )

    return str(row.get("booker_telegram_id") or "unknown")


def _format_history_date(value: str | None) -> str:
    if not value:
        return "дата не указана"

    text = str(value).strip()
    for candidate in (text, text.replace("Z", "+00:00")):
        try:
            return datetime.fromisoformat(candidate).strftime("%d.%m")
        except ValueError:
            pass

    for pattern in ("%Y-%m-%d %H:%M:%S", "%d.%m.%Y %H:%M:%S", "%d.%m.%Y"):
        try:
            return datetime.strptime(text, pattern).strftime("%d.%m")
        except ValueError:
            pass

    return text[:5] if len(text) >= 5 else text


def _responsible_history_text(database: Database, period: str) -> str:
    is_month = period == "month"
    rows = database.list_responsible_history(days=30 if is_month else None)
    if not rows:
        return (
            "За последний месяц пока нет ответственных по заявкам."
            if is_month
            else "Пока нет ответственных по заявкам."
        )

    grouped: dict[int, dict] = {}
    for row in rows:
        booker_id = int(row["booker_telegram_id"])
        if booker_id not in grouped:
            grouped[booker_id] = {
                "label": _history_booker_label(row),
                "leads": [],
            }
        grouped[booker_id]["leads"].append(row)

    sorted_groups = sorted(
        grouped.values(),
        key=lambda group: (-len(group["leads"]), group["label"].lower()),
    )

    title = "📋 Ответственные за последний месяц" if is_month else "📋 Ответственные за всё время"
    lines = [title, "", f"Всего заявок в работе: {len(rows)}"]

    for group in sorted_groups:
        leads = sorted(
            group["leads"],
            key=lambda row: str(row.get("taken_at") or ""),
            reverse=True,
        )
        lines.extend(["", f"{group['label']} — {len(leads)}"])
        for lead in leads[:20]:
            brand_name = str(lead.get("brand_name") or "").strip() or "бренд не указан"
            lines.append(f"• {_format_history_date(lead.get('taken_at'))} — {brand_name}")
        if len(leads) > 20:
            lines.append(f"...и ещё {len(leads) - 20}")

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


def _parse_lead_user_ids(data: str | None) -> tuple[int, int] | None:
    if not data:
        return None
    parts = data.split(":")
    if len(parts) != 3:
        return None
    try:
        return int(parts[1]), int(parts[2])
    except ValueError:
        return None


def _brand_responsibility_rules(database: Database, brand_name: str | None) -> list[dict]:
    normalized_brand = normalize_brand(brand_name)
    if not normalized_brand:
        return []
    return find_bookers_in_rules(normalized_brand, database.list_active_brand_rules())


def _user_is_responsible_for_brand(rules: list[dict], user_id: int) -> bool:
    return any(int(rule["booker_telegram_id"]) == user_id for rule in rules)


def _responsibility_labels(rules: list[dict]) -> list[str]:
    return [
        NotificationService.format_booker_label(
            rule["booker_telegram_id"],
            rule.get("booker_name"),
        )
        for rule in rules
    ]


def _save_brand_assignment(
    database: Database,
    brand_name: str | None,
    booker_telegram_id: int,
    booker_label: str,
) -> int | None:
    normalized_brand = normalize_brand(brand_name)
    if not normalized_brand:
        return None

    rule_id = database.ensure_brand_rule(normalized_brand, booker_telegram_id, booker_label)

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

    async def assign_lead_to_user(callback: CallbackQuery, lead_id: int) -> tuple[bool, str | None]:
        user = callback.from_user
        username = user.username
        full_name = user.full_name
        label = _booker_display(user.id, username, full_name)

        assigned, assignment = database.assign_lead(lead_id, user.id, username, full_name)

        if assignment is None:
            await callback.answer("Заявка не найдена.", show_alert=True)
            return False, None

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
            return False, None

        LOGGER.info("Lead assigned: lead_id=%s booker_id=%s booker=%s", lead_id, user.id, label)

        lead = database.get_lead(lead_id)
        if lead is not None:
            _save_brand_assignment(database, lead.get("brand_name"), user.id, label)
            database.update_lead_routing(
                lead_id,
                responsible_booker_telegram_id=user.id,
                responsible_booker_name=label,
                common_chat_message_id=lead.get("common_chat_message_id"),
                personal_message_id=lead.get("personal_message_id"),
                routing_status="assigned",
                common_notification_status=lead.get("common_notification_status"),
                personal_notification_status=lead.get("personal_notification_status"),
                assigned_booker_id=user.id,
                assigned_booker_telegram_id=user.id,
                assigned_booker_username=username,
                assigned_booker_name=full_name,
                last_error=None,
            )

        await callback.answer("Заявка взята в работу.")
        await notification_service.announce_lead_assignment(
            lead or {"id": lead_id, "common_chat_message_id": None},
            NotificationService.format_booker_label(user.id, label),
        )
        return True, label

    @router.message(CommandStart())
    async def start(message: Message) -> None:
        await message.answer(
            "Бот заявок клиентов",
            reply_markup=_start_keyboard(),
        )

    @router.message(F.text == RESPONSIBILITY_BUTTON_TEXT)
    async def responsibility_button(message: Message) -> None:
        await message.answer(
            "Какой период показать?",
            reply_markup=_responsible_history_keyboard(),
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

    @router.callback_query(F.data.startswith("responsible_history:"))
    async def responsible_history(callback: CallbackQuery) -> None:
        period = callback.data.split(":", 1)[1] if callback.data else ""
        if period not in {"month", "all"}:
            await callback.answer("Некорректный период.", show_alert=True)
            return

        await _send_callback_message(callback, _responsible_history_text(database, period))

    @router.callback_query(F.data.startswith("take_lead:"))
    @router.callback_query(F.data.startswith("lead_take:"))
    async def lead_take(callback: CallbackQuery) -> None:
        lead_id = _parse_lead_id(callback.data)
        if lead_id is None:
            await callback.answer("Некорректная заявка.", show_alert=True)
            return

        user = callback.from_user
        lead = database.get_lead(lead_id)
        if lead is None:
            await callback.answer("Заявка не найдена.", show_alert=True)
            return

        existing_assignment = database.get_lead_assignment(lead_id)
        if existing_assignment is not None:
            assigned_to = _assignment_label(existing_assignment)
            answer = "Заявка уже взята"
            if assigned_to:
                answer = f"{answer}: {assigned_to}"
            await callback.answer(answer, show_alert=True)
            return

        responsibility_rules = _brand_responsibility_rules(database, lead.get("brand_name"))
        if responsibility_rules and not _user_is_responsible_for_brand(responsibility_rules, user.id):
            labels = "\n".join(_responsibility_labels(responsibility_rules))
            await callback.answer()
            if callback.message:
                await callback.message.answer(
                    "Этот бренд уже закреплён за:\n"
                    f"{labels}\n\n"
                    "Всё равно взять в работу?",
                    reply_markup=_take_confirmation_keyboard(lead_id, user.id),
                )
            return

        await assign_lead_to_user(callback, lead_id)

    @router.callback_query(F.data.startswith("lead_take_force:"))
    async def lead_take_force(callback: CallbackQuery) -> None:
        parsed = _parse_lead_user_ids(callback.data)
        if parsed is None:
            await callback.answer("Некорректная заявка.", show_alert=True)
            return

        lead_id, expected_user_id = parsed
        if callback.from_user.id != expected_user_id:
            await callback.answer("Это подтверждение не для вас.", show_alert=True)
            return

        assigned, label = await assign_lead_to_user(callback, lead_id)
        if assigned and callback.message:
            await callback.message.edit_text(
                f"Заявка взята в работу: {NotificationService.format_booker_label(expected_user_id, label)}"
            )

    @router.callback_query(F.data.startswith("lead_take_cancel:"))
    async def lead_take_cancel(callback: CallbackQuery) -> None:
        parsed = _parse_lead_user_ids(callback.data)
        if parsed is None:
            await callback.answer("Некорректная заявка.", show_alert=True)
            return

        _, expected_user_id = parsed
        if callback.from_user.id != expected_user_id:
            await callback.answer("Это подтверждение не для вас.", show_alert=True)
            return

        await callback.answer("Ок, не берём заявку.")
        if callback.message:
            await callback.message.edit_text("Заявка не взята.")

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
