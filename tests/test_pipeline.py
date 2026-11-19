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


# ---------------------------------------------------------------- regression tests (loader + forecast fixes)
def _write(tmp, name, df, sep=","):
    p = tmp / name
    df.to_csv(p, sep=sep, index=False)
    return p


def test_ids_with_leading_zeros_stay_distinct(tmp):
    df = pd.DataFrame({"entry_id": ["001", "001", "1", "1"], "posting_date": ["2024-01-05"] * 4,
                       "account": ["0401", "8400", "1200", "8400"], "debit": ["100", "0", "50", "0"],
                       "credit": ["0", "100", "0", "50"]})
    lines, _ = loader.load(str(_write(tmp, "zeros.csv", df)))
    assert sorted(lines["entry_id"].unique()) == ["001", "1"]
    assert "0401" in set(lines["account"])                         # leading zero kept on accounts too


def test_explicit_manual_flag_wins(tmp):
    df = pd.DataFrame({"entry_id": ["a_1", "a_1", "p_2", "p_2"], "posting_date": ["2024-01-05"] * 4,
                       "account": ["1200", "8400", "1200", "8400"], "amount": ["100", "-100", "50", "-50"],
                       "is_manual": ["1", "1", "0", "0"]})
    lines, meta = loader.load(str(_write(tmp, "flag.csv", df)))
    src = lines.groupby("entry_id")["source"].first()
    assert src["a_1"] == "manual" and src["p_2"] == "system"         # the id prefix would say the opposite
    assert meta["manual_flag_column"] == "is_manual"


def test_labels_through_mapping(tmp):
    df = pd.DataFrame({"JE": ["1", "1", "2", "2"], "D": ["05/01/2024"] * 4, "GL": ["1200", "8400", "1200", "8400"],
                       "Amt": ["100", "-100", "50", "-50"], "Flagged": ["yes", "yes", "no", "no"],
                       "Why": ["Round amount", "Round amount", "", ""]})
    mp = tmp / "lab_map.json"
    mp.write_text(json.dumps({"entry_id": "JE", "posting_date": "D", "account": "GL", "amount": "Amt",
                              "is_anomaly": "Flagged", "anomaly_type": "Why"}))
    lines, meta = loader.load(str(_write(tmp, "lab.csv", df)), str(mp))
    e = lines.groupby("entry_id").agg(a=("is_anomaly", "max"), t=("anomaly_type", "first"))
    assert e.loc["1", "a"] == 1 and e.loc["1", "t"] == "Round amount" and e.loc["2", "a"] == 0
    assert lines["posting_date"].iloc[0] == pd.Timestamp("2024-01-05")   # 05/01 = 5 January


def test_generic_file_sharing_dib_names_is_not_read_as_dib(tmp):
    df = pd.DataFrame({"posting_id": ["x1", "x1"], "posting_date": ["2024-03-01"] * 2, "gl_account": ["1200", "8400"],
                       "amount": ["10", "-10"]})                        # no cd_flag, entered_date, user, text
    lines, meta = loader.load(str(_write(tmp, "dibish.csv", df)))
    assert meta["format"] == "Generic ledger"
    assert lines["debit"].sum() == 10 and lines["credit"].sum() == 10


def test_amount_formats():
    s = pd.Series(["1234.56", "1234,56", "1 234,56", "1,234.56", "1.234,56", "-5", ""])
    assert loader._num(s).tolist() == [1234.56, 1234.56, 1234.56, 1234.56, 1234.56, -5.0, 0.0]


def test_forecast_uses_no_future_information():
    from pipeline import forecast
    idx = pd.date_range("2023-01-01", "2024-12-01", freq="MS")
    v = np.array([100] * 12 + [100, 110, 95, 105, 100, 98, 102, 100, 97, 103, 100, 101], float)
    led = lambda vals: pd.DataFrame({"account": "8400", "posting_date": idx, "credit": vals, "debit": 0.0})
    a = forecast.forecast_revenue(led(v), "SKR03")
    v2 = v.copy(); v2[-1] = 500
    b = forecast.forecast_revenue(led(v2), "SKR03")
    assert a["months"][:-1] == b["months"][:-1]                     # a later month never changes an earlier verdict
    assert b["months"][-1]["flag"] and not a["months"][-1]["flag"]
