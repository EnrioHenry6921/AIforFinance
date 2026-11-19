"""
JournalGuard AI — Person 2: anomaly detection engine.

Works with the DIB General Ledger posting-line dataset.
Expected entry identifier: posting_id.
Ground-truth columns label and marking are retained for evaluation,
but NEVER used as model input features.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import re
import warnings

import numpy as np
import pandas as pd
import joblib

from sklearn.ensemble import IsolationForest
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import RobustScaler
from sklearn.metrics import (
    precision_score, recall_score, f1_score, confusion_matrix,
    classification_report, average_precision_score
)

ENTRY_ID_CANDIDATES = ["posting_id", "journal_entry_id", "entry_id", "document_id"]
DATE_CANDIDATES = ["posting_date", "document_date", "entered_date", "date"]
ENTERED_DATE_CANDIDATES = ["entered_date", "entry_date", "created_at", "timestamp"]
DEBIT_CANDIDATES = ["debit", "debit_amount", "amount_debit", "local_debit"]
CREDIT_CANDIDATES = ["credit", "credit_amount", "amount_credit", "local_credit"]
AMOUNT_CANDIDATES = ["amount", "amount_lc", "local_amount", "transaction_amount", "value"]
ACCOUNT_CANDIDATES = ["gl_account", "account", "account_number", "account_id"]
LABEL_CANDIDATES = ["label", "is_anomaly", "anomaly", "fraud_label"]
MARKING_CANDIDATES = ["marking", "anomaly_type", "scenario"]
REFERENCE_CANDIDATES = ["document_number", "document_no", "invoice_number", "reference", "document_reference"]


def _find_col(df: pd.DataFrame, candidates):
    lookup = {str(c).strip().lower(): c for c in df.columns}
    for candidate in candidates:
        if candidate.lower() in lookup:
            return lookup[candidate.lower()]
    return None


def _to_num(series):
    return pd.to_numeric(series.astype(str).str.replace(",", ".", regex=False), errors="coerce")


def _truthy_label(value):
    if pd.isna(value):
        return 0
    if isinstance(value, (int, float, np.integer, np.floating)):
        return int(value != 0)
    s = str(value).strip().lower()
    if s in {"", "0", "false", "normal", "none", "no", "nan"}:
        return 0
    if s in {"1", "true", "yes", "anomaly", "fraud", "suspicious"}:
        return 1
    # Non-empty textual labels are treated as a positive label.
    return 1


def build_entry_dataset(postings: pd.DataFrame) -> pd.DataFrame:
    """
    Convert posting lines into one row per complete journal entry.
    Keeps original label/marking only as ground truth, never as features.
    """
    if postings.empty:
        raise ValueError("Le fichier fourni est vide.")

    id_col = _find_col(postings, ENTRY_ID_CANDIDATES)
    if id_col is None:
        raise ValueError(
            "Identifiant d'écriture introuvable. Le dataset DIB attendu doit "
            "contenir 'posting_id'. Colonnes reçues : " + ", ".join(map(str, postings.columns))
        )

    data = postings.copy()
    data[id_col] = data[id_col].astype(str)
    if data[id_col].isna().any():
        raise ValueError("Certaines lignes n'ont pas d'identifiant d'écriture.")

    debit_col = _find_col(data, DEBIT_CANDIDATES)
    credit_col = _find_col(data, CREDIT_CANDIDATES)
    amount_col = _find_col(data, AMOUNT_CANDIDATES)
    account_col = _find_col(data, ACCOUNT_CANDIDATES)
    label_col = _find_col(data, LABEL_CANDIDATES)
    marking_col = _find_col(data, MARKING_CANDIDATES)
    date_col = _find_col(data, DATE_CANDIDATES)
    entered_col = _find_col(data, ENTERED_DATE_CANDIDATES)
    ref_col = _find_col(data, REFERENCE_CANDIDATES)

    for c in [debit_col, credit_col, amount_col]:
        if c is not None:
            data[c] = _to_num(data[c])

    # Identify available date columns and parse them without assuming a format.
    date_cols = []
    for candidate in DATE_CANDIDATES:
        col = _find_col(data, [candidate])
        if col is not None and col not in date_cols:
            data[col] = pd.to_datetime(data[col], errors="coerce", dayfirst=True)
            date_cols.append(col)

    def first_non_null(s):
        s = s.dropna()
        return s.iloc[0] if len(s) else pd.NaT

    agg = {
        "posting_line_count": (id_col, "size"),
    }
    if account_col:
        agg["account_count"] = (account_col, "nunique")
        agg["account_list"] = (account_col, lambda s: " | ".join(sorted(set(s.dropna().astype(str)))[:30]))
    else:
        agg["account_count"] = (id_col, "size")
        agg["account_list"] = (id_col, lambda s: "")

    for c in date_cols:
        agg[c] = (c, first_non_null)

    if debit_col:
        agg["total_debit"] = (debit_col, lambda s: s.fillna(0).sum())
    if credit_col:
        agg["total_credit"] = (credit_col, lambda s: s.fillna(0).sum())

    if amount_col:
        agg["absolute_line_amount_sum"] = (amount_col, lambda s: s.abs().fillna(0).sum())
        agg["signed_line_amount_sum"] = (amount_col, lambda s: s.fillna(0).sum())

    if label_col:
        agg["ground_truth_label"] = (label_col, lambda s: int(any(_truthy_label(v) for v in s)))
    if marking_col:
        agg["ground_truth_marking"] = (marking_col, lambda s: " | ".join(sorted(set(s.dropna().astype(str)))[:20]))
    if entered_col and entered_col not in date_cols:
        data[entered_col] = pd.to_datetime(data[entered_col], errors="coerce", dayfirst=True)
        agg[entered_col] = (entered_col, first_non_null)

    if ref_col:
        agg["document_reference"] = (ref_col, first_non_null)

    entries = data.groupby(id_col, dropna=False).agg(**agg).reset_index()
    entries = entries.rename(columns={id_col: "entry_id"})

    # A journal entry's value is counted once, not once for both debit and credit.
    if "total_debit" in entries.columns and "total_credit" in entries.columns:
        entries["entry_amount"] = entries[["total_debit", "total_credit"]].max(axis=1)
        entries["debit_credit_difference"] = (
            entries["total_debit"].fillna(0) - entries["total_credit"].fillna(0)
        ).abs()
        entries["has_debit_credit_data"] = 1
    elif "absolute_line_amount_sum" in entries.columns:
        # Without separate debit/credit columns, use half the absolute line total
        # only when signed amounts appear to contain both sides of double entry.
        entries["entry_amount"] = entries["absolute_line_amount_sum"]
        entries["debit_credit_difference"] = np.nan
        entries["has_debit_credit_data"] = 0
    else:
        entries["entry_amount"] = np.nan
        entries["debit_credit_difference"] = np.nan
        entries["has_debit_credit_data"] = 0

    # Duplicate reference = same document reference used by multiple entries.
    if "document_reference" in entries.columns:
        ref = entries["document_reference"].astype(str).str.strip()
        valid = ref.ne("") & ref.ne("nan") & ref.ne("None")
        counts = ref[valid].value_counts()
        entries["duplicate_reference"] = (valid & ref.map(counts).fillna(0).gt(1)).astype(int)
    else:
        entries["duplicate_reference"] = 0

    return entries


def engineer_features(entries: pd.DataFrame) -> pd.DataFrame:
    """Create explainable numerical features at journal-entry level."""
    df = entries.copy()
    df["entry_amount"] = _to_num(df.get("entry_amount", pd.Series(np.nan, index=df.index))).abs()
    df["log_entry_amount"] = np.log1p(df["entry_amount"].clip(lower=0))
    df["posting_line_count"] = _to_num(df.get("posting_line_count", pd.Series(1, index=df.index))).fillna(1)
    df["account_count"] = _to_num(df.get("account_count", pd.Series(1, index=df.index))).fillna(1)

    post_col = _find_col(df, ["posting_date", "document_date", "entered_date", "date"])
    if post_col:
        dt = pd.to_datetime(df[post_col], errors="coerce", dayfirst=True)
        df["posting_weekday"] = dt.dt.weekday
        df["is_weekend"] = dt.dt.weekday.isin([5, 6]).astype(float)
        df["is_month_end"] = (dt.dt.is_month_end).astype(float)
        df["is_year_end"] = (
            (dt.dt.month == 12) & (dt.dt.day >= 28)
        ).astype(float)
    else:
        df["posting_weekday"] = np.nan
        df["is_weekend"] = 0.0
        df["is_month_end"] = 0.0
        df["is_year_end"] = 0.0

    entered_col = _find_col(df, ["entered_date", "entry_date", "created_at", "timestamp"])
    if entered_col:
        entered = pd.to_datetime(df[entered_col], errors="coerce", dayfirst=True)
        df["posting_hour"] = entered.dt.hour
        df["is_unusual_hour"] = ((entered.dt.hour < 6) | (entered.dt.hour >= 20)).astype(float)
    else:
        df["posting_hour"] = np.nan
        df["is_unusual_hour"] = 0.0

    # Round amount: multiples of 1,000 or 100 depending on amount size.
    amt = df["entry_amount"].fillna(0)
    df["is_round_amount"] = (
        ((amt >= 1000) & (np.isclose(amt % 1000, 0, atol=0.01))) |
        ((amt >= 100) & (amt < 1000) & (np.isclose(amt % 100, 0, atol=0.01)))
    ).astype(float)

    diff = _to_num(df.get("debit_credit_difference", pd.Series(np.nan, index=df.index)))
    df["is_unbalanced"] = (diff.fillna(0).abs() > 0.01).astype(float)
    df["duplicate_reference"] = _to_num(
        df.get("duplicate_reference", pd.Series(0, index=df.index))
    ).fillna(0).astype(float)

    # Preserve a human-readable account descriptor for review, not model fitting.
    if "account_list" not in df:
        df["account_list"] = ""

    return df


FEATURE_COLUMNS = [
    "log_entry_amount",
    "posting_line_count",
    "account_count",
    "posting_weekday",
    "posting_hour",
    "is_weekend",
    "is_month_end",
    "is_year_end",
    "is_unusual_hour",
    "is_round_amount",
    "is_unbalanced",
    "duplicate_reference",
]


@dataclass
class JournalGuardDetector:
    contamination: float = 0.05
    random_state: int = 42
    n_estimators: int = 200
    model: Optional[Pipeline] = None
    feature_columns: tuple = tuple(FEATURE_COLUMNS)

    def _matrix(self, entries):
        X = entries.reindex(columns=list(self.feature_columns)).copy()
        for col in X.columns:
            X[col] = _to_num(X[col])
        return X.replace([np.inf, -np.inf], np.nan)

    def fit(self, entries: pd.DataFrame):
        X = self._matrix(entries)
        if len(X) < 10:
            raise ValueError(
                f"Il faut au moins 10 écritures pour entraîner Isolation Forest (reçu : {len(X)})."
            )
        self.model = Pipeline([
            ("imputer", SimpleImputer(strategy="median", keep_empty_features=False)),
            ("scaler", RobustScaler()),
            ("isolation_forest", IsolationForest(
                n_estimators=self.n_estimators,
                contamination=self.contamination,
                random_state=self.random_state,
                n_jobs=-1
            ))
        ])
        self.model.fit(X)
        return self

    def raw_anomaly_score(self, entries):
        if self.model is None:
            raise RuntimeError("Le modèle n'est pas entraîné. Appelez fit() d'abord.")
        # Higher score = more anomalous.
        return -self.model.decision_function(self._matrix(entries))

    def predict_labels(self, entries):
        if self.model is None:
            raise RuntimeError("Le modèle n'est pas entraîné.")
        return (self.model.predict(self._matrix(entries)) == -1).astype(int)

    def save(self, path):
        joblib.dump(self, path)

    @classmethod
    def load(cls, path):
        return joblib.load(path)


def add_risk_scores(entries: pd.DataFrame, detector: JournalGuardDetector) -> pd.DataFrame:
    """Combine model, rule and statistical scores into a 0–100 risk score."""
    df = entries.copy()
    raw = detector.raw_anomaly_score(df)
    # Percentile-based calibration makes the score easy to interpret within this run.
    df["ml_anomaly_score"] = pd.Series(raw, index=df.index).rank(pct=True) * 100

    rule_cols = [
        "is_weekend", "is_month_end", "is_year_end", "is_unusual_hour",
        "is_round_amount", "is_unbalanced", "duplicate_reference"
    ]
    for c in rule_cols:
        if c not in df:
            df[c] = 0
    df["rule_count"] = df[rule_cols].fillna(0).astype(float).sum(axis=1)
    df["rule_score"] = (df["rule_count"].clip(upper=4) / 4) * 100

    amount_pct = df["log_entry_amount"].rank(pct=True).fillna(0) * 100
    lines_pct = df["posting_line_count"].rank(pct=True).fillna(0) * 100
    df["statistical_score"] = 0.7 * amount_pct + 0.3 * lines_pct

    df["risk_score"] = (
        0.50 * df["ml_anomaly_score"] +
        0.30 * df["rule_score"] +
        0.20 * df["statistical_score"]
    ).clip(0, 100).round(1)

    df["risk_level"] = pd.cut(
        df["risk_score"],
        bins=[-0.001, 39.999, 69.999, 100],
        labels=["Low", "Medium", "High"]
    ).astype(str)

    def flags(row):
        labels = []
        mapping = {
            "is_weekend": "Posting le week-end",
            "is_month_end": "Posting en fin de mois",
            "is_year_end": "Posting en fin d'année",
            "is_unusual_hour": "Heure de saisie inhabituelle",
            "is_round_amount": "Montant rond",
            "is_unbalanced": "Débit/crédit non équilibrés",
            "duplicate_reference": "Référence documentaire répétée",
        }
        for col, label in mapping.items():
            if pd.notna(row.get(col)) and float(row.get(col, 0)) > 0:
                labels.append(label)
        return " ; ".join(labels) if labels else "Aucune règle déclenchée"

    df["rule_flags"] = df.apply(flags, axis=1)
    df["model_anomaly"] = detector.predict_labels(df)
    return df.sort_values("risk_score", ascending=False).reset_index(drop=True)


def analyse_ledger(postings: pd.DataFrame, detector: Optional[JournalGuardDetector] = None,
                   model_path: Optional[str] = None) -> pd.DataFrame:
    """
    One-call interface for Person 4.
    Input can be raw posting lines or already aggregated entries.
    """
    if "entry_id" in postings.columns and "posting_line_count" in postings.columns:
        entries = postings.copy()
    else:
        entries = build_entry_dataset(postings)
    entries = engineer_features(entries)

    if detector is None and model_path and Path(model_path).exists():
        detector = JournalGuardDetector.load(model_path)
    if detector is None:
        detector = JournalGuardDetector().fit(entries)

    return add_risk_scores(entries, detector)


def evaluate_predictions(y_true, y_pred, y_score=None):
    """Return standard classification metrics; y_true must be original labels."""
    y_true = np.asarray(y_true).astype(int)
    y_pred = np.asarray(y_pred).astype(int)
    result = {
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "f1_score": float(f1_score(y_true, y_pred, zero_division=0)),
        "confusion_matrix": confusion_matrix(y_true, y_pred).tolist(),
        "classification_report": classification_report(
            y_true, y_pred, zero_division=0, output_dict=True
        ),
    }
    if y_score is not None and len(np.unique(y_true)) > 1:
        result["average_precision"] = float(average_precision_score(y_true, y_score))
    return result


def get_entry_explanation(row: pd.Series) -> list[str]:
    """Transparent, rule-based explanations for the Isolation Forest result."""
    reasons = []
    checks = [
        ("is_weekend", "L'écriture a été comptabilisée pendant le week-end."),
        ("is_month_end", "L'écriture a été comptabilisée en fin de mois."),
        ("is_year_end", "L'écriture a été comptabilisée en fin d'année."),
        ("is_unusual_hour", "L'heure de saisie est inhabituelle selon la règle configurée."),
        ("is_round_amount", "Le montant est un montant rond."),
        ("is_unbalanced", "Le total débit et le total crédit ne sont pas équilibrés."),
        ("duplicate_reference", "La référence documentaire apparaît sur plusieurs écritures."),
    ]
    for col, message in checks:
        if col in row and pd.notna(row[col]) and float(row[col]) > 0:
            reasons.append(message)

    if not reasons:
        reasons.append(
            "Le modèle a détecté une combinaison de caractéristiques inhabituelle. "
            "Aucune règle métier individuelle n'a été déclenchée."
        )
    return reasons
