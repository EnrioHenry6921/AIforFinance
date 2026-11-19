"""
run.py - JournalGuard AI: run the whole chain and refresh the website, the Excel file and the memos.

    python -m pipeline.run                              # data/raw/journal_entries_4203.csv (DIB, own labels)
    python -m pipeline.run --input my_FEC.txt --country FR
    python -m pipeline.run --input export.csv --map mapping.json
    python -m pipeline.run --inject 42                  # add demo anomalies (default: only if the data has no labels)
    python -m pipeline.run --person2-scores team/person2/scored_entries.csv
    python -m pipeline.run --llm-top 40 --model llama3  # memos rewritten by the local LLM for the top 40

Outputs:
    web/data/dashboard.json            -> the website (and the Streamlit app)
    data/output/JE_audit_alerts.xlsx   -> working papers (alerts, memos, metrics, datacard)
    data/output/entries_scored.csv     -> 100% of entries with features and scores
    data/output/memos/<entry>.txt      -> one memo per alert (Person 3's memo layout)
"""
import argparse
import json
import math
import time
from collections import Counter
from datetime import datetime

import numpy as np
import pandas as pd

from . import (calendar_api, config, features, forecast, genai, inject, loader, model, person2_model, prompts,
               recommend, schema)


def log(msg):
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def clean_json(o):
    """NaN/inf are not valid JSON (the browser would refuse the file): turn them into null."""
    if isinstance(o, float):
        return None if math.isnan(o) or math.isinf(o) else o
    if isinstance(o, dict):
        return {str(k): clean_json(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean_json(v) for v in o]
    if isinstance(o, (np.floating,)):
        return clean_json(float(o))
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, (pd.Timestamp, datetime)):
        return o.isoformat()
    return o


def load_external():
    files = sorted(config.EXTERNAL_DIR.glob("features*.csv"))
    if not files:
        return None
    ext = pd.concat([pd.read_csv(f) for f in files])
    ext = ext.rename(columns={"posting_id": "entry_id"})
    return ext.drop_duplicates("entry_id")


def person2_layer(lines, meta, scores_file=None, use=True):
    """Person 2's scores: their own scored CSV if given, else their model (exported, any sklearn version)."""
    if not use:
        return None, "switched off"
    if scores_file:
        s = pd.read_csv(scores_file)
        idc = "posting_id" if "posting_id" in s else "entry_id"
        sc = "xgb_anomaly_score" if "xgb_anomaly_score" in s else "risk_score"
        return pd.DataFrame({"entry_id": s[idc].astype(str), "p2_score": s[sc].astype(float).round(1)}), f"scores file {scores_file}"
    if not person2_model.available():
        return None, "model file missing"
    p2, applicable = person2_model.score(lines)
    if not applicable:
        return None, "not applicable (trained on the DIB ledger's users and accounts only)"
    return p2, "Person 2's model (exported to models/person2_model.json)"


