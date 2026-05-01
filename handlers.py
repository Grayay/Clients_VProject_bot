from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import CallbackQuery, Message

from brand_router import find_booker_for_brand
from database import Database


def _user_label(message_or_callback: Message | CallbackQuery) -> str:
    user = message_or_callback.from_user
    if user is None:
        return "unknown"
    if user.username:
        return f"@{user.username}"
    return str(user.id)


def _booker_line(rule: dict) -> str:
    name = str(rule.get("booker_name") or "").strip()
    booker_id = rule["booker_telegram_id"]
    if name:
        return f"{rule['brand_pattern']} → {name} / {booker_id}"
    return f"{rule['brand_pattern']} → {booker_id}"


def build_router(database: Database) -> Router:
    router = Router()

    @router.message(CommandStart())
    async def start(message: Message) -> None:
        await message.answer(
            "Бот заявок из Google Forms.\n\n"
            "Команды:\n"
            "/brand_rules - список активных правил\n"
            "/add_brand_rule <бренд> <telegram_id> <имя опционально>\n"
            "/test_brand_route <бренд>"
        )

    @router.message(Command("brand_rules"))
    async def brand_rules(message: Message) -> None:
        rules = database.list_active_brand_rules()
        if not rules:
            await message.answer("Активных правил маршрутизации брендов пока нет.")
            return

        lines = ["Активные правила маршрутизации:"]
        lines.extend(_booker_line(rule) for rule in rules)
        await message.answer("\n".join(lines))

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

        booker_name = parts[2].strip() if len(parts) > 2 and parts[2].strip() else None
        rule_id = database.add_brand_rule(brand_pattern, booker_telegram_id, booker_name)
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

        await message.answer(f"matched: {_booker_line(booker)}")

    @router.callback_query(F.data.startswith("lead_take:"))
    async def lead_take(callback: CallbackQuery) -> None:
        lead_id = int(callback.data.split(":", 1)[1])
        label = _user_label(callback)
        updated = database.take_lead(lead_id, callback.from_user.id, label)

        if not updated:
            await callback.answer("Заявка не найдена.", show_alert=True)
            return

        await callback.answer("Заявка взята в работу.")
        if callback.message:
            await callback.message.answer(f"Заявка #{lead_id} взята в работу: {label}")

    @router.callback_query(F.data.startswith("lead_close:"))
    async def lead_close(callback: CallbackQuery) -> None:
        lead_id = int(callback.data.split(":", 1)[1])
        label = _user_label(callback)
        updated = database.close_lead(lead_id)

        if not updated:
            await callback.answer("Заявка не найдена.", show_alert=True)
            return

        await callback.answer("Заявка закрыта.")
        if callback.message:
            await callback.message.answer(f"Заявка #{lead_id} закрыта: {label}")

    return router
