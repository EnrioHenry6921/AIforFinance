"""Portfolio-level summary of model-scored journal entries."""
import pandas as pd


def generate_engagement_summary(scored_df):
    """Return a human-readable summary; flagged value is exposure under review, not loss."""
    if scored_df is None or len(scored_df)==0:
        return "No journal entries were supplied for screening."
    df=scored_df.copy()
    score_col=next((c for c in ["risk_score","xgb_anomaly_score","anomaly_score"] if c in df.columns),None)
    level_col="risk_level" if "risk_level" in df.columns else None
    amount_col=next((c for c in ["entry_amount","amount","total_debit"] if c in df.columns),None)
    if score_col:
        scores=pd.to_numeric(df[score_col],errors="coerce").fillna(0)
        high=int((scores>=70).sum()); medium=int(((scores>=40)&(scores<70)).sum())
        flagged=int((scores>=40).sum())
    elif level_col:
        levels=df[level_col].astype(str).str.title(); high=int((levels=="High").sum()); medium=int((levels=="Medium").sum()); flagged=high+medium
    else:
        high=medium=flagged=0
    total_value=None
    if amount_col:
        amounts=pd.to_numeric(df[amount_col],errors="coerce").fillna(0)
        total_value=float(amounts[scores>=40].sum()) if score_col else float(amounts.sum())
    # Only use explicit anomaly/signal labels if present. Do not infer from the score.
    anomaly_col=next((c for c in ["anomaly_type","risk_reasons","risk_interpretation"] if c in df.columns),None)
    common="Not available from supplied columns"
    if anomaly_col:
        vals=df[anomaly_col].dropna().astype(str)
        vals=vals[vals.str.strip()!=""]
        if len(vals): common=", ".join(vals.value_counts().head(5).index.tolist())
    lines=["JOURNALGUARD AI — ENGAGEMENT SCREENING SUMMARY", "",
        f"Journal entries screened: {len(df):,}",f"High-risk entries: {high:,}",
        f"Medium-risk entries: {medium:,}",f"Entries at Medium or High level: {flagged:,}",
        f"Common supplied indicators: {common}"]
    if total_value is not None:
        lines.append(f"Total value of entries at/above review threshold: {total_value:,.2f} (value under review, NOT a loss estimate)")
    lines += ["", "Interpretation and limitations:",
        "- Risk scores prioritise audit attention; they are not probabilities of fraud.",
        "- A flagged entry is not necessarily misstated or fraudulent.",
        "- Indicator counts depend on the fields supplied; missing fields are not treated as negative evidence.",
        "- Auditors must obtain and evaluate sufficient appropriate evidence before reaching conclusions."]
    return "\n".join(lines)
