import sqlite3
from pathlib import Path
from typing import Any


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def connect(self) -> sqlite3.Connection:
        if self.path.parent and not self.path.parent.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)

        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def init(self) -> None:
        with self.connect() as connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS form_leads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL DEFAULT 'google_sheets',
                    sheet_id TEXT NOT NULL,
                    sheet_tab TEXT NOT NULL,
                    row_number INTEGER NOT NULL,
                    external_id TEXT NOT NULL,
                    brand_name TEXT,
                    submitted_at TEXT,
                    raw_payload TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'new',
                    responsible_booker_telegram_id INTEGER NULL,
                    responsible_booker_name TEXT NULL,
                    common_chat_message_id INTEGER NULL,
                    personal_message_id INTEGER NULL,
                    routing_status TEXT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(source, sheet_id, sheet_tab, row_number)
                )
            """)
            connection.execute("""
                CREATE TABLE IF NOT EXISTS brand_booker_rules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    brand_pattern TEXT NOT NULL,
                    booker_telegram_id INTEGER NOT NULL,
                    booker_name TEXT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            connection.execute("""
                CREATE INDEX IF NOT EXISTS idx_brand_booker_rules_active
                ON brand_booker_rules(is_active)
            """)
            connection.execute("""
                CREATE INDEX IF NOT EXISTS idx_form_leads_status
                ON form_leads(status)
            """)

    @staticmethod
    def _to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        return dict(row)

    def insert_form_lead(self, lead: dict[str, Any]) -> int | None:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO form_leads (
                    source,
                    sheet_id,
                    sheet_tab,
                    row_number,
                    external_id,
                    brand_name,
                    submitted_at,
                    raw_payload
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    lead.get("source", "google_sheets"),
                    lead["sheet_id"],
                    lead["sheet_tab"],
                    lead["row_number"],
                    lead["external_id"],
                    lead.get("brand_name"),
                    lead.get("submitted_at"),
                    lead["raw_payload"],
                ),
            )
            if cursor.rowcount == 0:
                return None
            return int(cursor.lastrowid)

    def get_lead(self, lead_id: int) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM form_leads WHERE id = ?",
                (lead_id,),
            ).fetchone()
        return self._to_dict(row)

    def update_lead_routing(
        self,
        lead_id: int,
        *,
        responsible_booker_telegram_id: int | None,
        responsible_booker_name: str | None,
        common_chat_message_id: int | None,
        personal_message_id: int | None,
        routing_status: str,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE form_leads
                SET responsible_booker_telegram_id = ?,
                    responsible_booker_name = ?,
                    common_chat_message_id = ?,
                    personal_message_id = ?,
                    routing_status = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    responsible_booker_telegram_id,
                    responsible_booker_name,
                    common_chat_message_id,
                    personal_message_id,
                    routing_status,
                    lead_id,
                ),
            )

    def take_lead(self, lead_id: int, user_id: int, user_label: str | None = None) -> bool:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE form_leads
                SET status = 'in_progress',
                    responsible_booker_telegram_id = COALESCE(responsible_booker_telegram_id, ?),
                    responsible_booker_name = COALESCE(responsible_booker_name, ?),
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (user_id, user_label, lead_id),
            )
            return cursor.rowcount > 0

    def close_lead(self, lead_id: int) -> bool:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE form_leads
                SET status = 'closed',
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (lead_id,),
            )
            return cursor.rowcount > 0

    def add_brand_rule(
        self,
        brand_pattern: str,
        booker_telegram_id: int,
        booker_name: str | None = None,
    ) -> int:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO brand_booker_rules (
                    brand_pattern,
                    booker_telegram_id,
                    booker_name
                )
                VALUES (?, ?, ?)
                """,
                (brand_pattern.strip(), booker_telegram_id, booker_name),
            )
            return int(cursor.lastrowid)

    def list_active_brand_rules(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM brand_booker_rules
                WHERE is_active = 1
                ORDER BY brand_pattern COLLATE NOCASE ASC, id ASC
                """
            ).fetchall()
        return [dict(row) for row in rows]
