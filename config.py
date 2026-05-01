import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Config:
    bot_token: str
    google_sheet_id: str
    google_sheet_tab: str
    google_service_account_file: Path
    leads_poll_interval_seconds: int
    leads_notify_chat_id: int
    database_path: Path


def _required(name: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value.strip()


def _parse_int(name: str, default: str | None = None) -> int:
    value = os.getenv(name, default)
    if value is None or not value.strip():
        raise RuntimeError(f"Missing required environment variable: {name}")
    return int(value.strip())


def _resolve_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = BASE_DIR / path
    return path


def load_config() -> Config:
    load_dotenv(BASE_DIR / ".env")

    return Config(
        bot_token=_required("BOT_TOKEN"),
        google_sheet_id=_required("GOOGLE_SHEET_ID"),
        google_sheet_tab=os.getenv("GOOGLE_SHEET_TAB", "Ответы на форму (1)").strip(),
        google_service_account_file=_resolve_path(
            os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "google_service_account.json").strip()
        ),
        leads_poll_interval_seconds=_parse_int("LEADS_POLL_INTERVAL_SECONDS", "30"),
        leads_notify_chat_id=_parse_int("LEADS_NOTIFY_CHAT_ID"),
        database_path=_resolve_path(os.getenv("DATABASE_PATH", "leads.db").strip()),
    )
