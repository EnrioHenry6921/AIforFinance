"""
ask.py - Ask a question about the alerts in plain language (local LLM, data stays on the laptop).

    python -m pipeline.ask "Which users have the most off-hours alerts?"
    python -m pipeline.ask "Show the largest cash alerts" --model llama3

Reads data/output/entries_scored.csv written by `python -m pipeline.run`. Without a running Ollama
it answers simple counting questions itself (alerts by user, by theme) and says so.
"""
import argparse

import pandas as pd

from . import config, genai


def load_alerts():
    f = config.OUT_DIR / "entries_scored.csv"
    if not f.exists():
        raise SystemExit("No scored entries yet: run `python -m pipeline.run` first.")
    s = pd.read_csv(f, low_memory=False, parse_dates=["posting_date"])
    a = s[s["alert"] == 1].sort_values("risk_score", ascending=False).copy()
    flag_cols = [c for c in genai_flags() if c in a]
    a["rule_hits"] = [[genai_flags()[c] for c in flag_cols if r[c] > 0] for _, r in a[flag_cols].iterrows()]
    a["theme"] = [genai.theme(r) for _, r in a.iterrows()]
    return a


def genai_flags():
    from .features import LABEL
    from .model import RULES
    return {f: LABEL[f] for f in RULES}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("question")
    ap.add_argument("--model", default=config.OLLAMA_MODEL)
    a = ap.parse_args(argv)
    alerts = load_alerts()
    use = genai.ollama_available()
    res = genai.ask(a.question, alerts, use, a.model)
    print(res.get("answer", res) if isinstance(res, dict) else res)
    if isinstance(res, dict) and res.get("entry_ids"):
        print("Entries:", ", ".join(map(str, res["entry_ids"])))
    if not use:
        print("\n(local LLM not running: offline summary)\nAlerts by user:\n" + alerts["user"].value_counts().head(10).to_string()
              + "\n\nAlerts by theme:\n" + alerts["theme"].value_counts().to_string())
    return res


if __name__ == "__main__":
    main()