def main(argv=None):
    ap = argparse.ArgumentParser(description="JournalGuard AI - test 100% of journal entries")
    ap.add_argument("--input", default=None)
    ap.add_argument("--map", default=None, help="JSON mapping of your column names to ours")
    ap.add_argument("--chart", default=None, choices=[None, "SKR03", "PCG"])
    ap.add_argument("--country", default=config.HOLIDAY_COUNTRY)
    ap.add_argument("--inject", type=int, default=None, help="demo anomalies to add (default: 0 if the data has labels, else 42)")
    ap.add_argument("--person2-scores", default=None)
    ap.add_argument("--no-person2", action="store_true")
    ap.add_argument("--llm-top", type=int, default=config.LLM_TOP_N)
    ap.add_argument("--model", default=config.OLLAMA_MODEL)
    ap.add_argument("--language", default="English")
    ap.add_argument("--out", default=str(config.WEB_DATA))
    a = ap.parse_args(argv)
    t0 = time.time()

    log("1/8 Loading and checking the ledger")
    lines, meta = loader.load(a.input, a.map, a.chart)
    lines, warnings = schema.validate(lines, meta)
    card = loader.datacard(lines, meta)
    years = sorted(lines["posting_date"].dt.year.unique())
    log(f"    {card['format']} · {card['entries']:,} entries · chart {meta['chart']} · labels: {card['label_source']}")

    log("2/8 Public holidays (Nager.Date API)")
    a.country = a.country or config.CHARTS[meta["chart"]].get("country", "FR")
    hol, hol_src = calendar_api.public_holidays(years, a.country)
    log(f"    {a.country}: {len(hol)} holidays ({hol_src})")

    n_inject = a.inject if a.inject is not None else (0 if card["labelled_entries"] else config.INJECT_N)
    label_source = meta["label_source"] or ""
    if n_inject:
        log(f"3/8 Injecting {n_inject} labelled demo anomalies")
        lines = inject.inject(lines, hol, n_inject, chart=meta["chart"], has_time=meta["has_entry_time"])
        label_source = "injected" if not label_source else label_source + "+injected"
    else:
        log("3/8 No demo anomalies injected" + (" (the data has its own labels)" if card["labelled_entries"] else ""))

    log("4/8 Features (P1 timing, P2 amount, context)")
    ext = load_external()
    e, perf_mat = features.add_features(features.build_entries(lines), hol, meta["chart"], meta["has_entry_time"], lines, ext)
    benford = features.benford_table(e)

    log("5/8 Person 2's model")
    p2, p2_note = person2_layer(lines, meta, a.person2_scores, not a.no_person2 and config.USE_PERSON2)
    log(f"    {p2_note}")

    log("6/8 Scoring 100% of entries (rules, Isolation Forest, LOF, autoencoder, XGBoost/SHAP)")
    s, metrics = model.score_all(e, p2, "dataset" if label_source.startswith("dataset") else label_source or "none")
    metrics["person2_note"] = p2_note
    if config.PERSON2_METRICS.exists():
        metrics["person2_reported"] = json.loads(config.PERSON2_METRICS.read_text())
    fc = forecast.forecast_revenue(lines, meta["chart"])

    log("7/8 Gen AI: nature, themes, memos, engagement summary")
    llm = genai.ollama_available()
    log(f"    local LLM {'available: ' + a.model if llm else 'NOT running -> memos from Person 3’s library'}")
    top = s.head(config.TOP_N_EXPORT).copy()
    top["nature"] = [genai.nature(r, meta["chart"]) for _, r in top.iterrows()]
    top["theme"] = [genai.theme(r) for _, r in top.iterrows()]
    memos = []
    for n, (_, r) in enumerate(top.iterrows()):
        use = llm and n < a.llm_top
        if use:
            log(f"    memo {n + 1}/{a.llm_top} {r['entry_id']}")
        memos.append(genai.memo(r, use, a.model, a.language))
    top["memo"] = memos
    alerts = top[top["alert"] == 1]
    themes = dict(Counter(genai.theme(r) for _, r in s[s["alert"] == 1].iterrows()).most_common())
    lab = s[s["is_anomaly"] == 1]
    gt = (f"Ground truth ({label_source}): {int(lab['alert'].sum())} of {len(lab)} labelled entries are alerted."
          if len(lab) else "No ground-truth labels in this data.")
    facts = dict(ledger=f"{card['format']}, {card['period']}", n_entries=len(s), n_manual=int(s["is_manual"].sum()),
                 cutoff=config.ALERT_CUTOFF, n_alerts=int(s["alert"].sum()),
                 value_under_review=float(s.loc[s["alert"] == 1, "amount"].sum()), themes=themes, ground_truth=gt,
                 forecast_flags=[m["month"] for m in fc.get("months", []) if m["flag"]] or "none",
                 top5=[f"{r.entry_id} {r.text} {r.amount:,.0f} EUR score {r.risk_score}" for r in alerts.head(5).itertuples()])
    summary = genai.engagement_summary(facts, llm, a.model)

    log("8/8 Writing website data, Excel and memos")
    ids = set(top["entry_id"])
    det = lines[lines["entry_id"].isin(ids)]
    det_map = {k: [{"account": r.account, "name": r.account_name, "debit": round(r.debit, 2), "credit": round(r.credit, 2)}
                   for r in g.itertuples()] for k, g in det.groupby("entry_id")}

    def rec(r):
        return {
            "id": r["entry_id"], "score": float(r["risk_score"]), "alert": int(r["alert"]), "level": r["risk_level"],
            "rules_score": float(r["rules_score"]), "iforest": round(float(r["iforest_pct"]), 3), "lof": round(float(r["lof_pct"]), 3),
            "autoencoder": round(float(r["autoencoder_pct"]), 3), "xgb": round(float(r["xgb_proba"]), 3),
            "p2": None if pd.isna(r["p2_score"]) else float(r["p2_score"]),
            "posting_date": f"{r['posting_date']:%Y-%m-%d}", "entered_at": f"{r['entered_at']:%Y-%m-%d %H:%M}",
            "delay": int(r["entry_delay_days"]), "user": r["user"], "text": r["text"], "source": r["source"],
            "nature": r["nature"], "theme": r["theme"], "amount": round(float(r["amount"]), 2), "accounts": r["accounts"],
            "main_account": f"{r['main_account']} {r['main_account_name']}", "rules": list(r["rule_hits"]),
            "shap": r["shap_top"], "memo": r["memo"], "recommendations": recommend.recommend(r["rule_hits"], r["shap_top"]),
            "injected": (r["anomaly_type"] or "labelled") if r["is_anomaly"] else None, "lines": det_map.get(r["entry_id"], []),
        }

    months = s.groupby([s["posting_date"].dt.to_period("M"), "source"]).agg(n=("entry_id", "size"), amt=("amount", "sum"))
    monthly = {}
    for (mth, src), v in months.iterrows():
        d = monthly.setdefault(str(mth), {"month": str(mth), "system": 0, "manual": 0, "amount": 0.0, "alerts": 0})
        d[src] = int(v["n"])
        d["amount"] = round(d["amount"] + float(v["amt"]), 2)
    for mth, n in s[s["alert"] == 1].groupby(s["posting_date"].dt.to_period("M")).size().items():
        monthly[str(mth)]["alerts"] = int(n)
    wd = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    users = s.groupby("user").agg(entries=("entry_id", "size"), manual=("is_manual", "sum"), alerts=("alert", "sum"),
                                  night=("is_night", "sum"), amount=("amount", "sum")).reset_index()
    rule_counts = Counter(h for hits in s.loc[s["alert"] == 1, "rule_hits"] for h in hits)
    param_counts = Counter(features.PARAM.get({v: k for k, v in features.LABEL.items()}.get(h, ""), "Other")
                           for hits in s.loc[s["alert"] == 1, "rule_hits"] for h in hits)
    gt_types = (lab.groupby("anomaly_type").agg(n=("entry_id", "size"), alerted=("alert", "sum"))
                .reset_index().to_dict("records") if len(lab) else [])

    data = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"), "app": "JournalGuard AI",
        "dataset": {"name": "DIB General Ledger Data" if "DIB" in card["format"] else card["format"],
                    "doi": "10.5281/zenodo.22014653", "url": "https://zenodo.org/records/22014653", "license": "CC BY 4.0",
                    "authors": "Gronewald, Stephan, Rombach, Fettke (Saarland University / DFKI)",
                    "datacard": card, "warnings": warnings, "holiday_country": a.country, "holiday_source": hol_src,
                    "holidays_in_period": len(hol)},
        "settings": {"approval_threshold": config.APPROVAL_THRESHOLD, "alert_cutoff": config.ALERT_CUTOFF,
                     "late_entry_days": config.LATE_ENTRY_DAYS, "night_hours": list(config.NIGHT_HOURS),
                     "working_hours": list(features.working_hours(s["entered_hour"].dropna())) if meta["has_entry_time"] else None,
                     "period_end_days": config.PERIOD_END_DAYS, "performance_materiality": perf_mat,
                     "materiality_pct_revenue": config.MATERIALITY_PCT_REVENUE, "llm_model": a.model, "llm_used": llm,
                     "injected": n_inject, "label_source": label_source or "none", "system_weight": config.SYSTEM_WEIGHT, "chart": meta["chart"],
                     "has_entry_time": meta["has_entry_time"]},
        "kpis": {"entries": len(s), "manual": int(s["is_manual"].sum()), "alerts": int(s["alert"].sum()),
                 "alert_rate": round(float(s["alert"].mean()), 5), "labelled": len(lab), "found": int(lab["alert"].sum()),
                 "injected": int((s["anomaly_type"].isin(list(inject.TYPES))).sum()),
                 "amount_tested": round(float(s["amount"].sum()), 2),
                 "value_under_review": round(float(s.loc[s["alert"] == 1, "amount"].sum()), 2),
                 "real_alerts": int(((s["alert"] == 1) & (s["is_anomaly"] == 0)).sum()),
                 "alerts_loaded": int(top["alert"].sum()), "high": int((s["risk_level"] == "High").sum())},
        "metrics": metrics, "ground_truth_types": gt_types, "themes": themes,
        "flag_params": {features.LABEL[f]: features.PARAM[f] for f in features.FEATURES},
        "charts": {"monthly": list(monthly.values()),
                   "weekday": [{"day": d, "n": int((s["posting_date"].dt.day_name() == d).sum())} for d in wd],
                   "hours": [{"hour": h, "n": int((s["entered_hour"] == h).sum())} for h in range(24)],
                   "score_hist": np.histogram(s["risk_score"], bins=20, range=(0, 100))[0].tolist(),
                   "by_rule": [{"rule": k, "n": v} for k, v in rule_counts.most_common()],
                   "by_param": [{"param": k, "n": v} for k, v in param_counts.most_common()],
                   "benford": benford, "users": users.round(2).to_dict("records"),
                   "flags_all": {features.LABEL[f]: int(s[f].sum()) for f in model.RULES if f in s}},
        "forecast": fc, "summary": summary,
        "prompts": {"version": prompts.PROMPT_VERSION, "log": prompts.PROMPT_LOG, "library": prompts.LIBRARY},
        "recommendation_library": list(recommend.library().values()),
        "alerts": [rec(r) for _, r in top.iterrows()],
    }
    out = config.WEB_DATA if a.out == str(config.WEB_DATA) else __import__("pathlib").Path(a.out)
    out.write_text(json.dumps(clean_json(data), ensure_ascii=False, allow_nan=False))
    log(f"    {out} ({out.stat().st_size / 1e6:.1f} MB)")

    # ---- Excel working papers + one memo file per alert
    memo_dir = config.OUT_DIR / "memos"
    memo_dir.mkdir(exist_ok=True)
    for old in memo_dir.glob("*.txt"):
        old.unlink()
    for _, r in alerts.iterrows():
        (memo_dir / f"audit_memo_{r['entry_id']}.txt").write_text(genai.memo_text(r["memo"], r), encoding="utf-8")
    xl = top.copy()
    xl["red_flags"] = xl["rule_hits"].map("; ".join)
    xl["shap_drivers"] = xl["shap_top"].map(lambda d: "; ".join(f"{x['feature']} (+{x['shap']})" for x in d))
    for k in ["why_suspicious", "assertion_at_risk", "source"]:
        xl["memo_" + k] = xl["memo"].map(lambda m: m.get(k, ""))
    xl["evidence_to_obtain"] = xl["memo"].map(lambda m: " | ".join(m.get("evidence_to_obtain", [])))
    xl["follow_up_procedures"] = xl["memo"].map(lambda m: " | ".join(m.get("follow_up_procedures", [])))
    xl["library_codes"] = xl["memo"].map(lambda m: ", ".join(m.get("library_codes", [])))
    xl["auditor_decision"], xl["auditor_comment"] = "", ""
    cols = ["entry_id", "risk_score", "risk_level", "alert", "posting_date", "entered_at", "user", "source", "nature", "theme",
            "text", "accounts", "amount", "red_flags", "shap_drivers", "p2_score", "memo_why_suspicious", "evidence_to_obtain",
            "follow_up_procedures", "library_codes", "memo_assertion_at_risk", "memo_source", "is_anomaly", "anomaly_type",
            "auditor_decision", "auditor_comment"]
    with pd.ExcelWriter(config.OUT_DIR / "JE_audit_alerts.xlsx", engine="openpyxl") as w:
        xl[cols].to_excel(w, sheet_name="Alerts", index=False)
        if metrics["models"]:
            pd.DataFrame(metrics["models"]).T.to_excel(w, sheet_name="Model metrics")
        if metrics["by_type"]:
            pd.DataFrame(metrics["by_type"]).to_excel(w, sheet_name="Recall by anomaly type", index=False)
        pd.DataFrame([card]).T.rename(columns={0: "value"}).to_excel(w, sheet_name="Datacard")
        pd.DataFrame(fc.get("months", [])).to_excel(w, sheet_name="Revenue forecast", index=False)
    keep = ["entry_id", "posting_date", "entered_at", "user", "source", "text", "accounts", "amount"] + \
        [f for f in features.FEATURES if f in s] + ["rules_score", "iforest_pct", "lof_pct", "autoencoder_pct", "xgb_proba",
                                                    "p2_score", "risk_score", "risk_level", "alert", "is_anomaly", "anomaly_type"]
    s[keep].to_csv(config.OUT_DIR / "entries_scored.csv", index=False)
    log(f"Done in {time.time() - t0:.0f}s: {len(s):,} entries scored, {int(s['alert'].sum())} alerts. {gt}")
    return data


if __name__ == "__main__":
    main()
