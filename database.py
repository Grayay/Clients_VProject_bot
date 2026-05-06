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

    @staticmethod
    def _table_columns(connection: sqlite3.Connection, table_name: str) -> set[str]:
        rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
        return {str(row["name"]) for row in rows}

    def _ensure_columns(
        self,
        connection: sqlite3.Connection,
        table_name: str,
        columns: dict[str, str],
    ) -> None:
        existing_columns = self._table_columns(connection, table_name)
        for column_name, column_sql in columns.items():
            if column_name not in existing_columns:
                connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_sql}")

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
                    client_name TEXT,
                    shooting_location TEXT,
                    shooting_city TEXT,
                    contact TEXT,
                    shooting_date_period TEXT,
                    comment TEXT,
                    raw_payload TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'new',
                    responsible_booker_telegram_id INTEGER NULL,
                    responsible_booker_name TEXT NULL,
                    common_chat_message_id INTEGER NULL,
                    personal_message_id INTEGER NULL,
                    routing_status TEXT NULL,
                    common_notification_status TEXT NOT NULL DEFAULT 'pending',
                    personal_notification_status TEXT NOT NULL DEFAULT 'not_needed',
                    assigned_booker_id INTEGER NULL,
                    assigned_booker_name TEXT NULL,
                    last_error TEXT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(source, sheet_id, sheet_tab, row_number)
                )
            """)
            self._ensure_columns(
                connection,
                "form_leads",
                {
                    "source": "source TEXT NOT NULL DEFAULT 'google_sheets'",
                    "sheet_id": "sheet_id TEXT NOT NULL DEFAULT ''",
                    "sheet_tab": "sheet_tab TEXT NOT NULL DEFAULT ''",
                    "row_number": "row_number INTEGER NOT NULL DEFAULT 0",
                    "external_id": "external_id TEXT NOT NULL DEFAULT ''",
                    "brand_name": "brand_name TEXT",
                    "submitted_at": "submitted_at TEXT",
                    "client_name": "client_name TEXT",
                    "shooting_location": "shooting_location TEXT",
                    "shooting_city": "shooting_city TEXT",
                    "contact": "contact TEXT",
                    "shooting_date_period": "shooting_date_period TEXT",
                    "comment": "comment TEXT",
                    "raw_payload": "raw_payload TEXT NOT NULL DEFAULT '{}'",
                    "status": "status TEXT NOT NULL DEFAULT 'new'",
                    "responsible_booker_telegram_id": "responsible_booker_telegram_id INTEGER NULL",
                    "responsible_booker_name": "responsible_booker_name TEXT NULL",
                    "common_chat_message_id": "common_chat_message_id INTEGER NULL",
                    "personal_message_id": "personal_message_id INTEGER NULL",
                    "routing_status": "routing_status TEXT NULL",
                    "common_notification_status": "common_notification_status TEXT NOT NULL DEFAULT 'pending'",
                    "personal_notification_status": "personal_notification_status TEXT NOT NULL DEFAULT 'not_needed'",
                    "assigned_booker_id": "assigned_booker_id INTEGER NULL",
                    "assigned_booker_name": "assigned_booker_name TEXT NULL",
                    "last_error": "last_error TEXT NULL",
                    "created_at": "created_at TEXT DEFAULT CURRENT_TIMESTAMP",
                    "updated_at": "updated_at TEXT DEFAULT CURRENT_TIMESTAMP",
                },
            )
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
            self._ensure_columns(
                connection,
                "brand_booker_rules",
                {
                    "brand_pattern": "brand_pattern TEXT NOT NULL DEFAULT ''",
                    "booker_telegram_id": "booker_telegram_id INTEGER NOT NULL DEFAULT 0",
                    "booker_name": "booker_name TEXT NULL",
                    "is_active": "is_active INTEGER NOT NULL DEFAULT 1",
                    "created_at": "created_at TEXT DEFAULT CURRENT_TIMESTAMP",
                    "updated_at": "updated_at TEXT DEFAULT CURRENT_TIMESTAMP",
                },
            )
            connection.execute("""
                CREATE TABLE IF NOT EXISTS lead_assignments (
                    lead_id INTEGER NOT NULL UNIQUE,
                    booker_telegram_id INTEGER NOT NULL,
                    booker_username TEXT,
                    booker_name TEXT,
                    assigned_at TEXT NOT NULL
                )
            """)
            connection.execute("""
                CREATE TABLE IF NOT EXISTS lead_personal_notifications (
                    lead_id INTEGER NOT NULL,
                    booker_telegram_id INTEGER NOT NULL,
                    message_id INTEGER NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    last_error TEXT NULL,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (lead_id, booker_telegram_id)
                )
            """)
            self._ensure_columns(
                connection,
                "lead_assignments",
                {
                    "lead_id": "lead_id INTEGER",
                    "booker_telegram_id": "booker_telegram_id INTEGER",
                    "booker_username": "booker_username TEXT",
                    "booker_name": "booker_name TEXT",
                    "assigned_at": "assigned_at TEXT",
                },
            )
            self._ensure_columns(
                connection,
                "lead_personal_notifications",
                {
                    "lead_id": "lead_id INTEGER NOT NULL DEFAULT 0",
                    "booker_telegram_id": "booker_telegram_id INTEGER NOT NULL DEFAULT 0",
                    "message_id": "message_id INTEGER NULL",
                    "status": "status TEXT NOT NULL DEFAULT 'pending'",
                    "last_error": "last_error TEXT NULL",
                    "updated_at": "updated_at TEXT DEFAULT CURRENT_TIMESTAMP",
                },
            )
            connection.execute("""
                CREATE INDEX IF NOT EXISTS idx_brand_booker_rules_active
                ON brand_booker_rules(is_active)
            """)
            connection.execute("""
                CREATE INDEX IF NOT EXISTS idx_form_leads_status
                ON form_leads(status)
            """)
            connection.execute("""
                CREATE INDEX IF NOT EXISTS idx_form_leads_common_notification_status
                ON form_leads(common_notification_status)
            """)
            connection.execute("""
                CREATE INDEX IF NOT EXISTS idx_form_leads_personal_notification_status
                ON form_leads(personal_notification_status)
            """)
            connection.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_lead_assignments_lead_id
                ON lead_assignments(lead_id)
            """)
            connection.execute("""
                CREATE INDEX IF NOT EXISTS idx_lead_personal_notifications_status
                ON lead_personal_notifications(status)
            """)
            connection.execute("""
                UPDATE form_leads
                SET routing_status = 'assigned'
                WHERE (routing_status IS NULL OR routing_status = '')
                  AND EXISTS (
                      SELECT 1
                      FROM lead_assignments
                      WHERE lead_assignments.lead_id = form_leads.id
                  )
            """)
            connection.execute("""
                UPDATE form_leads
                SET routing_status = 'matched'
                WHERE (routing_status IS NULL OR routing_status = '')
                  AND responsible_booker_telegram_id IS NOT NULL
            """)
            connection.execute("""
                UPDATE form_leads
                SET routing_status = 'not_matched'
                WHERE routing_status IS NULL OR routing_status = ''
            """)
            connection.execute("""
                UPDATE form_leads
                SET assigned_booker_id = responsible_booker_telegram_id
                WHERE assigned_booker_id IS NULL
                  AND responsible_booker_telegram_id IS NOT NULL
            """)
            connection.execute("""
                UPDATE form_leads
                SET assigned_booker_name = responsible_booker_name
                WHERE (assigned_booker_name IS NULL OR assigned_booker_name = '')
                  AND responsible_booker_name IS NOT NULL
            """)
            connection.execute("""
                UPDATE form_leads
                SET common_notification_status = 'sent'
                WHERE common_chat_message_id IS NOT NULL
                  AND COALESCE(common_notification_status, '') != 'sent'
            """)
            connection.execute("""
                UPDATE form_leads
                SET common_notification_status = 'pending'
                WHERE common_notification_status IS NULL OR common_notification_status = ''
            """)
            connection.execute("""
                UPDATE form_leads
                SET personal_notification_status = 'sent'
                WHERE personal_message_id IS NOT NULL
                  AND COALESCE(personal_notification_status, '') != 'sent'
            """)
            connection.execute("""
                UPDATE form_leads
                SET personal_notification_status = 'pending'
                WHERE COALESCE(personal_notification_status, 'not_needed') = 'not_needed'
                  AND assigned_booker_id IS NOT NULL
                  AND personal_message_id IS NULL
            """)
            connection.execute("""
                UPDATE form_leads
                SET personal_notification_status = 'not_needed'
                WHERE personal_notification_status IS NULL OR personal_notification_status = ''
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
                    client_name,
                    shooting_location,
                    shooting_city,
                    contact,
                    shooting_date_period,
                    comment,
                    raw_payload
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    lead.get("source", "google_sheets"),
                    lead["sheet_id"],
                    lead["sheet_tab"],
                    lead["row_number"],
                    lead["external_id"],
                    lead.get("brand_name"),
                    lead.get("submitted_at"),
                    lead.get("client_name"),
                    lead.get("shooting_location"),
                    lead.get("shooting_city"),
                    lead.get("contact"),
                    lead.get("shooting_date_period"),
                    lead.get("comment"),
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
        common_notification_status: str | None = None,
        personal_notification_status: str | None = None,
        assigned_booker_id: int | None = None,
        assigned_booker_name: str | None = None,
        last_error: str | None = None,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE form_leads
                SET responsible_booker_telegram_id = ?,
                    responsible_booker_name = ?,
                    common_chat_message_id = COALESCE(?, common_chat_message_id),
                    personal_message_id = COALESCE(?, personal_message_id),
                    routing_status = ?,
                    common_notification_status = COALESCE(?, common_notification_status),
                    personal_notification_status = COALESCE(?, personal_notification_status),
                    assigned_booker_id = COALESCE(?, assigned_booker_id),
                    assigned_booker_name = COALESCE(?, assigned_booker_name),
                    last_error = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    responsible_booker_telegram_id,
                    responsible_booker_name,
                    common_chat_message_id,
                    personal_message_id,
                    routing_status,
                    common_notification_status,
                    personal_notification_status,
                    assigned_booker_id,
                    assigned_booker_name,
                    last_error,
                    lead_id,
                ),
            )

    def list_leads_needing_notification_retry(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM form_leads
                WHERE (
                    common_chat_message_id IS NULL
                    AND COALESCE(common_notification_status, 'pending') IN ('pending', 'failed')
                )
                OR (
                    COALESCE(personal_notification_status, 'not_needed') IN ('pending', 'failed')
                )
                ORDER BY created_at ASC, id ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def assign_lead(
        self,
        lead_id: int,
        booker_telegram_id: int,
        booker_username: str | None,
        booker_name: str | None,
    ) -> tuple[bool, dict[str, Any] | None]:
        with self.connect() as connection:
            lead = connection.execute(
                "SELECT id FROM form_leads WHERE id = ?",
                (lead_id,),
            ).fetchone()
            if lead is None:
                return False, None

            existing_assignment = connection.execute(
                """
                SELECT *
                FROM lead_assignments
                WHERE lead_id = ?
                """,
                (lead_id,),
            ).fetchone()
            if existing_assignment is not None:
                return False, self._to_dict(existing_assignment)

            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO lead_assignments (
                    lead_id,
                    booker_telegram_id,
                    booker_username,
                    booker_name,
                    assigned_at
                )
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (lead_id, booker_telegram_id, booker_username, booker_name),
            )
            assigned = cursor.rowcount == 1

            assignment = connection.execute(
                """
                SELECT *
                FROM lead_assignments
                WHERE lead_id = ?
                """,
                (lead_id,),
            ).fetchone()

            if assigned:
                connection.execute(
                    """
                    UPDATE form_leads
                    SET status = 'in_progress',
                        responsible_booker_telegram_id = ?,
                        responsible_booker_name = ?,
                        assigned_booker_id = ?,
                        assigned_booker_name = ?,
                        routing_status = 'assigned',
                        personal_notification_status = CASE
                            WHEN personal_message_id IS NULL THEN 'pending'
                            ELSE personal_notification_status
                        END,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (booker_telegram_id, booker_name, booker_telegram_id, booker_name, lead_id),
                )

            return assigned, self._to_dict(assignment)

    def get_lead_assignment(self, lead_id: int) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM lead_assignments
                WHERE lead_id = ?
                """,
                (lead_id,),
            ).fetchone()
        return self._to_dict(row)

    def take_lead(self, lead_id: int, user_id: int, user_label: str | None = None) -> bool:
        assigned, _ = self.assign_lead(lead_id, user_id, None, user_label)
        return assigned

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
        return self.ensure_brand_rule(brand_pattern, booker_telegram_id, booker_name)

    def find_brand_rule_for_booker(
        self,
        brand_pattern: str,
        booker_telegram_id: int,
        *,
        only_active: bool = True,
    ) -> dict[str, Any] | None:
        sql = """
            SELECT *
            FROM brand_booker_rules
            WHERE lower(trim(brand_pattern)) = lower(trim(?))
              AND booker_telegram_id = ?
        """
        params: tuple[Any, ...] = (brand_pattern.strip(), booker_telegram_id)
        if only_active:
            sql += " AND is_active = 1"
        sql += " ORDER BY is_active DESC, id ASC LIMIT 1"

        with self.connect() as connection:
            row = connection.execute(sql, params).fetchone()
        return self._to_dict(row)

    def ensure_brand_rule(
        self,
        brand_pattern: str,
        booker_telegram_id: int,
        booker_name: str | None = None,
    ) -> int:
        brand_pattern = brand_pattern.strip()
        existing_active = self.find_brand_rule_for_booker(
            brand_pattern,
            booker_telegram_id,
            only_active=True,
        )
        if existing_active:
            return int(existing_active["id"])

        existing_any = self.find_brand_rule_for_booker(
            brand_pattern,
            booker_telegram_id,
            only_active=False,
        )
        if existing_any:
            self.update_brand_rule(
                int(existing_any["id"]),
                brand_pattern,
                booker_telegram_id,
                booker_name,
            )
            return int(existing_any["id"])

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
                (brand_pattern, booker_telegram_id, booker_name),
            )
            return int(cursor.lastrowid)

    def get_lead_personal_notification(
        self,
        lead_id: int,
        booker_telegram_id: int,
    ) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM lead_personal_notifications
                WHERE lead_id = ?
                  AND booker_telegram_id = ?
                """,
                (lead_id, booker_telegram_id),
            ).fetchone()
        return self._to_dict(row)

    def upsert_lead_personal_notification(
        self,
        lead_id: int,
        booker_telegram_id: int,
        *,
        message_id: int | None,
        status: str,
        last_error: str | None = None,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO lead_personal_notifications (
                    lead_id,
                    booker_telegram_id,
                    message_id,
                    status,
                    last_error,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(lead_id, booker_telegram_id) DO UPDATE SET
                    message_id = COALESCE(excluded.message_id, lead_personal_notifications.message_id),
                    status = excluded.status,
                    last_error = excluded.last_error,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (lead_id, booker_telegram_id, message_id, status, last_error),
            )

    def update_brand_rule(
        self,
        rule_id: int,
        brand_pattern: str,
        booker_telegram_id: int,
        booker_name: str | None = None,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE brand_booker_rules
                SET brand_pattern = ?,
                    booker_telegram_id = ?,
                    booker_name = ?,
                    is_active = 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (brand_pattern.strip(), booker_telegram_id, booker_name, rule_id),
            )

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
