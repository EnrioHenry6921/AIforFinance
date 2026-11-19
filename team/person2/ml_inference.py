"""
Module d'inférence Machine Learning — JournalGuard AI (Personne 2)
Fonction principale : analyse_ledger(df)

Ce module :
1. Regroupe automatiquement les lignes comptables par écriture (posting_id).
2. Calcule les 12 variables explicatives retenues pour le modèle.
3. Applique le modèle entraîné (XGBoost si disponible/entraîné, sinon le pipeline
   Gradient Boosting pré-entraîné inclus dans models/journalguard_model.joblib).
4. Renvoie un DataFrame complet avec xgb_anomaly_score, risk_score, risk_level,
   predicted_anomaly et risk_interpretation.
"""

from pathlib import Path
import joblib
import numpy as np
import pandas as pd

FEATURE_COLUMNS = [
    "log_entry_amount",
    "posting_line_count",
    "account_count",
    "posting_weekday",
    "posting_month",
    "posting_day",
    "posting_hour",
    "doc_to_post_days",
    "post_to_enter_days",
    "user_entry_count",
    "account_signature",
    "user",
]

OUTPUT_COLUMNS = [
    "posting_id",
    "posting_date",
    "document_date",
    "entered_date",
    "user",
    "account_signature",
    "posting_line_count",
    "account_count",
    "total_debit",
    "total_credit",
    "entry_amount",
    "xgb_anomaly_score",
    "risk_score",
    "risk_level",
    "predicted_anomaly",
    "account_names",
    "debit_credit_difference",
    "log_entry_amount",
    "posting_weekday",
    "posting_month",
    "posting_day",
    "posting_hour",
    "is_weekend_calc",
    "is_unusual_hour_calc",
    "doc_to_post_days",
    "post_to_enter_days",
    "user_entry_count",
    "risk_interpretation",
]

CAVEAT_TEXT = (
    "Score de similarité avec les anomalies labellisées du dataset ; "
    "ce score ne constitue pas une preuve de fraude."
)


def _prepare_entry_level(df: pd.DataFrame) -> pd.DataFrame:
    """Agrège les lignes comptables par écriture (posting_id) et crée les 12 variables."""
    data = df.copy()

    # Si le DataFrame est déjà au niveau écriture avec les colonnes calculées
    if all(col in data.columns for col in FEATURE_COLUMNS) and "posting_id" in data.columns:
        return data

    if "debit" not in data.columns or "credit" not in data.columns:
        cd = data["cd_flag"].astype(str).str.upper().str.strip()
        amt = pd.to_numeric(data["amount"], errors="coerce").fillna(0.0)
        data["debit"] = np.where(cd == "D", amt, 0.0)
        data["credit"] = np.where(cd == "C", amt, 0.0)

    data["gl_account_str"] = data["gl_account"].astype(str).str.strip()
    data["posting_date_dt"] = pd.to_datetime(data["posting_date"], errors="coerce")
    data["document_date_dt"] = pd.to_datetime(data["document_date"], errors="coerce")
    data["entered_date_dt"] = pd.to_datetime(data["entered_date"], errors="coerce")

    agg_dict = {
        "posting_date_dt": ("posting_date_dt", "first"),
        "document_date_dt": ("document_date_dt", "first"),
        "entered_date_dt": ("entered_date_dt", "first"),
        "user": ("user", "first"),
        "posting_line_count": ("gl_account_str", "count"),
        "account_count": ("gl_account_str", "nunique"),
        "account_signature": (
            "gl_account_str",
            lambda s: "|".join(sorted(set(s))),
        ),
        "total_debit": ("debit", "sum"),
        "total_credit": ("credit", "sum"),
    }

    if "gl_account_name" in data.columns:
        agg_dict["account_names"] = (
            "gl_account_name",
            lambda s: " | ".join(dict.fromkeys(s.astype(str))),
        )

    entries = data.groupby("posting_id", as_index=False).agg(**agg_dict)

    if "account_names" not in entries.columns:
        entries["account_names"] = ""

    entries["total_debit"] = entries["total_debit"].round(2)
    entries["total_credit"] = entries["total_credit"].round(2)
    entries["debit_credit_difference"] = (
        entries["total_debit"] - entries["total_credit"]
    ).round(2)
    entries["entry_amount"] = np.maximum(
        entries["total_debit"], entries["total_credit"]
    )
    entries["log_entry_amount"] = np.log1p(entries["entry_amount"].clip(lower=0))

    entries["posting_weekday"] = entries["posting_date_dt"].dt.weekday
    entries["posting_month"] = entries["posting_date_dt"].dt.month
    entries["posting_day"] = entries["posting_date_dt"].dt.day
    entries["posting_hour"] = entries["entered_date_dt"].dt.hour.fillna(0).astype(int)

    entries["is_weekend_calc"] = (entries["posting_weekday"] >= 5).astype(int)
    entries["is_unusual_hour_calc"] = (
        (entries["posting_hour"] < 8) | (entries["posting_hour"] >= 18)
    ).astype(int)

    entries["doc_to_post_days"] = (
        (entries["posting_date_dt"] - entries["document_date_dt"])
        .dt.total_seconds()
        .div(86400.0)
        .round(2)
    )
    entries["post_to_enter_days"] = (
        (entries["entered_date_dt"].dt.normalize() - entries["posting_date_dt"].dt.normalize())
        .dt.days.astype(float)
    )

    user_counts = entries["user"].value_counts()
    entries["user_entry_count"] = entries["user"].map(user_counts).astype(int)

    entries["posting_date"] = entries["posting_date_dt"].dt.strftime("%Y-%m-%d")
    entries["document_date"] = entries["document_date_dt"].dt.strftime("%Y-%m-%d")
    entries["entered_date"] = entries["entered_date_dt"].dt.strftime("%Y-%m-%d %H:%M:%S")

    return entries


def _assign_risk_level(score: float) -> str:
    if score >= 70.0:
        return "High"
    if score >= 40.0:
        return "Medium"
    return "Low"


def analyse_ledger(
    df: pd.DataFrame,
    model_path: str | Path = "models/journalguard_model.joblib",
    threshold: float = 0.50,
) -> pd.DataFrame:
    """
    Fonction principale à appeler depuis Streamlit.
    Prend en entrée un DataFrame de lignes comptables (CSV importé)
    et renvoie un DataFrame d'écritures scorées.
    """
    model_file = Path(model_path)
    if not model_file.exists():
        alt_path = Path(__file__).parent / model_path
        if alt_path.exists():
            model_file = alt_path
        else:
            raise FileNotFoundError(
                f"Modèle introuvable : {model_file}. "
                "Vérifiez que le dossier 'models/' contient 'journalguard_model.joblib'."
            )

    entries_df = _prepare_entry_level(df)

    pipeline = joblib.load(model_file)
    X = entries_df[FEATURE_COLUMNS]
    proba = pipeline.predict_proba(X)[:, 1]

    entries_df["xgb_anomaly_score"] = proba * 100.0
    entries_df["risk_score"] = entries_df["xgb_anomaly_score"].round(1)
    entries_df["risk_level"] = entries_df["xgb_anomaly_score"].apply(_assign_risk_level)
    entries_df["predicted_anomaly"] = (proba >= threshold).astype(int)
    entries_df["risk_interpretation"] = CAVEAT_TEXT

    final_cols = [c for c in OUTPUT_COLUMNS if c in entries_df.columns]
    result = entries_df[final_cols].sort_values(
        by="xgb_anomaly_score", ascending=False
    ).reset_index(drop=True)

    return result
