"""AI Service: optional drafting assistance over the shared data.

Design rules (agreed with GPHA Internal Audit):
* Off by default; an administrator turns it on and chooses the provider (Configuration > AI).
* Pluggable: Anthropic, Azure OpenAI or any OpenAI-compatible endpoint, including a model hosted on GPHA's
  own server so that audit data never leaves the network.
* Output is always a *draft* returned to the user. Nothing is written to a record until the user accepts it
  through the normal edit screens, so authorship, review and sign-off stay with people (IIA GIAS 4.2, 13.x).
* Personal data (e-mail addresses, phone numbers) is removed before sending when the admin rule is on.
* Every request is logged in ``ai_requests`` and in the audit trail.
"""

from __future__ import annotations

import json
import re

from sqlalchemy.orm import Session

from app.core.appconfig import cfg
from app.core.audit import log_action
from app.core.config import settings
from app.services.ai import providers
from app.services.ai.models import AiRequest
from app.services.ai.providers import AiError, ProviderConfig

FEATURES = {
    "finding_draft": "Draft a finding's condition, criteria, cause, effect and recommendation",
    "report_summary": "Draft an audit report's executive summary from its findings",
    "rcm_suggest": "Suggest risks and controls for an audit objective",
}

SYSTEM = (
    "You assist internal auditors at the Ghana Ports and Harbours Authority (GPHA). Work to the IIA Global "
    "Internal Audit Standards, the Internal Audit Agency Act, 2003 (Act 658) and the Public Financial Management "
    "Act, 2016 (Act 921). Write in clear, formal British English. Use only the facts provided; never invent "
    "figures, names, dates or evidence - where a fact is missing write [to be confirmed]. Your text is a draft "
    "that an auditor will review and edit."
)

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
_PHONE = re.compile(r"(?<!\w)(\+?\d[\d\s-]{7,}\d)(?!\w)")


def provider_config() -> ProviderConfig:
    return ProviderConfig(provider=str(cfg("ai_provider")).strip(), model=str(cfg("ai_model")).strip(),
                          base_url=str(cfg("ai_base_url")).strip(), api_key=settings.ai_api_key or "",
                          timeout=int(cfg("ai_timeout_seconds")))


def status() -> dict:
    conf = provider_config()
    enabled = bool(cfg("ai_enabled"))
    problems = []
    if conf.provider not in providers.PROVIDERS:
        problems.append(f"Unknown provider '{conf.provider}'")
    if conf.provider in ("anthropic", "azure_openai") and not conf.api_key:
        problems.append("GPHA_AI_API_KEY is not set on the server")
    return {
        "enabled": enabled,
        "ready": enabled and not problems,
        "provider": conf.provider,
        "provider_name": providers.PROVIDERS.get(conf.provider, "Unknown"),
        "model": conf.model,
        "endpoint": conf.base_url,
        "api_key_set": bool(conf.api_key),
        "redacts_personal_data": bool(cfg("ai_redact_personal_data")),
        "problems": problems,
        "features": FEATURES,
        "providers": providers.PROVIDERS,
    }


def redact(text: str) -> str:
    if not cfg("ai_redact_personal_data"):
        return text
    return _PHONE.sub("[phone removed]", _EMAIL.sub("[e-mail removed]", text))


def _prepare(prompt: str) -> str:
    return redact(prompt)[: int(cfg("ai_max_input_chars"))]


def _json_block(text: str):  # noqa: ANN202
    """Parse the first JSON object/array in the model's answer."""
    match = re.search(r"(\{.*\}|\[.*\])", text, re.S)
    if not match:
        raise AiError("The AI answer did not contain the expected structure; try again")
    try:
        return json.loads(match.group(1))
    except ValueError:
        raise AiError("The AI answer could not be read; try again") from None


