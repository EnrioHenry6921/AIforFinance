"""
build_report.py - The brief's "Python report (notebook/PDF) with performance metrics".

    python -m pipeline.run              # first: score the ledger
    python report/build_report.py       # then: writes report/JournalGuard_report.ipynb (+ .html, + .pdf)

The notebook is built from the pipeline's own outputs (web/data/dashboard.json, data/output/entries_scored.csv),
executed, and exported to HTML; the PDF is printed from the HTML with headless Chrome/Chromium if one is installed.
"""
import shutil
import subprocess
import sys
from pathlib import Path

import nbformat as nbf
from nbclient import NotebookClient
from nbconvert import HTMLExporter

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
NB = HERE / "JournalGuard_report.ipynb"

md = nbf.v4.new_markdown_cell
code = nbf.v4.new_code_cell

cells = [
    md("# JournalGuard AI: testing 100% of journal entries\n"
       "AI & Finance · Project 2 · Team 9 (ESSEC). Report generated from the pipeline's outputs.\n\n"
       "**Question.** Among all journal entries of a ledger, which ones are at risk of fraud or material error? "
       "We score **every** entry instead of a sample, and write an audit memo for each alert. "
       "A score prioritises audit work; it is not a probability of fraud, and the auditor decides."),
    code("import json, pandas as pd, numpy as np, matplotlib.pyplot as plt\n"
         "from pathlib import Path\n"
         "ROOT = Path.cwd().parent if Path.cwd().name == 'report' else Path.cwd()\n"
         "D = json.loads((ROOT / 'web/data/dashboard.json').read_text())\n"
         "S = pd.read_csv(ROOT / 'data/output/entries_scored.csv', low_memory=False, parse_dates=['posting_date'])\n"
         "M, K = D['metrics'], D['kpis']\n"
         "plt.rcParams.update({'figure.figsize': (9, 3.6), 'axes.spines.top': False, 'axes.spines.right': False})\n"
         "pd.set_option('display.max_colwidth', 90)\n"
         "print(f\"{K['entries']:,} entries scored · {K['alerts']:,} alerts ({K['alert_rate']:.2%}) · \"\n"
         "      f\"{K['found']:,} of {K['labelled']:,} labelled anomalies alerted\")"),
    md("## 1. Data\nDIB General Ledger Data (Gronewald, Stephan, Rombach, Fettke; Zenodo DOI 10.5281/zenodo.22014653, "
       "CC BY 4.0): a synthetic German company (SKR03 chart); the original file has **850 labelled anomalies** in 8 "
       "scenarios (the datacard below shows the file used for this run). "
       "The generator's helper columns (`weekend`, `nwh`, `promptly`, `top_n`, `high_cash`, `label`, `marking`) are "
       "dropped on load: they would let a model cheat. Enrichment: public holidays (Nager.Date API, `holidays` library "
       "as fallback), the ledger's own working day, user hour profiles, account age, rare account combinations, "
       "materiality from revenue."),
    code("pd.Series(D['dataset']['datacard']).to_frame('value')"),
    md("## 2. Exploratory analysis"),
    code("fig, ax = plt.subplots(1, 3, figsize=(13, 3.4))\n"
         "b = pd.DataFrame(D['charts']['benford']['overall'])\n"
         "ax[0].bar(b['digit'], b['observed'], color='#9fb3c8', label='observed'); ax[0].plot(b['digit'], b['benford'], 'o-', color='#2F7BFF', label='Benford')\n"
         "ax[0].set_title(f\"First digit vs Benford (MAD {D['charts']['benford']['mad']})\"); ax[0].legend()\n"
         "w = pd.DataFrame(D['charts']['weekday']); ax[1].bar(w['day'].str[:3], w['n'], color='#2F7BFF'); ax[1].set_title('Entries by posting weekday')\n"
         "h = pd.DataFrame(D['charts']['hours']); wh = D['settings']['working_hours'] or [0, 23]\n"
         "ax[2].bar(h['hour'], h['n'], color=['#2F7BFF' if (x < wh[0] or x > wh[1]) else '#9fb3c8' for x in h['hour']]); ax[2].set_yscale('log')\n"
         "ax[2].set_title(f'Entry hour (working day {wh[0]:02d}:00-{wh[1]:02d}:59)'); plt.tight_layout()"),
    code("lab = S[S['is_anomaly'] == 1]\n"
         "print('Labelled anomalies by scenario:'); print(lab['anomaly_type'].value_counts().to_string())\n"
         "print(f\"\\nOnly {(lab['source'] == 'manual').mean():.0%} of labelled anomalies are manual entries; the rest are system batches.\")\n"
         "print(f\"Normal entries entered 10-29 days late: {int(((S['is_delayed_entry'] == 1) & (S['is_anomaly'] == 0)).sum()):,} \"\n"
         "      f\"(labelled: {int(((S['is_delayed_entry'] == 1) & (S['is_anomaly'] == 1)).sum())}). Labels are a sample, so a rule alone cannot be precise.\")"),
    md("## 3. Method\n"
       "1. **Rules** (points): P1 timing (weekend, holiday, year-end, revenue at year end, late entry, outside working hours), "
       "P2 amount (round, just below the approval threshold, split, above performance materiality, high cash), context "
       "(rare account pair, new account, unusual hour for the user, duplicates). Timing counts fully only for manual entries.\n"
       "2. **Unsupervised**: Isolation Forest, LOF and an autoencoder (MLP). LOF or the autoencoder replaces Isolation Forest "
       "only with a clear gain (+0.02 PR-AUC); otherwise we keep the simpler model.\n"
       "3. **Supervised**: XGBoost on the features and who entered the entry, decision cut tuned on validation rows, "
       "explained per entry with **SHAP**. Person 2's HistGradientBoosting model is a further layer.\n"
       "4. **Composite risk score** 0-100 (noisy-OR of the layers); alert at 50.\n\n"
       "**Evaluation**: temporal split (the last 25% of the period is never trained on) and a **circularity test**: two "
       "scenarios are never shown to XGBoost."),
    code("print(M['split'])\n"
         "t = pd.DataFrame(M['models']).T[['alerts', 'precision', 'recall', 'f1', 'precision_at_k', 'pr_auc']]\n"
         "p2 = (M.get('person2_reported') or {}).get('xgboost_threshold_0_5')\n"
         "if p2: t.loc[\"Person 2 (own temporal test)\"] = [p2['predicted_anomalies'], p2['precision'], p2['recall'], p2['f1_score'], np.nan, p2['average_precision']]\n"
         "t.astype(float).round(3)"),
    md("## 4. Performance"),
    code("fig, ax = plt.subplots()\n"
         "plot = t.drop(index=[i for i in t.index if 'in-sample' in i])\n"
         "x = np.arange(len(plot)); ax.bar(x - .2, plot['precision'], .4, label='precision', color='#2F7BFF'); ax.bar(x + .2, plot['recall'], .4, label='recall', color='#9fb3c8')\n"
         "ax.set_xticks(x, plot.index, rotation=20, ha='right'); ax.set_ylim(0, 1.05); ax.legend(); ax.set_title('Precision and recall on the unseen test period')\n"
         "print('Recall on the scenarios the model was taught:', M['recall_seen_types'])"),
    code("ct = pd.DataFrame(M['by_type']).set_index('type')\n"
         "ct[[c for c in ['n', 'held_out', 'rules', 'iforest', 'xgboost', 'person2', 'combined'] if c in ct]].round(2)"),
    md("**Reading.** XGBoost catches nearly every scenario it was taught and almost none of the two it never saw "
       "(M7 shadow bank, M8 cross-linked clearing): the circularity risk the brief warns about. That is why the score "
       "never relies on the ML alone, and why a new fraud pattern needs a new rule. Person 2's row marked *in-sample* "
       "was trained on every label of this ledger, so its own temporal test is the fair comparison."),
    code("fi = pd.DataFrame(M['feature_importance']).head(10).iloc[::-1]\n"
         "fig, ax = plt.subplots(figsize=(9, 3.6)); ax.barh(fi['feature'], fi['importance'], color='#2F7BFF'); ax.set_title('What drives XGBoost (gain)');"),
    md("## 5. Predictive analytics: expected vs actual revenue\nSeasonal naive forecast (same month last year × "
       "year-to-date growth on matching months). The band uses only the errors of earlier months, so no month is judged "
       "with information from the future."),
    code("f = pd.DataFrame(D['forecast']['months'])\n"
         "if len(f):\n"
         "    fig, ax = plt.subplots(); ax.fill_between(f['month'], f['low'], f['high'], color='#9fb3c8', alpha=.35, label='band')\n"
         "    ax.plot(f['month'], f['expected'], '--', color='#555', label='expected'); ax.plot(f['month'], f['actual'], 'o-', color='#2F7BFF', label='actual')\n"
         "    ax.scatter(f.loc[f['flag'], 'month'], f.loc[f['flag'], 'actual'], s=90, color='#e5484d', zorder=3, label='outside band')\n"
         "    ax.tick_params(axis='x', rotation=45); ax.legend(); ax.set_title('Monthly revenue')\n"
         "    display(f[f['flag']][['month', 'actual', 'expected', 'band_pct']])"),
    md("## 6. Generative AI\nA local LLM (Ollama, so client data never leaves the laptop) is optional. Without it, "
       "every memo is built from **Person 3's recommendation library**, grounded only in computed facts. Uses: cleaning "
       "and categorising entry descriptions (nature), plain-language explanation of each alert, grouping of alerts by "
       "theme, audit memo per alert, engagement summary, natural-language questions about the alerts."),
    code("print(D['summary']['overview'])\n"
         "print('\\nAlerts by theme:'); print(pd.Series(D['themes']).to_string())"),
    code("a = next(x for x in D['alerts'] if 'memo' in x and x['rules'])\n"
         "m = a['memo']\n"
         "print(f\"Entry {a['id']} · {a['text']} · {a['amount']:,.2f} EUR · score {a['score']}\")\n"
         "print('Red flags:', '; '.join(a['rules']))\n"
         "print('SHAP drivers:', '; '.join(f\"{s['feature']} (+{s['shap']})\" for s in a['shap']))\n"
         "print('\\nWhy suspicious:', m['why_suspicious'])\n"
         "print('Evidence to obtain:'); [print(' -', e) for e in m['evidence_to_obtain']]\n"
         "print('Follow-up procedures:'); [print(' -', e) for e in m['follow_up_procedures']]\n"
         "print('Source:', m['source'])"),
    code("pd.DataFrame(D['prompts']['library'])[['name', 'role']]"),
    md("## 7. Limitations\n"
       "- The ledger and its labels are synthetic; real fraud can look different and real ledgers are confidential.\n"
       "- Labels are a sample of entries matching each pattern, so precision has a ceiling; rules alone are weak here.\n"
       "- Circularity: the supervised model only finds what it was taught (see the held-out scenarios).\n"
       "- Thresholds and materiality are our assumptions (`pipeline/config.py`).\n"
       "- Gen AI can produce plausible but wrong explanations: memos use only computed facts, SHAP shows the real "
       "drivers, and every memo must be reviewed. Human judgment remains mandatory.\n\n"
       "**Outputs**: `data/output/JE_audit_alerts.xlsx` (working papers), `data/output/entries_scored.csv` (100% of "
       "entries), `data/output/memos/`, the website (https://je-audit.vercel.app) and the Streamlit triage app."),
]

