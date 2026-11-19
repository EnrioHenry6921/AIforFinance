# JournalGuard AI – Testing 100% of journal entries

AI & Finance · Project 2 · Team 9 · live site: https://je-audit.vercel.app

**In plain English:** an auditor normally checks a *sample* of journal entries. JournalGuard checks **all of them**.
Every entry gets a risk score from five layers, the riskiest ones get an audit memo, and the **auditor decides**.

| Layer | What it does | Who |
|---|---|---|
| Data | Reads the DIB general ledger (Zenodo, with its own 850 labelled anomalies), a French FEC or any CSV/Excel export; datacard and checks | Person 1 + 4 |
| Rules | Audit red flags: P1 timing (weekend, holiday, year-end, late entry, off-hours), P2 amount (high cash, round, below threshold, materiality), context (rare account pair, new account, unusual hour for the user, duplicates) | Person 4 |
| Unsupervised | Isolation Forest, LOF, autoencoder (kept only if clearly better) | Person 4 |
| Supervised | XGBoost + SHAP (ours) and **Person 2's HistGradientBoosting model** | Person 2 + 4 |
| Gen AI | Memo per alert grounded in **Person 3's recommendation library**, themes, engagement summary, "ask the alerts"; optional local LLM (Ollama) | Person 3 + 4 |

## Results on the original DIB file (`journal_entries_4203.csv`, 102,429 entries, 850 labelled)

Temporal test (last 25% of the period, never trained on) and **M7 shadow bank / M8 cross-linked clearing never shown to XGBoost** (circularity test):

| | Precision | Recall | F1 | PR-AUC |
|---|---|---|---|---|
| Rules alone | 0% | 0% | – | 0.07 |
| Isolation Forest | 13% | 4% | 0.06 | 0.09 |
| XGBoost (ours) | 74% | 59% | 0.65 | 0.62 |
| **Combined risk score** | **63%** | **62%** | **0.62** | **0.58** |
| Person 2's model, its own temporal test | 37% | 98% | 0.54 | 0.73 |

* On the anomaly types the model was taught, the combined score catches **89%**; it catches ~0% of M7/M8 (never seen) — the ML only finds what it was taught.
* The rules are weak on this dataset because the labels are a *sample*: 7,215 normal entries are also 10–29 days late, 15,000 normal entries were typed on a weekend. Identity matters: all 250 weekend anomalies were entered by one user, so the supervised model sees who entered each entry (PR-AUC 0.25 → 0.62).
* Across the whole ledger 3,094 entries (3%) are alerted, including 832 of the 850 labelled ones. A score prioritises audit work; it is **not** a probability of fraud.

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# put journal_entries_4203.csv (Zenodo 10.5281/zenodo.22014653) in data/raw/, then:
python -m pipeline.run                          # ~2.5 min: scores 100%, writes website data, Excel, memos
python -m http.server 8000 -d web               # open http://localhost:8000

python -m pipeline.run --input my_FEC.txt       # a French FEC (PCG chart, French holidays, no entry time)
python -m pipeline.run --input export.csv --map mapping.json   # any export; mapping = {"entry_id": "JE_no", ...}
python -m pipeline.run --inject 42              # add 42 labelled demo anomalies (automatic if the file has no labels)
python -m pipeline.ask "Which users have the most off-hours alerts?"
python -m pipeline.watch                        # score every file dropped in data/inbox and email the alerts
python -m pipeline.synthetic --entries 20000 --format dib --out data/raw/synthetic.csv   # test data
python -m pytest -q                             # 16 tests incl. the original file (~3 min)
```

Optional local Gen AI: install Ollama, `ollama pull llama3`, then `OLLAMA_ORIGINS="*" ollama serve` so the
website's "Rewrite with local AI" and "Ask" buttons work. Client data never leaves the laptop.
Email for `watch.py` only through environment variables `JG_SMTP_HOST`, `JG_SMTP_PORT`, `JG_SMTP_USER`,
`JG_SMTP_PASSWORD`, `JG_ALERT_TO`; without them the email is saved as `data/output/alert_email.eml`.

## Outputs

| File | Use |
|---|---|
| `web/data/dashboard.json` | the website |
| `data/output/JE_audit_alerts.xlsx` | working papers: top alerts with memo, evidence, procedures, library codes, empty auditor decision columns; metrics; datacard; forecast |
| `data/output/entries_scored.csv` | **100% of entries** with every feature and every layer's score |
| `data/output/memos/audit_memo_<id>.txt` | one memo per alert in Person 3's layout |

## What's inside

```
pipeline/
  config.py         thresholds and settings (our assumptions, documented), charts of accounts SKR03 + PCG
  loader.py         DIB / FEC / generic CSV-Excel reader, separator detection, labels, datacard
  schema.py         input checks (clear errors and warnings)
  textclean.py      cleans posting texts
  calendar_api.py   public holidays (Nager.Date API, fallback holidays library); country follows the chart
  synthetic.py      Faker-style generator in the DIB layout, markings 1-8, FEC export
  inject.py         labelled demo anomalies (chart-aware)
  features.py       P1 timing, P2 amount, context features; working day learned from the data; Benford
  model.py          rules, IF/LOF/autoencoder, XGBoost + SHAP, blend, temporal split, circularity test
  person2_model.py  Person 2's model, exported to JSON and re-implemented (runs on any scikit-learn)
  recommend.py      maps red flags to Person 3's recommendation library
  forecast.py       expected vs actual revenue per month
  prompts.py        prompt library v3 (system + user prompts, change log)
  genai.py          nature, themes, memos, engagement summary, ask; template fallback without LLM
  run.py            runs everything        ask.py   questions in plain language        watch.py   inbox + email
team/person2, team/person3   teammates' deliverables, kept as delivered
models/person2_model.json    Person 2's trained model (tools/export_person2_model.py re-creates it)
tests/                       pytest suite; CI in .github/workflows/ci.yml
web/                         static dashboard (Vercel)
```

See **INTEGRATION.md** for how each teammate's work plugs in.

## Data and limits

Gronewald, Stephan, Rombach, Fettke, *DIB General Ledger Data*, Zenodo, DOI 10.5281/zenodo.22014653, CC BY 4.0.
The ledger and its labels are synthetic; real fraud can look different. Generator helper columns (`weekend`, `nwh`,
`promptly`, `top_n`, `high_cash`, `label`, `marking`) are never model inputs. Thresholds and materiality are our
assumptions. The LLM only receives computed facts and every memo must be reviewed; the auditor decides and signs.
