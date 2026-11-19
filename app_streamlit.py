"""
app_streamlit.py - JournalGuard AI triage app (the brief's "Streamlit triage app").

    streamlit run app_streamlit.py

Reads what `python -m pipeline.run` wrote (web/data/dashboard.json + web/data/memos/), so it shows exactly
the same scores, SHAP drivers and memos as the website. Auditor decisions are saved to
data/output/decisions.csv (shared by everyone using this copy of the project) and go into the Excel export.
"""
import io
import json
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "web" / "data" / "dashboard.json"
MEMOS = ROOT / "web" / "data" / "memos"
DECISIONS = ROOT / "data" / "output" / "decisions.csv"
STATUSES = ["open", "retained", "to investigate", "dismissed"]

st.set_page_config(page_title="JournalGuard AI · triage", page_icon="✅", layout="wide")


@st.cache_data
def load(mtime):
    d = json.loads(DATA.read_text(encoding="utf-8"))
    rows = pd.DataFrame(d["alerts"])
    return d, rows


@st.cache_data
def lazy_memos(mtime):
    if not (MEMOS / "index.json").exists():
        return {}
    out = {}
    for f in sorted(MEMOS.glob("memos_*.json")):
        out.update(json.loads(f.read_text(encoding="utf-8")))
    return out


def decisions():
    if DECISIONS.exists():
        return pd.read_csv(DECISIONS, dtype=str).fillna("").set_index("entry_id")
    return pd.DataFrame(columns=["decision", "comment", "saved_at"]).rename_axis("entry_id")


def save_decision(entry_id, decision, comment):
    dec = decisions()
    if decision == "open":
        dec = dec.drop(index=entry_id, errors="ignore")
    else:
        dec.loc[entry_id] = [decision, comment, datetime.now().strftime("%Y-%m-%d %H:%M")]
    DECISIONS.parent.mkdir(parents=True, exist_ok=True)
    dec.reset_index().to_csv(DECISIONS, index=False)


if not DATA.exists():
    st.error("No results yet. Run `python -m pipeline.run` first, then reload this page.")
    st.stop()

D, R = load(DATA.stat().st_mtime)
LAZY = lazy_memos(DATA.stat().st_mtime)
PARAM = D.get("flag_params", {})
LIB = {str(r["marking_code"]): r for r in D.get("recommendation_library", [])}


def memo_of(row):
    m = row.get("memo")
    return m if isinstance(m, dict) else LAZY.get(row["id"])


def recs_of(row):
    if isinstance(row.get("recommendations"), list):
        return row["recommendations"]
    out, seen = [], set()
    for f in list(row["rules"]) + [x["feature"] for x in row["shap"]]:
        c = D.get("flag_codes", {}).get(f)
        if c and c not in seen and c in LIB:
            seen.add(c)
            out.append({"code": c, "signal": f, **LIB[c]})
    return out or [{**D.get("generic_recommendation", {}), "signal": "model score"}]


# ------------------------------------------------------------------ sidebar: thresholds and filters
k, s = D["kpis"], D["settings"]
lo = int(D.get("web_rows", {}).get("min_score", 0))
st.sidebar.title("JournalGuard AI")
st.sidebar.caption(f"{D['dataset']['datacard']['format']} · {D['dataset']['datacard']['period']}")
cutoff = st.sidebar.slider("Alert cut-off", lo, 99, int(s["alert_cutoff"]),
                           help="Entries at or above this risk score are alerts. The pipeline used "
                                f"{s['alert_cutoff']}.")
min_score = st.sidebar.slider("Min score shown", lo, 100, lo)
param = st.sidebar.selectbox("Parameter", ["All", "P1 Timing", "P2 Amount", "Context"])
source = st.sidebar.selectbox("Source", ["All", "manual", "system"])
status = st.sidebar.selectbox("Status", ["All"] + STATUSES)
query = st.sidebar.text_input("Search (id, user, text, red flag)")

dec = decisions()
R["status"] = R["id"].map(dec["decision"]).fillna("open") if len(dec) else "open"
f = R[R["score"] >= min_score]
if param != "All":
    f = f[f["rules"].map(lambda rs: any(PARAM.get(r, "Context") == param for r in rs))]