nb = nbf.v4.new_notebook(cells=cells, metadata={"kernelspec": {"name": "python3", "display_name": "Python 3", "language": "python"}})


def main():
    if not (ROOT / "data/output/entries_scored.csv").exists():
        sys.exit("Run `python -m pipeline.run` first (data/output/entries_scored.csv is missing).")
    NotebookClient(nb, timeout=600, kernel_name="python3", resources={"metadata": {"path": str(HERE)}}).execute()
    nbf.write(nb, NB)
    html, _ = HTMLExporter(exclude_input=False).from_notebook_node(nb)
    (HERE / "JournalGuard_report.html").write_text(html, encoding="utf-8")
    print("wrote", NB.name, "and JournalGuard_report.html")
    # the PDF is the reader's version: results only, no code (the code is in the notebook and the HTML)
    clean, _ = HTMLExporter(exclude_input=True, exclude_input_prompt=True, exclude_output_prompt=True).from_notebook_node(nb)
    clean = clean.replace("</head>", "<style>@page{size:A4;margin:14mm} pre{white-space:pre-wrap}</style></head>")
    (HERE / ".print.html").write_text(clean, encoding="utf-8")
    chrome = next((c for c in ["google-chrome", "chromium", "chromium-browser", "chrome"] if shutil.which(c)), None)
    if chrome:
        pdf = HERE / "JournalGuard_report.pdf"
        subprocess.run([chrome, "--headless", "--no-sandbox", "--disable-gpu", "--no-pdf-header-footer",
                        f"--print-to-pdf={pdf}", (HERE / ".print.html").as_uri()],
                       check=True, capture_output=True, timeout=180)
        (HERE / ".print.html").unlink()
        print("wrote", pdf.name)
    else:
        print("No Chrome/Chromium found: open the HTML and print it to PDF.")


if __name__ == "__main__":
    main()
