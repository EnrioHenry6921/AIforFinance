# Integration: how the four parts fit into one project

One command runs everything: `python -m pipeline.run`. Each teammate's part plugs in at a fixed point.
If you deliver a new version, drop it in the place below and run `python -m pytest -q`; nothing else changes.

## Person 1 – Data

* **Input:** any file in `data/raw/` or passed with `--input`. Accepted: the DIB layout (`posting_id;…;amount;cd_flag;…`),
  a French FEC (`JournalCode|EcritureNum|…`), or any CSV/Excel with a mapping JSON:
  `{"entry_id": "...", "posting_date": "...", "entered_at": "...", "account": "...", "amount": "..." or "debit"/"credit", "user": "...", "text": "..."}`.
  Separators (`; , | tab`) and date formats are detected.
* **Labels (optional):** a column `label`/`is_anomaly` (0/1) and `marking`/`anomaly_type`. With labels, no demo anomalies are injected.
* **Checks:** `schema.py` stops on unreadable dates or missing amounts and warns on unbalanced entries.
* **Extra features:** put `data/external/features*.csv` with `posting_id` (or `entry_id`) and columns named `feat_*`;
  they are added to the ML models automatically.

## Person 2 – Machine learning

* **Model:** `models/person2_model.json`. Their `journalguard_model.joblib` was saved with scikit-learn 1.4 and cannot be
  loaded by newer versions, so `tools/export_person2_model.py` (run once in a scikit-learn 1.4 environment) exports the
  trees to JSON and `pipeline/person2_model.py` re-implements the prediction (checked: identical to the joblib, max difference 0.0).
  **New model?** Re-run the export script on the new joblib.
* **Or scores only:** `--person2-scores scored_entries.csv` (columns `posting_id` + `xgb_anomaly_score` or `risk_score`, 0–100).
* **Their metrics** are read from `team/person2/model_metrics.json` and shown next to ours.
* The model applies when the ledger has the DIB users and accounts; otherwise it is skipped and the run says why.
  It was trained on all 850 labels, so on the DIB file it is in-sample: the honest combined score is evaluated without it.

## Person 3 – Gen AI

* **Recommendation library:** `team/person3/genai/recommendation_library.csv` (codes 1–8, GEN-1…GEN-5). `recommend.py`
  maps each red flag to a code (`FLAG_TO_CODE`); every memo lists only the evidence and procedures of the codes its flags support.
  **New rows or wording?** Edit the CSV; a new flag needs one line in `FLAG_TO_CODE`.
* **Safeguards** (no fraud claims; separate facts, scores and items to verify; leave the auditor's conclusion blank) are in
  the system prompt (`prompts.py`, v3) and in the template memo used without an LLM.
* **Memo layout:** `genai.memo_text` writes Person 3's layout to `data/output/memos/`.

## Person 4 – Integration and app

`run.py` (orchestration), `features.py`/`model.py` (rules, unsupervised, XGBoost + SHAP, blend, evaluation), `genai.py`,
the website (`web/`), `ask.py`, `watch.py`, tests and deployment.

## Output contract

`data/output/entries_scored.csv` – one row per entry: ids, dates, user, accounts, amount, every feature, `rules_score`,
`iforest_pct`, `lof_pct`, `autoencoder_pct`, `xgb_proba`, `p2_score`, `risk_score` (0–100), `risk_level`, `alert`,
`is_anomaly`, `anomaly_type`. `web/data/dashboard.json` – everything the website shows (valid JSON, no NaN).
