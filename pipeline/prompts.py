"""
prompts.py - PROMPT LIBRARY (deliverable for the Demo slide).

Each prompt = SYSTEM prompt (how the AI behaves) + USER prompt (context + question).
Rule for every prompt: the LLM EXPLAINS numbers our models computed. It never scores,
never invents facts, and only uses the data given in the prompt.
Version the prompts here; note what changed and why in PROMPT_LOG.
"""

PROMPT_VERSION = "v2"
PROMPT_LOG = [
    "v1 - auditor persona, JSON output, French audit vocabulary (FEC/PCG sample data).",
    "v2 - adapted to the DIB general ledger (SKR03 accounts, entry timestamps, users); memo now uses "
    "both the rules triggered and the SHAP drivers; added the assertion at risk and the NEP 240 / ISA 240 link.",
]

SYSTEM_AUDITOR = """You are a senior external auditor applying NEP 240 / ISA 240
(the auditor's responsibilities relating to fraud), which require testing the appropriateness
of journal entries and other adjustments.
You review journal entries that our risk models flagged.

Strict rules:
- Use ONLY the facts in the user message. Never invent amounts, dates, people, documents or reasons.
- The risk score, the rules triggered and the SHAP drivers were computed by our models.
  Do not change them; explain them in plain business language.
- Write for an audit manager: factual, short, concrete. Write in {language}.
- If the facts are not enough to conclude, say so and list the evidence to obtain.
- Answer ONLY with valid JSON, no text before or after."""

USER_MEMO = """Write an audit memo for this flagged journal entry.

ENTRY
- Entry id: {entry_id} ({source} entry, nature: {nature})
- Posting date: {posting_date} ({weekday}) | Entered: {entered_at} ({delay} days later, at {hour}:00)
- Description: "{text}"
- Accounts: {accounts} (main account {main_account} {main_account_name})
- Amount: {amount:,.2f} EUR | Posted by: {user}

MODEL RESULT
- Risk score: {risk_score}/100
- Red-flag rules triggered: {rules}
- Main drivers of the ML prediction (SHAP, largest first): {shap}

CONTEXT
- Approval threshold: {threshold:,.0f} EUR | Performance materiality: {perf_mat:,.0f} EUR

Return JSON with exactly these keys:
{{
  "risk_level": "High" | "Medium" | "Low",
  "why_suspicious": "2-3 sentences linking each red flag to an audit risk",
  "possible_explanations": ["legitimate reasons that could explain it"],
  "follow_up_procedures": ["3-5 concrete audit procedures"],
  "assertion_at_risk": "e.g. occurrence, cut-off, accuracy, completeness",
  "conclusion": "one sentence"
}}"""

USER_NATURE = """Classify the nature of this journal entry from its description and accounts.
Description: "{text}" | Accounts: {accounts}
Return JSON: {{"nature": one of ["purchase", "sale", "payment", "payroll", "accrual", "deferral",
"reversal", "credit note", "adjustment", "other"], "confidence": "high"|"medium"|"low"}}"""

USER_SUMMARY = """Write the engagement summary for the audit working papers.

FACTS (computed by our models - use only these):
- Ledger: {ledger}
- Entries tested: {n_entries} (100% of the ledger), of which manual: {n_manual}
- Alerts (risk score >= {cutoff}): {n_alerts}
- Alerts by parameter: {by_param}
- Alerts by red flag: {by_rule}
- Demo anomalies injected: {n_injected}; found: {found}
- Revenue forecast: months outside the expected band: {forecast_flags}
- Top 5 alerts: {top5}

Return JSON:
{{
  "overview": "3-4 sentences",
  "key_themes": ["recurring patterns seen across the alerts"],
  "recommended_next_steps": ["3-5 steps"],
  "limitations": ["limits of this analysis the reader must know"]
}}"""

LIBRARY = [
    {"name": "System - auditor persona", "role": "system", "used_for": "every call", "text": SYSTEM_AUDITOR},
    {"name": "Audit memo per alert", "role": "user", "used_for": "Recommendation / reporting", "text": USER_MEMO},
    {"name": "Entry nature classification", "role": "user", "used_for": "Data enrichment", "text": USER_NATURE},
    {"name": "Engagement summary", "role": "user", "used_for": "Analysis / reporting", "text": USER_SUMMARY},
]
