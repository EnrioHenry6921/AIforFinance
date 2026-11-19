"""
config.py - All settings in one place. Change values here, not in the code.
Every audit threshold below is OUR ASSUMPTION (say so in the presentation).
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
RAW_FILE = RAW_DIR / "journal_entries_4203.csv"          # original DIB file (with label + marking)
RAW_FALLBACKS = ["journal_entries_4203.csv", "journal_entries_clean.csv"]   # tried in this order, then any CSV
INBOX_DIR = ROOT / "data" / "inbox"                      # drop new exports here for the scheduler (watch.py)
EXTERNAL_DIR = ROOT / "data" / "external"                # teammates' extra features / scores (optional)
OUT_DIR = ROOT / "data" / "output"                       # Excel, CSV, memos, caches (not committed)
WEB_DATA = ROOT / "web" / "data" / "dashboard.json"      # what the website shows
for d in (RAW_DIR, INBOX_DIR, EXTERNAL_DIR, OUT_DIR, WEB_DATA.parent):
    d.mkdir(parents=True, exist_ok=True)

# ---------- Charts of accounts ----------
# The DIB ledger is a German company (SKR03); a French FEC uses the PCG. Everything that
# depends on account numbers reads it from here, so both work.
CHARTS = {
    "SKR03": {
        "country": "DE",
        "revenue_prefixes": ["80", "81", "82", "83", "84", "85", "86", "87", "88"],
        "cash_prefixes": ["1000"],                   # Kasse
        "bank_prefixes": ["1100", "1200"],
        "vat_rate": 0.19,
        "accounts": {"receivable": ("1400", "Trade receivables"), "revenue": ("8400", "Revenue, 19%"),
                     "vat_out": ("1776", "VAT, 19%"), "bank": ("1100", "Bank (Postbank)"),
                     "payable": ("1600", "Trade payables"), "other_liab": ("1700", "Other liabilities"),
                     "consulting": ("4950", "Legal and consulting expenses"),
                     "maintenance": ("4260", "Maintenance of operating premises"),
                     "advertising": ("4600", "Advertising expenses"), "cash": ("1000", "Cash")},
    },
    "PCG": {
        "country": "FR",
        "revenue_prefixes": ["70"],
        "cash_prefixes": ["53"],
        "bank_prefixes": ["512"],
        "vat_rate": 0.20,
        "accounts": {"receivable": ("411000", "Clients"), "revenue": ("706000", "Prestations de services"),
                     "vat_out": ("445710", "TVA collectée"), "bank": ("512000", "Banque"),
                     "payable": ("401000", "Fournisseurs"), "other_liab": ("408100", "Fournisseurs - FNP"),
                     "consulting": ("622600", "Honoraires"), "maintenance": ("615000", "Entretien et réparations"),
                     "advertising": ("623000", "Publicité"), "cash": ("530000", "Caisse")},
    },
}

# ---------- Calendar ----------
# Plan = France first. NB: the DIB ledger is a German company, so "DE" is also defensible.
HOLIDAY_COUNTRY = None    # None = country of the chart of accounts (SKR03 -> DE, PCG -> FR); or force e.g. "FR"
NAGER_URL = "https://date.nager.at/api/v3/PublicHolidays/{year}/{country}"

# ---------- Manual entries ----------
# DIB posting_id prefix: a..i / aa..ai = system batches; p = accruals/deferrals,
# r = reversals/credit notes, x/xa = payroll, z = injected (demo). FEC: journals OD/AN.
MANUAL_PREFIXES = ["p", "r", "x", "xa", "z"]
MANUAL_JOURNALS = ["OD", "AN"]

# ---------- DIB ground-truth markings (the dataset's own labels) ----------
DIB_MARKINGS = {
    1: "High amount", 2: "High cash disbursement", 3: "Delayed entry (10-29 days)",
    4: "Very delayed entry (>29 days)", 5: "Non-working hours", 6: "Weekend posting",
    7: "Shadow bank account", 8: "Cross-linked clearing",
}
# Columns of the original DIB file that are generator flags: never used as model inputs
DIB_LEAKY_COLUMNS = ["label", "marking", "weekend", "nwh", "promptly", "top_n", "high_cash"]

# ---------- P1 Timing ----------
PERIOD_END_DAYS = 5        # days before 31/12 = closing window
LATE_ENTRY_DAYS = 30       # typed in more than 30 days after the posting date
DELAYED_ENTRY_DAYS = 10    # 10-29 days = delayed (DIB marking 3)
NIGHT_HOURS = (20, 6)      # fallback: entered between 20:00 and 06:00
WORK_HOUR_SHARE = 0.01     # working day = hours holding >= 1% of all entries (DIB: 08:00-16:59)

# ---------- P2 Amount ----------
APPROVAL_THRESHOLD = 5_000.0
NEAR_THRESHOLD_BAND = 0.06
MATERIALITY_PCT_REVENUE = 0.01
PERFORMANCE_MAT_PCT = 0.75
ROUND_UNIT = 500
HIGH_CASH_AMOUNT = 1_000.0     # cash payment above this = "high cash disbursement"

# ---------- Context (account and user behaviour) ----------
RARE_COMBO_MAX = 3             # account combination used at most N times in the ledger = rare
NEW_ACCOUNT_DAYS = 30          # account first used less than N days before the entry, and rarely used
USER_HOUR_PCT = (0.02, 0.98)   # entry hour outside the user's usual 2%-98% range
DUPLICATE_DAYS = 7             # same amount + accounts + text by the same user within N days (manual entries)

# ---------- Demo anomalies ----------
INJECT_N = 42                  # used when the data has NO labels of its own (use --inject to force)
HELD_OUT_INJECTED = ["night_entry", "year_end_revenue"]       # never shown to XGBoost
HELD_OUT_MARKINGS = ["M7 Shadow bank account", "M8 Cross-linked clearing"]

# ---------- Scoring ----------
SYSTEM_WEIGHT = 0.25
ALERT_CUTOFF = 50
TOP_N_EXPORT = 400
TEST_SHARE = 0.25              # last 25% of the period = test set (temporal split, like Person 2)
USE_PERSON2 = True             # add Person 2's classifier to the combined score when it applies

# ---------- Local Gen AI (Ollama) ----------
OLLAMA_URL = "http://localhost:11434"
OLLAMA_MODEL = "llama3:latest"
LLM_TOP_N = 40
OLLAMA_TIMEOUT = 180

# ---------- Alerts by email (watch.py) - set these as environment variables, never in code ----------
# JG_SMTP_HOST, JG_SMTP_PORT, JG_SMTP_USER, JG_SMTP_PASSWORD, JG_ALERT_TO

# ---------- Teammates' deliverables ----------
PERSON2_MODEL = ROOT / "models" / "person2_model.json"
PERSON2_METRICS = ROOT / "team" / "person2" / "model_metrics.json"
PERSON3_LIBRARY = ROOT / "team" / "person3" / "genai" / "recommendation_library.csv"
