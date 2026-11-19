"""Evaluation and optional supervised XGBoost benchmark for JournalGuard AI."""
from pathlib import Path
import json
import numpy as np
import pandas as pd

from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    precision_score, recall_score, f1_score, confusion_matrix,
    classification_report, average_precision_score
)

from journalguard_ml import (
    build_entry_dataset, engineer_features, JournalGuardDetector,
    FEATURE_COLUMNS, evaluate_predictions
)


def run_isolation_forest_evaluation(postings: pd.DataFrame, output_dir="outputs"):
    """
    Holdout evaluation at journal-entry level.
    Uses original `label` only as y_true, never as X.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    entries = engineer_features(build_entry_dataset(postings))
    if "ground_truth_label" not in entries:
        raise ValueError("Le dataset ne contient pas de colonne label exploitable.")

    y = entries["ground_truth_label"].fillna(0).astype(int)
    if y.nunique() < 2:
        raise ValueError("Il faut des écritures normales ET anormales pour calculer les métriques.")

    train_idx, test_idx = train_test_split(
        entries.index, test_size=0.25, random_state=42, stratify=y
    )
    train = entries.loc[train_idx].copy()
    test = entries.loc[test_idx].copy()

    detector = JournalGuardDetector(contamination=0.05, random_state=42, n_estimators=200)
    detector.fit(train)

    pred = detector.predict_labels(test)
    score = detector.raw_anomaly_score(test)
    metrics = evaluate_predictions(y.loc[test_idx], pred, score)

    result = test.copy()
    result["actual_label"] = y.loc[test_idx]
    result["predicted_anomaly"] = pred
    result["raw_anomaly_score"] = score
    result.to_csv(out / "isolation_forest_test_predictions.csv", index=False)

    with open(out / "isolation_forest_metrics.json", "w", encoding="utf-8") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)

    detector.save(out / "isolation_forest.pkl")
    return metrics, detector, result


def run_optional_xgboost(postings: pd.DataFrame, output_dir="outputs"):
    """
    Supervised benchmark. Runs only if XGBoost is installed and both classes
    have enough observations. Original labels are target y, not features.
    """
    try:
        from xgboost import XGBClassifier
        from sklearn.impute import SimpleImputer
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import RobustScaler
    except ImportError as exc:
        raise ImportError("Installez xgboost pour lancer ce benchmark : pip install xgboost") from exc

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    entries = engineer_features(build_entry_dataset(postings))
    if "ground_truth_label" not in entries:
        raise ValueError("Le dataset ne contient pas de colonne label.")

    y = entries["ground_truth_label"].fillna(0).astype(int)
    if y.value_counts().min() < 5:
        raise ValueError("Pas assez d'exemples dans la classe minoritaire pour un split fiable.")

    X = entries[FEATURE_COLUMNS].apply(pd.to_numeric, errors="coerce")
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, random_state=42, stratify=y
    )
    ratio = max(1.0, float((y_train == 0).sum()) / max(1, (y_train == 1).sum()))

    model = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler", RobustScaler()),
        ("xgb", XGBClassifier(
            n_estimators=150, max_depth=4, learning_rate=0.05,
            subsample=0.9, colsample_bytree=0.9,
            scale_pos_weight=ratio, random_state=42,
            eval_metric="logloss", n_jobs=-1
        ))
    ])
    model.fit(X_train, y_train)
    prob = model.predict_proba(X_test)[:, 1]
    pred = (prob >= 0.5).astype(int)

    metrics = {
        "precision": float(precision_score(y_test, pred, zero_division=0)),
        "recall": float(recall_score(y_test, pred, zero_division=0)),
        "f1_score": float(f1_score(y_test, pred, zero_division=0)),
        "average_precision": float(average_precision_score(y_test, prob)),
        "confusion_matrix": confusion_matrix(y_test, pred).tolist(),
        "classification_report": classification_report(
            y_test, pred, zero_division=0, output_dict=True
        )
    }
    import joblib
    joblib.dump(model, out / "xgboost_model.pkl")
    with open(out / "xgboost_metrics.json", "w", encoding="utf-8") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)

    # Optional SHAP explanation for the supervised tree model.
    try:
        import shap
        xgb_step = model.named_steps["xgb"]
        x_test_transformed = model.named_steps["scaler"].transform(
            model.named_steps["imputer"].transform(X_test)
        )
        explainer = shap.TreeExplainer(xgb_step)
        shap_values = explainer.shap_values(x_test_transformed)
        np.save(out / "xgboost_shap_values.npy", np.asarray(shap_values))
        with open(out / "xgboost_shap_feature_names.json", "w", encoding="utf-8") as f:
            json.dump(FEATURE_COLUMNS, f, ensure_ascii=False, indent=2)
    except Exception as exc:
        print(f"SHAP non exécuté (facultatif) : {exc}")

    return metrics, model


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="CSV brut des lignes comptables DIB")
    parser.add_argument("--output", default="outputs")
    args = parser.parse_args()

    raw = pd.read_csv(args.input)
    metrics, _, _ = run_isolation_forest_evaluation(raw, args.output)
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