def run(db: Session, *, user, feature: str, prompt: str, record_type: str | None, record_id: int | None,  # noqa: ANN001
        request=None) -> str:  # noqa: ANN001
    """Send one prompt; log it; return the raw text. Raises AiError (logged) on failure."""
    if not cfg("ai_enabled"):
        raise AiError("AI assistance is turned off. An administrator can turn it on under Configuration > AI.")
    conf = provider_config()
    text = _prepare(prompt)
    entry = AiRequest(user_id=user.id, feature=feature, record_type=record_type, record_id=record_id,
                      provider=conf.provider[:40], model=conf.model[:120], input_chars=len(text), status="ok")
    try:
        answer = providers.complete(conf, SYSTEM, text)
        if not answer:
            raise AiError("The AI provider returned an empty answer")
        entry.output_chars = len(answer)
        return answer
    except AiError as exc:
        entry.status = "error"
        entry.error = str(exc)[:1000]
        raise
    finally:
        db.add(entry)
        log_action(db, user_id=user.id,
                   action=f"AI_{feature.upper()} {record_type or ''}={record_id or ''} status={entry.status}",
                   request=request)
        db.commit()


# ---------------------------------------------------------------- feature prompts

FINDING_FIELDS = ("condition", "criteria", "cause", "effect", "recommendation")


def finding_prompt(finding, audit, notes: str) -> str:  # noqa: ANN001
    current = "\n".join(f"{f.title()}: {getattr(finding, f) or ''}" for f in FINDING_FIELDS)
    return (
        f"Audit: {audit.title}\nScope: {audit.scope}\n\nFinding title: {finding.title}\n"
        f"Risk rating: {getattr(finding.risk_rating, 'value', finding.risk_rating)}\n"
        f"Description: {finding.description}\n{current}\n\nAuditor's notes:\n{notes}\n\n"
        "Draft the finding in the 5C structure. Answer ONLY with a JSON object with the keys condition, criteria, "
        "cause, effect and recommendation (strings). The recommendation must be specific, actionable and address "
        "the cause."
    )


def parse_finding(text: str) -> dict:
    data = _json_block(text)
    if not isinstance(data, dict):
        raise AiError("The AI answer did not contain the expected structure; try again")
    return {f: str(data.get(f) or "").strip() for f in FINDING_FIELDS}


def report_prompt(report, audit, findings: list) -> str:  # noqa: ANN001
    lines = [f"- [{getattr(f.risk_rating, 'value', f.risk_rating)}] {f.title}: {f.condition or f.description}"
             for f in findings]
    return (
        f"Audit: {audit.title}\nScope and objectives: {report.scope_objectives or audit.scope}\n"
        f"Overall rating: {getattr(report.overall_rating, 'value', report.overall_rating) or '[to be confirmed]'}\n"
        f"Findings:\n" + ("\n".join(lines) or "- none recorded") + "\n\n"
        "Draft an executive summary for the Director-General and the Audit Committee (150-250 words): purpose and "
        "scope, overall conclusion, the most significant findings and the key actions. Plain text only."
    )


def rcm_prompt(objective, audit) -> str:  # noqa: ANN001
    existing = "\n".join(f"- {r.title}" for r in objective.risks) or "- none yet"
    return (
        f"Audit: {audit.title}\nScope: {audit.scope}\nObjective: {objective.title}\n{objective.description}\n"
        f"Risks already recorded:\n{existing}\n\n"
        "Suggest up to 5 further risks to this objective, each with likelihood and impact (1-5) and up to 3 key "
        "controls. Answer ONLY with a JSON array of objects: {\"risk\": str, \"description\": str, "
        "\"likelihood\": int, \"impact\": int, \"controls\": [str]}."
    )


def parse_rcm(text: str) -> list[dict]:
    data = _json_block(text)
    if isinstance(data, dict):
        data = data.get("risks") or []
    out = []
    for item in data[:5] if isinstance(data, list) else []:
        if not isinstance(item, dict) or not str(item.get("risk") or "").strip():
            continue

        def score(v) -> int:  # noqa: ANN001
            try:
                return min(5, max(1, int(v)))
            except (TypeError, ValueError):
                return 3

        out.append({"risk": str(item["risk"]).strip()[:255], "description": str(item.get("description") or ""),
                    "likelihood": score(item.get("likelihood")), "impact": score(item.get("impact")),
                    "controls": [str(c).strip()[:255] for c in (item.get("controls") or []) if str(c).strip()][:3]})
    if not out:
        raise AiError("The AI answer did not contain any usable risks; try again")
    return out
