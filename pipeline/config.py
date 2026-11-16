"""
config.py - All settings in one place. Change values here, not in the code.
Every audit threshold below is OUR ASSUMPTION (say so in the presentation).
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_FILE = ROOT / "data" / "raw" / "journal_entries_clean.csv"   # DIB General Ledger Data (Zenodo)
OUT_DIR = ROOT / "data" / "output"                                # Excel, CSV, caches (not committed)
WEB_DATA = ROOT / "web" / "data" / "dashboard.json"               # what the website shows
OUT_DIR.mkdir(parents=True, exist_ok=True)
WEB_DATA.parent.mkdir(parents=True, exist_ok=True)

# ---------- Calendar ----------
# Plan = France first. NB: the DIB ledger is a German company (SKR03 accounts, 19% VAT),
# so "DE" is also defensible. Change it here or with: python -m pipeline.run --country DE
HOLIDAY_COUNTRY = "FR"
NAGER_URL = "https://date.nager.at/api/v3/PublicHolidays/{year}/{country}"

# ---------- Manual entries ----------
# In this ledger the posting_id prefix tells the source:
#   a..i / aa..ai = system batches (purchases, sales, payments)
#   p = accruals/deferrals, r = reversals/credit notes, x/xa = payroll, z = injected (demo)
MANUAL_PREFIXES = ["p", "r", "x", "xa", "z"]

# ---------- P1 Timing ----------
PERIOD_END_DAYS = 5        # days around 31/12 = closing window
LATE_ENTRY_DAYS = 30       # typed in more than 30 days after the posting date
NIGHT_HOURS = (20, 6)      # entered between 20:00 and 06:00

# ---------- P2 Amount ----------
APPROVAL_THRESHOLD = 5_000.0   # entries above this need a second approval (EUR)
NEAR_THRESHOLD_BAND = 0.06     # "just below" = within 6% under the threshold
MATERIALITY_PCT_REVENUE = 0.01 # overall materiality = 1% of yearly revenue (account 8400)
PERFORMANCE_MAT_PCT = 0.75     # performance materiality = 75% of overall
ROUND_UNIT = 500               # "round" = multiple of 500 EUR and at least 1 000 EUR

# ---------- Demo anomalies ----------
INJECT_N = 42                  # labelled anomalous entries added for the demo
HELD_OUT_TYPES = ["night_entry", "year_end_revenue"]  # never shown to XGBoost in training

# ---------- Scoring ----------
SYSTEM_WEIGHT = 0.25           # red flags on system (batch) entries count 25%; manual entries 100%
ALERT_CUTOFF = 50              # risk score >= cut-off = alert
TOP_N_EXPORT = 400             # alerts shipped to the website (all entries are scored)

# ---------- Local Gen AI (Ollama) ----------
OLLAMA_URL = "http://localhost:11434"
OLLAMA_MODEL = "llama3:latest"  # or "qwen3.6" - whatever you pulled with `ollama pull`
LLM_TOP_N = 40                  # memos written by the LLM; the rest use the template
OLLAMA_TIMEOUT = 180