if source != "All":
    f = f[f["source"] == source]
if status != "All":
    f = f[f["status"] == status]
if query:
    q = query.lower()
    hay = f["id"] + " " + f["user"] + " " + f["text"] + " " + f["accounts"] + " " + f["rules"].map(" ".join) + " " + f["nature"]
    f = f[hay.str.lower().str.contains(q, regex=False)]
alerts = R[R["score"] >= cutoff]

# ------------------------------------------------------------------ header
st.title("Journal entry triage")
c = st.columns(4)
for col, (label, value, note) in zip(c, [
        ("Entries tested", f"{k['entries']:,}", "100% of the ledger"),
        ("Alerts at this cut-off", f"{len(alerts):,}", f"{len(alerts) / k['entries']:.2%} of entries"),
        ("Reviewed", f"{(R['status'] != 'open').sum():,}", f"of {len(R):,} entries shown here"),
        ("Labelled anomalies alerted", f"{k['found']:,} / {k['labelled']:,}" if k["labelled"] else "n/a",
         f"at the pipeline's cut-off {s['alert_cutoff']}")]):
    col.metric(label, value)
    col.caption(note)

tab_tri, tab_mod, tab_sum, tab_data = st.tabs(["Triage", "Models", "Engagement summary", "Data"])

# ------------------------------------------------------------------ triage
with tab_tri:
    st.caption(f"{len(f):,} entries match · {int((f['score'] >= cutoff).sum()):,} at or above the cut-off. "
               "Scores prioritise audit work; they are not a probability of fraud.")
    view = f.assign(red_flags=f["rules"].map("; ".join), alert=f["score"] >= cutoff)[
        ["id", "score", "alert", "posting_date", "user", "source", "amount", "red_flags", "status", "text"]]
    st.dataframe(view, hide_index=True, width="stretch", height=330,
                 column_config={"score": st.column_config.ProgressColumn("Risk", min_value=0, max_value=100, format="%.0f"),
                                "amount": st.column_config.NumberColumn("Amount (EUR)", format="%.2f")})

    if st.button("Prepare Excel export of these entries"):
        xl = io.BytesIO()
        exp = view.copy()
        memos = [memo_of(r) or {} for r in f.to_dict("records")]
        exp["why_suspicious"] = [m.get("why_suspicious", "") for m in memos]
        exp["evidence_to_obtain"] = [" | ".join(m.get("evidence_to_obtain", [])) for m in memos]
        exp["follow_up_procedures"] = [" | ".join(m.get("follow_up_procedures", [])) for m in memos]
        exp["auditor_comment"] = exp["id"].map(dec["comment"]) if len(dec) else ""
        with pd.ExcelWriter(xl, engine="openpyxl") as w:
            exp.to_excel(w, sheet_name="Alerts", index=False)
        st.download_button(f"Download Excel ({len(exp):,} rows)", xl.getvalue(),
                           f"JournalGuard_triage_{datetime.now():%Y-%m-%d}.xlsx",
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    if len(f):
        pick = st.selectbox("Open an entry", f["id"].tolist(),
                            format_func=lambda i: f"{i} · score {R.loc[R['id'] == i, 'score'].iloc[0]:.0f} · "
                                                  f"{R.loc[R['id'] == i, 'text'].iloc[0]}")
        row = R[R["id"] == pick].iloc[0].to_dict()
        left, right = st.columns([1, 1])
        with left:
            st.subheader(row["text"])
            st.write(f"**{row['id']}** · {row['source']} entry · {row['nature']} · posted {row['posting_date']} · "
                     f"entered {row['entered_at']} ({row['delay']} days later) · user **{row['user']}** · "
                     f"**{row['amount']:,.2f} EUR**")
            if isinstance(row.get("injected"), str) and row["injected"]:
                st.info(f"Labelled anomaly in the data: {row['injected']}")
            st.write("**Entry lines**")
            st.dataframe(pd.DataFrame(row["lines"]), hide_index=True, width="stretch")
            st.write("**Red flags (rules):** " + (", ".join(row["rules"]) or "none, flagged by the models"))
            if row["shap"]:
                st.write("**Why the model flagged it (SHAP)**")
                st.bar_chart(pd.DataFrame(row["shap"]).set_index("feature")["shap"], horizontal=True, height=180)
        with right:
            m = memo_of(row)
            st.subheader("Audit memo")
            if m:
                st.write(f"**{m.get('risk_level', '')} risk** · assertion at risk: {m.get('assertion_at_risk', '')} · "
                         f"library {', '.join(m.get('library_codes', []))}")
                st.write(m.get("why_suspicious", ""))
                for title, key in [("Evidence to obtain", "evidence_to_obtain"), ("Follow-up procedures", "follow_up_procedures"),
                                   ("Possible legitimate explanations", "possible_explanations")]:
                    st.write(f"**{title}**")
                    st.markdown("\n".join(f"- {x}" for x in m.get(key, [])))
                st.caption(f"Generated by {m.get('source', '')}. Must be reviewed by the auditor.")
            else:
                st.info(f"No memo: this entry scored {row['score']:.0f}, below the pipeline's cut-off of {s['alert_cutoff']}.")
                st.markdown("\n".join(f"- **{r['code']} {r['anomaly']}**: {r['audit_procedure']}" for r in recs_of(row)))
            st.subheader("Auditor decision")
            cur = dec.loc[pick] if pick in dec.index else None
            choice = st.radio("Decision", STATUSES, horizontal=True,
                              index=STATUSES.index(cur["decision"]) if cur is not None else 0, key=f"d_{pick}")
            comment = st.text_area("Comment for the working papers", cur["comment"] if cur is not None else "", key=f"c_{pick}")
            if st.button("Save decision", type="primary"):
                save_decision(pick, choice, comment)
                st.success("Saved to data/output/decisions.csv")
                st.rerun()

# ------------------------------------------------------------------ models
with tab_mod:
    m = D["metrics"]
    st.caption(m.get("split", ""))
    if m.get("models"):
        st.write("**Model comparison** (unseen test period)")
        st.dataframe(pd.DataFrame(m["models"]).T, width="stretch")
        st.write("**Circularity test**: recall by anomaly type (held-out types were never shown to XGBoost)")
        st.dataframe(pd.DataFrame(m["by_type"]), hide_index=True, width="stretch")
        if m.get("person2_reported"):
            st.write("**Person 2's model, own temporal test**")
            st.json(m["person2_reported"].get("xgboost_threshold_0_5", m["person2_reported"]), expanded=False)
        st.write("**What drives XGBoost**")
        st.bar_chart(pd.DataFrame(m["feature_importance"][:10]).set_index("feature")["importance"], horizontal=True)
    else:
        st.info("No labelled anomalies in this run: scored with rules and unsupervised detectors only.")
    fc = D.get("forecast", {})
    if fc.get("months"):
        st.write("**Revenue: expected vs actual**", f"({fc.get('method', '')})")
        st.line_chart(pd.DataFrame(fc["months"]).set_index("month")[["actual", "expected", "low", "high"]])

# ------------------------------------------------------------------ summary
with tab_sum:
    sm = D["summary"]
    st.write(sm.get("overview", ""))
    for title, key in [("Key themes", "key_themes"), ("Recommended next steps", "recommended_next_steps"), ("Limitations", "limitations")]:
        st.write(f"**{title}**")
        st.markdown("\n".join(f"- {x}" for x in sm.get(key, [])))
    st.caption(sm.get("source", ""))
    st.write("**Alerts by theme**")
    st.bar_chart(pd.Series(D.get("themes", {})), horizontal=True)

# ------------------------------------------------------------------ data
with tab_data:
    st.write("**Datacard**")
    st.dataframe(pd.Series(D["dataset"]["datacard"]).astype(str).rename("value"), width="stretch")
    st.write(f"Source: [{D['dataset']['name']}]({D['dataset']['url']}) · {D['dataset']['license']} · "
             f"holidays {D['dataset']['holiday_country']} ({D['dataset']['holiday_source']})")
    for w in D["dataset"].get("warnings", []):
        st.warning(w)
