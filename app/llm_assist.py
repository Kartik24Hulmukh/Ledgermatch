"""OPTIONAL LLM assist for unmatched deposits. OFF by default.

Honest scope: the deterministic engine is complete without this module. When
LLM_API_KEY is set (any OpenAI-compatible endpoint, e.g. a Zyloo/Kimi K3 or
OpenAI base URL), unmatched deposits are sent for advisory suggestions only.
Sends ONLY: the flagged deposit's date/description/amount and up to 15 candidate
open invoices. Suggested invoice numbers are validated against the candidate
set - the model can never invent an invoice. Failures never crash a run.
This adapter has NOT been tested against a live endpoint from this sandbox
(no network/API key available at build time) - test with your own key.
"""
from __future__ import annotations

import json
import os
import urllib.request

DEFAULT_BASE = "https://api.openai.com/v1"

SYSTEM = (
    "You reconcile bank deposits against open invoices for a bookkeeper. "
    "Given one deposit and candidate open invoices, reply with strict JSON only: "
    '{"invoice_nos": ["..."], "confidence": 0.0, "reasoning": "..."}. '
    "Selected invoice amounts should plausibly sum to the deposit amount. "
    'If unsure, return {"invoice_nos": []}. Never invent invoice numbers.')


def enabled() -> bool:
    return bool(os.environ.get("LLM_API_KEY"))


def suggest(txn, candidates, timeout: int = 45) -> dict:
    key = os.environ.get("LLM_API_KEY")
    if not key:
        return {"txn_id": txn.id, "error": "LLM assist disabled (no LLM_API_KEY set)"}
    base = os.environ.get("LLM_BASE_URL", DEFAULT_BASE).rstrip("/")
    model = os.environ.get("LLM_MODEL", "kimi-k3")
    cand = [{"invoice_no": i.invoice_no, "customer": i.customer,
             "date": i.date.isoformat(), "amount": str(i.amount)}
            for i in candidates[:15]]
    user = json.dumps({
        "deposit": {"date": txn.date.isoformat(), "description": txn.description,
                    "amount": str(txn.amount)},
        "open_invoices": cand,
    })
    payload = {"model": model, "temperature": 0,
               "messages": [{"role": "system", "content": SYSTEM},
                            {"role": "user", "content": user}]}
    req = urllib.request.Request(
        base + "/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
        text = data["choices"][0]["message"]["content"]
        start, end = text.find("{"), text.rfind("}")
        parsed = json.loads(text[start:end + 1])
        valid = {c["invoice_no"] for c in cand}
        nos = [n for n in parsed.get("invoice_nos", []) if n in valid]
        return {"txn_id": txn.id, "ai_suggestion": True, "invoice_nos": nos,
                "reasoning": str(parsed.get("reasoning", ""))[:500],
                "note": "AI suggestion - verify before applying."}
    except Exception as exc:  # network, auth, parse - degrade gracefully
        return {"txn_id": txn.id, "error": f"LLM assist failed: {type(exc).__name__}"}
