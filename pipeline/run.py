"""
run.py - Run the whole pipeline and refresh the website data.

    python -m pipeline.run                         # default: DIB ledger, French holidays, 42 demo anomalies
    python -m pipeline.run --country DE            # German public holidays
    python -m pipeline.run --inject 0              # no demo anomalies (pure real data)
    python -m pipeline.run --input data/raw/FEC.txt
    python -m pipeline.run --llm-top 40            # memos written by the local LLM for the top 40 alerts

Outputs:
    web/data/dashboard.json        -> the website
    data/output/JE_audit_alerts.xlsx  -> working papers (alerts, memos, metrics)
    data/output/entries_scored.csv -> 100% of entries with features and scores
"""
import argparse
import json
from collections import Counter
from datetime import datetime

import numpy as np
import pandas as pd

from . import calendar_api, config, features, genai, inject, loader, model, prompts


def log(msg):
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=str(config.RAW_FILE))
    ap.add_argument("--country", default=config.HOLIDAY_COUNTRY)
    ap.add_argument("--inject", type=int, default=config.INJECT_N)
    ap.add_argument("--llm-top", type=int, default=config.LLM_TOP_N)
    ap.add_argument("--model", default=config.OLLAMA_MODEL)
    ap.add_argument("--language", default="English")
    a = ap.parse_args()

    log("1/7 Loading ledger")
    lines, fmt = loader.load(a.input)
    card = loader.datacard(lines, fmt)
    years = sorted(lines["posting_date"].dt.year.unique())

    log("2/7 Public holidays (Nager.Date API)")
    hol, hol_src = calendar_api.public_holidays(years, a.country)

    log(f"3/7 Injecting {a.inject} labelled demo anomalies")
    if a.inject:
        lines = inject.inject(lines, hol, a.inject)

    log("4/7 Features (P1 timing, P2 amount)")
    e, perf_mat = features.add_features(features.build_entries(lines), hol)
    benford = features.benford_table(e)

    log("5/7 Scoring 100% of entries (rules + Isolation Forest + XGBoost/SHAP)")
    s, metrics = model.score_all(e)
    fc = model.forecast_revenue(lines)

    log("6/7 Gen AI: nature, memos, engagement summary")
    llm = genai.ollama_available()
    log(f"    local LLM {'available: ' + a.model if llm else 'NOT running -> template memos'}")
    top = s.head(config.TOP_N_EXPORT).copy()
    top["nature"] = [genai.nature(r, use_llm=False) for _, r in top.iterrows()]
    memos = []
    for n, (_, r) in enumerate(top.iterrows()):
        use = llm and n < a.llm_top
        if use:
            log(f"    memo {n + 1}/{a.llm_top} {r['entry_id']}")
        memos.append(genai.memo(r, use, a.model, a.language))
    top["memo"] = memos

    alerts = s[s["alert"] == 1]
    rule_counts = Counter(h for hits in alerts["rule_hits"] for h in hits)
    param_of = {features.FEATURES[f]: features.PARAM[f] for f in features.FEATURES}
    param_counts = Counter(param_of.get(h, "Other") for hits in alerts["rule_hits"] for h in hits)
    inj = s[s["is_anomaly"] == 1]
    facts = dict(
        ledger=f"{fmt}, {card['period']}", n_entries=len(s), n_manual=int(s["is_manual"].sum()),
        cutoff=config.ALERT_CUTOFF, n_alerts=len(alerts), by_param=dict(param_counts), by_rule=dict(rule_counts.most_common()),
        n_injected=int(inj["entry_id"].nunique()), found=int(inj["alert"].sum()),
        forecast_flags=[m["month"] for m in fc.get("months", []) if m["flag"]] or "none",
        top5=[f"{r.entry_id} {r.text} {r.amount:,.0f} EUR score {r.risk_score}" for r in alerts.head(5).itertuples()])
    summary = genai.engagement_summary(facts, llm, a.model)

    log("7/7 Writing website data and Excel")
    # entry lines for the alerts shown on the website
    ids = set(top["entry_id"])
    det = lines[lines["entry_id"].isin(ids)]
    det_map = {k: [{"account": r.account, "name": r.account_name, "debit": round(r.debit, 2),
                    "credit": round(r.credit, 2)} for r in g.itertuples()] for k, g in det.groupby("entry_id")}

    def rec(r):
        return {
            "id": r["entry_id"], "score": float(r["risk_score"]), "alert": int(r["alert"]),
            "rules_score": float(r["rules_score"]), "iforest": round(float(r["iforest_pct"]), 3),
            "xgb": round(float(r["xgb_proba"]), 3), "posting_date": f"{r['posting_date']:%Y-%m-%d}",
            "entered_at": f"{r['entered_at']:%Y-%m-%d %H:%M}", "delay": int(r["entry_delay_days"]),
            "user": r["user"], "text": r["text"], "source": r["source"], "nature": r["nature"],
            "amount": round(float(r["amount"]), 2), "accounts": r["accounts"],
            "main_account": f"{r['main_account']} {r['main_account_name']}",
            "rules": list(r["rule_hits"]), "shap": r["shap_top"], "memo": r["memo"],
            "injected": r["anomaly_type"] or None, "lines": det_map.get(r["entry_id"], []),
        }

    months = s.groupby([s["posting_date"].dt.to_period("M"), "source"]).agg(n=("entry_id", "size"), amt=("amount", "sum"))
    monthly = {}
    for (m, src), v in months.iterrows():
        d = monthly.setdefault(str(m), {"month": str(m), "system": 0, "manual": 0, "amount": 0.0, "alerts": 0})
        d[src] = int(v["n"])
        d["amount"] = round(d["amount"] + float(v["amt"]), 2)
    for m, n in alerts.groupby(alerts["posting_date"].dt.to_period("M")).size().items():
        monthly[str(m)]["alerts"] = int(n)

    wd = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    users = s.groupby("user").agg(entries=("entry_id", "size"), manual=("is_manual", "sum"),
                                  alerts=("alert", "sum"), night=("is_night", "sum"),
                                  amount=("amount", "sum")).reset_index()
    hist = np.histogram(s["risk_score"], bins=20, range=(0, 100))[0].tolist()

    data = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "dataset": {
            "name": "DIB General Ledger Data", "doi": "10.5281/zenodo.22014653",
            "url": "https://zenodo.org/records/22014653", "license": "CC BY 4.0",
            "authors": "Gronewald, Stephan, Rombach, Fettke (Saarland University / DFKI)",
            "datacard": card, "holiday_country": a.country, "holiday_source": hol_src,
            "holidays_in_period": len(hol),
        },
        "settings": {"approval_threshold": config.APPROVAL_THRESHOLD, "alert_cutoff": config.ALERT_CUTOFF,
                     "late_entry_days": config.LATE_ENTRY_DAYS, "night_hours": config.NIGHT_HOURS,
                     "period_end_days": config.PERIOD_END_DAYS, "performance_materiality": perf_mat,
                     "materiality_pct_revenue": config.MATERIALITY_PCT_REVENUE, "llm_model": a.model,
                     "llm_used": llm, "injected": a.inject},
        "kpis": {"entries": len(s), "manual": int(s["is_manual"].sum()), "alerts": len(alerts),
                 "alert_rate": round(len(alerts) / len(s), 5), "injected": facts["n_injected"],
                 "found": facts["found"], "amount_tested": round(float(s["amount"].sum()), 2),
                 "real_alerts": int((alerts["is_anomaly"] == 0).sum())},
        "metrics": metrics,
        "charts": {
            "monthly": list(monthly.values()),
            "weekday": [{"day": d, "n": int((s["posting_date"].dt.day_name() == d).sum())} for d in wd],
            "hours": [{"hour": h, "n": int((s["entered_hour"] == h).sum())} for h in range(24)],
            "score_hist": hist, "by_rule": [{"rule": k, "n": v} for k, v in rule_counts.most_common()],
            "by_param": [{"param": k, "n": v} for k, v in param_counts.most_common()],
            "benford": benford, "users": users.round(2).to_dict("records"),
            "flags_all": {features.FEATURES[f]: int(s[f].sum()) for f in model.RULES},
        },
        "forecast": fc,
        "summary": summary,
        "prompts": {"version": prompts.PROMPT_VERSION, "log": prompts.PROMPT_LOG, "library": prompts.LIBRARY},
        "alerts": [rec(r) for _, r in top.iterrows()],
    }
    config.WEB_DATA.write_text(json.dumps(data, ensure_ascii=False, default=str))
    log(f"    {config.WEB_DATA} ({config.WEB_DATA.stat().st_size / 1e6:.1f} MB)")

    # ---- Excel working papers
    xl = top.copy()
    xl["rules_triggered"] = xl["rule_hits"].map("; ".join)
    xl["shap_drivers"] = xl["shap_top"].map(lambda d: "; ".join(f"{x['feature']} (+{x['shap']})" for x in d))
    for k in ["risk_level", "why_suspicious", "assertion_at_risk", "conclusion"]:
        xl[k] = xl["memo"].map(lambda m: m.get(k, ""))
    xl["follow_up_procedures"] = xl["memo"].map(lambda m: " | ".join(m.get("follow_up_procedures", [])))
    xl["memo_source"] = xl["memo"].map(lambda m: m.get("source", ""))
    xl["auditor_decision"] = ""
    xl["auditor_comment"] = ""
    cols = ["entry_id", "risk_score", "alert", "posting_date", "entered_at", "user", "source", "nature", "text",
            "accounts", "amount", "rules_triggered", "shap_drivers", "risk_level", "why_suspicious",
            "assertion_at_risk", "follow_up_procedures", "conclusion", "memo_source", "anomaly_type",
            "auditor_decision", "auditor_comment"]
    with pd.ExcelWriter(config.OUT_DIR / "JE_audit_alerts.xlsx", engine="openpyxl") as w:
        xl[cols].to_excel(w, "Alerts", index=False)
        pd.DataFrame(metrics["models"]).T.to_excel(w, "Model metrics")
        pd.DataFrame(metrics["by_type"]).to_excel(w, "Recall by anomaly type", index=False)
        pd.DataFrame([card]).T.rename(columns={0: "value"}).to_excel(w, "Datacard")
        pd.DataFrame(fc.get("months", [])).to_excel(w, "Revenue forecast", index=False)
    keep = ["entry_id", "posting_date", "entered_at", "user", "source", "text", "accounts", "amount"] + \
        list(features.FEATURES) + ["rules_score", "iforest_pct", "xgb_proba", "risk_score", "alert", "anomaly_type"]
    s[keep].to_csv(config.OUT_DIR / "entries_scored.csv", index=False)
    log(f"Done: {len(s):,} entries scored, {len(alerts)} alerts, {facts['found']}/{facts['n_injected']} demo anomalies found")


if __name__ == "__main__":
    main()
