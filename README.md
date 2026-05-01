# Clients VProject Leads Bot

MVP Telegram bot for client leads from Google Forms / Google Sheets.

## What It Does

- Polls a Google Sheet every `LEADS_POLL_INTERVAL_SECONDS`.
- Inserts only new rows into local SQLite storage.
- Sends every new lead to the common Telegram chat.
- Matches the lead brand against local brand-to-booker rules.
- Sends an additional personal message to the matched booker.
- Does not modify the Google Sheet.

## Setup

1. Install Python 3.12+.

2. Create and activate a virtual environment:

PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

macOS / Linux:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Create `.env` from `.env.example` and fill in values:

PowerShell:

```powershell
Copy-Item .env.example .env
```

macOS / Linux:

```bash
cp .env.example .env
```

Required values:

```env
BOT_TOKEN=
GOOGLE_SHEET_ID=
GOOGLE_SHEET_TAB=Ответы на форму (1)
GOOGLE_SERVICE_ACCOUNT_FILE=google_service_account.json
LEADS_POLL_INTERVAL_SECONDS=30
LEADS_NOTIFY_CHAT_ID=
DATABASE_PATH=leads.db
```

5. Put `google_service_account.json` in this folder.

6. Share the Google Sheet with the service account email from `google_service_account.json` as a viewer.

7. Run the bot:

```bash
python main.py
```

The database and tables are created automatically on startup.

## Brand Routing Commands

Add a first brand rule in Telegram:

```text
/add_brand_rule Lime 123456789 Анна
```

List active rules:

```text
/brand_rules
```

Test routing:

```text
/test_brand_route Lime
```

Submit a test Google Form response and verify:

- one notification appears in `LEADS_NOTIFY_CHAT_ID`;
- if the brand matches an active rule, one personal notification goes to the booker;
- repeated polling does not duplicate the same sheet row.

## Lead Buttons

- `Взять в работу` sets the lead status to `in_progress`.
- `Закрыть` sets the lead status to `closed`.

All state is stored in SQLite at `DATABASE_PATH`.
