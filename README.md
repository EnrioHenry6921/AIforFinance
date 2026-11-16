# JE Audit – Testing 100% of journal entries

AI & Finance · Project 2 · Team 9

**In plain English:** an auditor normally checks a *sample* of journal entries. This project checks **all of them**.
Every entry of a real-format general ledger gets a risk score from three layers: audit red-flag **rules**, an **Isolation Forest** (finds outliers without labels) and **XGBoost** (predicts the probability of an anomaly, explained with **SHAP**).
A **local LLM** (Ollama, so client data never leaves the laptop) writes an audit memo for each alert, and the **auditor decides** in a web dashboard.

The ledger is clean, so we inject **labelled anomalies** to prove the system finds them (recall, precision) and to run a **circularity test**: two anomaly types are never shown to XGBoost.

---

## Quick start

```bash
# 1. Python environment
python3 -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 2. Put the ledger in data/raw/  (journal_entries_clean.csv, or journal_entries_4203.csv from Zenodo)

# 3. Optional: local Gen AI for the memos
#    install Ollama (ollama.com), then:  ollama pull llama3

# 4. Run the pipeline (about 1 minute; longer with the LLM)
python -m pipeline.run                    # French holidays, 42 demo anomalies, LLM memos for the top 40
python -m pipeline.run --country DE       # German holidays (the DIB company is German)
python -m pipeline.run --inject 0         # real data only, no demo anomalies

# 5. Open the dashboard locally
python -m http.server 8000 -d web         # then open http://localhost:8000
```

To use the **"Rewrite with local AI"** buttons on the website, start Ollama so the page may call it:
`OLLAMA_ORIGINS="*" ollama serve`

## What's inside

```
pipeline/
  config.py        all thresholds and settings (our assumptions, documented)
  loader.py        reads the DIB general ledger or a French FEC into one format + datacard
  calendar_api.py  public holidays from the Nager.Date API (fallback: holidays library)
  inject.py        labelled demo anomalies (P1 timing, P2 amount)
  features.py      entry-level features + Benford's law
  model.py         rules + Isolation Forest + XGBoost/SHAP, metrics, circularity test, revenue forecast
  prompts.py       PROMPT LIBRARY (system + user prompts, versioned)
  genai.py         local LLM calls (memos, entry nature, engagement summary) + template fallback
  run.py           runs everything -> web/data/dashboard.json + data/output/JE_audit_alerts.xlsx
web/               static dashboard (HTML/CSS/JS, Chart.js, SheetJS) - deployed on Vercel
  index.html, assets/app.js, assets/style.css, data/dashboard.json
```

## Dashboard pages

| Page | What it shows |
|---|---|
| Dashboard | entries tested, alerts, detection rate, circularity test, monthly trend, entry times, priority alerts |
| Alerts & memos | every top-risk entry; filters, adjustable cut-off; click → entry lines, red flags, SHAP drivers, audit memo, auditor decision; CSV / Excel export |
| Data & EDA | datacard, "do we trust the data?", Benford (overall and per user), weekday, score distribution, red flags |
| Models & prediction | model comparison (precision, recall, F1, PR-AUC), circularity matrix, revenue forecast (expected vs actual), feature importance, scoring recipe |
| Gen AI & prompts | engagement summary, local AI status, the 4 Gen AI roles, prompt library + change log |
| Method | objective, 3 missions, 2 parameters, pipeline steps, limits and governance |

Decisions made on the website are stored **in the browser** (localStorage). Export them to Excel for the working papers.

## Results on the DIB ledger (default run)

- 102,483 entries scored (102,429 real + 54 injected), 697 manual
- 110 alerts (0.11%): all **54/54** demo anomalies found + 56 real entries worth a look (e.g. a December accrual posted on a Sunday and entered in February)
- Circularity: XGBoost catches **0%** of the two held-out types; the rules and the combined score catch **100%**
- Revenue forecast flags December 2024 (the injected year-end revenue)

## Checked against the project plan

| Plan item | Status |
|---|---|
| M1 Detect / M2 Prioritise (predict) / M3 Document | ✅ rules + IForest / XGBoost + SHAP / local LLM memos |
| P1 Timing, P2 Amount (focus on 2 parameters) | ✅ |
| Predictive A (supervised risk) and B (forecast) | ✅ both |
| Circularity control (held-out types, real data review) | ✅ |
| API enrichment (Nager.Date), datacard, consistency checks, EDA, Benford | ✅ |
| Precision, recall, F1, PR-AUC, precision in the top k | ✅ |
| Gen AI: 4 roles, local (sovereignty), LLM explains but never scores, prompt library | ✅ |
| Triage app with decisions, adjustable cut-off, Excel export | ✅ web dashboard (replaces Streamlit: Vercel can't run Streamlit) |
| France focus | ⚠️ NEP 240 framework + French holidays by default, but the DIB company is **German** (SKR03, 19% VAT): `--country DE` available. The loader also reads a French FEC |
| Duplicates (stretch) | ❌ dropped: no supplier or invoice number in the ledger |
| Autoencoder / LOF (optional), APScheduler (optional) | not done |
| Python report notebook → PDF | Persons 2–3 (this repo gives them all the numbers) |

## Data

Gronewald, J., Stephan, S., Rombach, A., Fettke, P. *DIB General Ledger Data*. Zenodo. DOI [10.5281/zenodo.22014653](https://doi.org/10.5281/zenodo.22014653). CC BY 4.0.
The raw CSV is not committed (54 MB): see `data/raw/README.md`.

## Deploy

The website is static: Vercel serves the `web/` folder (`vercel.json`). After re-running the pipeline, commit `web/data/dashboard.json` and push: Vercel redeploys automatically.
