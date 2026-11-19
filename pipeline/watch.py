"""
watch.py - Monitoring: score every ledger dropped in data/inbox, then send (or save) an alert email.

    python -m pipeline.watch            # check the inbox once (schedule it with cron / Task Scheduler)
    python -m pipeline.watch --every 60 # keep checking every 60 minutes

Email goes out only if JG_SMTP_HOST, JG_SMTP_USER, JG_SMTP_PASSWORD and JG_ALERT_TO are set as environment
variables (never in code). Otherwise the email is written to data/output/alert_email.eml to open by hand.
Processed files move to data/inbox/done.
"""
import argparse
import os
import smtplib
import time
from email.message import EmailMessage

from . import config, run


def email(data, src):
    k, top = data["kpis"], [a for a in data["alerts"] if a["alert"]][:10]
    msg = EmailMessage()
    msg["Subject"] = f"JournalGuard AI: {k['alerts']} alerts in {src.name} ({k['high']} high)"
    msg["From"] = os.environ.get("JG_SMTP_USER", "journalguard@localhost")
    msg["To"] = os.environ.get("JG_ALERT_TO", "auditor@localhost")
    body = [f"{k['entries']:,} entries tested (100%), {k['alerts']:,} alerts, {k['value_under_review']:,.0f} EUR under review.",
            "", "Top alerts:"] + [f"- {a['id']} | {a['posting_date']} | {a['user']} | {a['amount']:,.2f} EUR | score {a['score']:.0f} | "
                                  f"{'; '.join(a['rules']) or 'models only'}" for a in top]
    body += ["", "Scores prioritise audit attention; they are not proof of fraud. Memos: data/output/memos."]
    msg.set_content("\n".join(body))
    xl = config.OUT_DIR / "JE_audit_alerts.xlsx"
    if xl.exists():
        msg.add_attachment(xl.read_bytes(), maintype="application",
                           subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet", filename=xl.name)
    host = os.environ.get("JG_SMTP_HOST")
    if host and os.environ.get("JG_SMTP_PASSWORD") and os.environ.get("JG_ALERT_TO"):
        with smtplib.SMTP(host, int(os.environ.get("JG_SMTP_PORT", 587))) as s:
            s.starttls()
            s.login(os.environ["JG_SMTP_USER"], os.environ["JG_SMTP_PASSWORD"])
            s.send_message(msg)
        return f"sent to {msg['To']}"
    out = config.OUT_DIR / "alert_email.eml"
    out.write_bytes(bytes(msg))
    return f"saved to {out} (set JG_SMTP_* to send)"


def check_once():
    inbox = config.INBOX_DIR
    inbox.mkdir(parents=True, exist_ok=True)
    done = inbox / "done"
    done.mkdir(exist_ok=True)
    files = [f for f in sorted(inbox.iterdir()) if f.is_file() and f.suffix.lower() in (".csv", ".txt", ".xlsx")]
    for f in files:
        run.log(f"New ledger in the inbox: {f.name}")
        data = run.main(["--input", str(f)])
        run.log("Email " + email(data, f))
        f.rename(done / f.name)
    return len(files)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--every", type=int, default=0, help="minutes between checks (0 = once)")
    a = ap.parse_args(argv)
    while True:
        n = check_once()
        if not a.every:
            print(f"{n} file(s) processed")
            return n
        time.sleep(a.every * 60)


if __name__ == "__main__":
    main()
