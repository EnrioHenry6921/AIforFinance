"""
End-to-end and unit tests for JournalGuard AI.  Run:  python -m pytest -q
Uses small synthetic ledgers so the whole suite runs in about a minute; the real DIB file is tested
when it is present in data/raw (test_original_dib).
"""
import json
import math

import numpy as np
import pandas as pd
import pytest

from pipeline import config, features, genai, loader, model, person2_model, recommend, run, schema, synthetic


@pytest.fixture(scope="session")
def tmp(tmp_path_factory):
    return tmp_path_factory.mktemp("jg")


@pytest.fixture(scope="session")
def dib(tmp):
    df = synthetic.generate(entries=3000, years=(2023, 2024), anomaly_rate=0.01, seed=1)
    p = tmp / "syn_dib.csv"
    df.to_csv(p, sep=";", index=False)
    return p, df


def _run(tmp, *args):
    out = tmp / f"d{abs(hash(args)) % 10**6}.json"
    data = run.main([*args, "--out", str(out), "--llm-top", "0"])
    text = out.read_text()
    assert "NaN" not in text and "Infinity" not in text           # the browser refuses NaN in JSON
    return data, json.loads(text)


# ---------------------------------------------------------------- loading
def test_semicolon_and_labels(dib):
    p, df = dib
    lines, meta = loader.load(str(p))
    assert meta["label_source"] == "dataset"
    assert lines["entry_id"].nunique() == df["posting_id"].nunique()
    assert meta["has_entry_time"] and meta["chart"] == "SKR03"
    for col in config.DIB_LEAKY_COLUMNS:          # generator columns are dropped on load (our own high_cash
        assert col not in lines.columns           # feature is recomputed from accounts and amounts)


def test_debit_equals_credit(dib):
    lines, meta = loader.load(str(dib[0]))
    g = lines.groupby("entry_id")[["debit", "credit"]].sum()
    assert np.allclose(g["debit"], g["credit"], atol=0.02)


def test_schema_rejects_garbage(tmp):
    bad = tmp / "bad.csv"
    pd.DataFrame({"entry_id": [1, 2], "posting_date": ["x", "y"], "account": ["1", "2"], "amount": [1, -1]}).to_csv(bad, index=False)
    with pytest.raises(schema.LedgerError):
        lines, meta = loader.load(str(bad))
        schema.validate(lines, meta)


def test_missing_columns_message(tmp):
    bad = tmp / "nocols.csv"
    pd.DataFrame({"foo": [1], "bar": [2]}).to_csv(bad, index=False)
    with pytest.raises(ValueError, match="mapping"):
        loader.load(str(bad))


# ---------------------------------------------------------------- features
def test_working_hours_from_data():
    h = pd.Series([9] * 50 + [10] * 50 + [11] * 50 + [15] * 50 + [16] * 50 + [23])
    assert features.working_hours(h) == (9, 16)
    assert features.outside_working_hours(h).sum() == 1


def test_fec_has_no_night_flags(tmp, dib):
    fec = synthetic.to_fec(dib[1])
    p = tmp / "syn_fec.txt"
    fec.to_csv(p, sep="|", index=False)
    lines, meta = loader.load(str(p))
    assert meta["chart"] == "PCG" and not meta["has_entry_time"]
    e, _ = features.add_features(features.build_entries(lines), {}, meta["chart"], False, lines)
    assert e["is_night"].sum() == 0 and e["user_unusual_hour"].sum() == 0


def test_materiality_from_revenue(dib):
    lines, meta = loader.load(str(dib[0]))
    e, pm = features.add_features(features.build_entries(lines), {}, "SKR03", True, lines)
    assert pm and all(v > 0 for v in pm.values())


# ---------------------------------------------------------------- models
def test_signal_mapping():
    assert math.isclose(float(model.signal(0.8, 0.8)), 0.6, rel_tol=1e-6)
    assert float(model.signal(0.93, 0.99)) < 0.5 < float(model.signal(0.995, 0.99))


def test_person2_model_loads():
    if not person2_model.available():
        pytest.skip("models/person2_model.json missing")
    m = person2_model.load()
    assert len(m["trees"]) > 0 and len(m["numeric_features"]) == 10


def test_recommendations_use_person3_library():
    lib = recommend.library()
    assert {"1", "2", "3", "4", "5", "6", "7", "8"} <= set(lib)
    recs = recommend.recommend(["High cash disbursement", "Entered outside working hours"], [])
    assert [r["code"] for r in recs] == ["2", "5"]


# ---------------------------------------------------------------- end to end
def test_e2e_dib_labels(tmp, dib):
    data, js = _run(tmp, "--input", str(dib[0]))
    assert js["settings"]["label_source"] == "dataset" and js["settings"]["injected"] == 0
    assert js["kpis"]["entries"] == dib[1]["posting_id"].nunique()
    assert js["metrics"]["models"]["Risk score (combined)"]["recall"] is not None
    assert js["alerts"] and all("memo" in a and a["recommendations"] is not None for a in js["alerts"])
    assert (config.OUT_DIR / "JE_audit_alerts.xlsx").exists()


def test_e2e_fec_injected(tmp):
    p = tmp / "syn_fec.txt"
    data, js = _run(tmp, "--input", str(p))
    assert js["settings"]["chart"] == "PCG" and js["dataset"]["holiday_country"] == "FR"
    assert js["kpis"]["injected"] > 0
    assert js["metrics"]["models"]["Risk score (combined)"]["recall"] >= 0.5


def test_e2e_no_labels_one_year(tmp, dib):
    df = dib[1]
    one = df[pd.to_datetime(df["posting_date"]).dt.year == pd.to_datetime(df["posting_date"]).dt.year.min()]
    p = tmp / "one.csv"
    one.drop(columns=["label", "marking"]).to_csv(p, sep=";", index=False)
    data, js = _run(tmp, "--input", str(p), "--inject", "0")
    assert js["metrics"]["models"] == {} and js["kpis"]["alerts"] >= 0
    assert js["summary"]["overview"]


def test_e2e_generic_mapping(tmp, dib):
    d = dib[1]
    g = pd.DataFrame({"JE_no": d["posting_id"], "GL Date": pd.to_datetime(d["posting_date"]).dt.strftime("%d/%m/%Y"),
                      "Acct": d["gl_account"], "Signed": d["amount"].where(d["cd_flag"] == "D", -d["amount"]),
                      "Clerk": d["user"]})
    p, mp = tmp / "generic.csv", tmp / "map.json"
    g.to_csv(p, index=False)
    mp.write_text(json.dumps({"entry_id": "JE_no", "posting_date": "GL Date", "account": "Acct", "amount": "Signed",
                              "user": "Clerk"}))
    data, js = _run(tmp, "--input", str(p), "--map", str(mp))
    assert js["kpis"]["entries"] >= d["posting_id"].nunique()


def test_memo_never_claims_fraud(tmp, dib):
    data, js = _run(tmp, "--input", str(dib[0]))
    for a in js["alerts"][:50]:
        text = json.dumps(a["memo"]).lower()
        assert "is fraud" not in text and "committed fraud" not in text


@pytest.mark.skipif(not config.RAW_FILE.exists(), reason="original DIB file not in data/raw")
def test_original_dib(tmp):
    data, js = _run(tmp)
    m = js["metrics"]
    assert js["kpis"]["labelled"] == 850
    assert m["models"]["Risk score (combined)"]["pr_auc"] > 0.4      # honest temporal test, see README
    assert m["recall_seen_types"]["Risk score (combined)"] > 0.75
