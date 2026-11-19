"""
prompts.py - PROMPT LIBRARY (deliverable for the Demo slide).

Each prompt = SYSTEM prompt (how the AI behaves) + USER prompt (context + question).
The LLM EXPLAINS numbers our models computed. It never scores, never invents facts,
and only uses the data given in the prompt. Version the prompts here (PROMPT_LOG).
"""

PROMPT_VERSION = "v3"
PROMPT_LOG = [
    "v1 - auditor persona, JSON output, French audit vocabulary (FEC/PCG sample data).",
    "v2 - adapted to the DIB general ledger (SKR03 accounts, entry timestamps, users); memo uses the rules "
    "triggered and the SHAP drivers; added the assertion at risk and the NEP 240 / ISA 240 link.",
    "v3 - merged Person 3's safeguards (no fraud claims, distinguish facts / scores / indicators / items to verify, "
    "leave the auditor's conclusion blank); memo grounded in Person 3's recommendation library; "
    "added the 'ask the alerts' prompt for natural-language questions.",
]

SYSTEM_AUDITOR = """You are an audit documentation assistant supporting a human external auditor
applying NEP 240 / ISA 240 (testing the appropriateness of journal entries and other adjustments).

Strict rules:
- Use ONLY the facts and audit recommendations supplied in the user message.
  Never invent dates, amounts, account names, approvals, documents, explanations or evidence.
- Do not claim or imply that fraud, theft, misconduct or management override occurred.
- Distinguish clearly between (1) facts in the ledger, (2) model screening scores,
  (3) rule-based indicators and (4) matters that still require auditor verification.
- A risk score is a prioritisation indicator, NOT a probability of fraud and NOT proof.
  Do not change, reinterpret or recalculate it.
- If no driver is identified, say that the specific driver is not identified.
- Neutral, concise, professional audit language. Write in {language}.
- Leave the auditor's conclusion and sign-off for human completion.
- Answer ONLY with valid JSON, no text before or after."""

USER_MEMO = """Draft an audit working-paper memo for this flagged journal entry.

ENTRY (facts from the ledger)
- Entry id: {entry_id} ({source} entry, nature: {nature})
- Posting date: {posting_date} ({weekday}) | Entered: {entered_at} ({delay} days later{hour_text})
- Description: "{text}"
- Accounts: {accounts} (main account {main_account} {main_account_name})
- Amount: {amount:,.2f} EUR | Posted by: {user}

SCREENING RESULT (computed by models - do not change)
- Risk score: {risk_score}/100 ({risk_level})
- Red-flag rules triggered: {rules}
- Main drivers of the ML prediction (SHAP, largest first): {shap}
- Person 2 model score: {p2}

AUDIT LIBRARY (Person 3) - procedures supported by the indicators above
{library}

CONTEXT
- Approval threshold: {threshold:,.0f} EUR | Performance materiality: {perf_mat:,.0f} EUR

Return JSON with exactly these keys:
{{
  "risk_level": "High" | "Medium" | "Low",
  "why_suspicious": "2-3 sentences linking each indicator to an audit risk, without claiming fraud",
  "possible_explanations": ["legitimate reasons that could explain it"],
  "evidence_to_obtain": ["documents to request, from the library"],
  "follow_up_procedures": ["3-5 concrete audit procedures, from the library"],
  "assertion_at_risk": "e.g. occurrence, cut-off, accuracy, completeness",
  "auditor_conclusion": ""
}}"""

USER_NATURE = """Classify the nature of this journal entry from its description and accounts.
Description: "{text}" | Accounts: {accounts}
Return JSON: {{"nature": one of ["purchase", "sale", "payment", "payroll", "accrual", "deferral",
"reversal", "credit note", "adjustment", "other"], "confidence": "high"|"medium"|"low"}}"""

USER_SUMMARY = """Write the engagement summary for the audit working papers.

FACTS (computed by our models - use only these):
- Ledger: {ledger}
- Entries tested: {n_entries} (100% of the ledger), of which manual: {n_manual}
- Alerts (risk score >= {cutoff}): {n_alerts}; value under review: {value_under_review} EUR (not a loss estimate)
- Alerts by theme: {themes}
- Ground truth: {ground_truth}
- Revenue forecast: months outside the expected band: {forecast_flags}
- Top 5 alerts: {top5}

Return JSON:
{{
  "overview": "3-4 sentences",
  "key_themes": ["recurring patterns seen across the alerts"],
  "recommended_next_steps": ["3-5 steps"],
  "limitations": ["limits of this analysis the reader must know"]
}}"""

USER_ASK = """Answer the auditor's question using ONLY the alert table below (one row per flagged entry).
If the table does not contain the answer, say so. Quote entry ids when you refer to entries.

QUESTION: {question}

ALERT TABLE (CSV):
{table}

Return JSON: {{"answer": "2-5 sentences", "entry_ids": ["ids you refer to"]}}"""

LIBRARY = [
    {"name": "System - auditor persona", "role": "system", "used_for": "every call", "text": SYSTEM_AUDITOR},
    {"name": "Audit memo per alert", "role": "user", "used_for": "Recommendation / reporting", "text": USER_MEMO},
    {"name": "Entry nature classification", "role": "user", "used_for": "Data enrichment", "text": USER_NATURE},
    {"name": "Engagement summary", "role": "user", "used_for": "Analysis / reporting", "text": USER_SUMMARY},
    {"name": "Ask the alerts", "role": "user", "used_for": "Natural-language querying", "text": USER_ASK},
]
