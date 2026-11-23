"""Live service wiring and the JSON-reply helper used by every LLM step.

Services.live() builds real clients from config. Tests construct Services(...) with fakes; runtime
code never substitutes a fake for an off service, it raises config.Blocked instead.
"""
import json
import re

import clients
import config


class Services:
    def __init__(self, llm=None, cognee=None, senso=None, llm_backend=None):
        self._llm = llm
        self.cognee = cognee
        self.senso = senso
        self.llm_backend = llm_backend

    @classmethod
    def live(cls, need=("llm", "senso", "cognee")):
        for s in need:
            config.require(s)
        return cls(llm=clients.llm_chat if config.mode("llm") == "live" else None,
                   cognee=clients.CogneeLive() if config.mode("cognee") == "live" else None,
                   senso=clients.SensoLive() if config.mode("senso") == "live" else None,
                   llm_backend=config.llm_backend())

    def llm(self, messages, **kw):
        if self._llm is None:
            config.require("llm")
        return self._llm(messages, **kw)


class InvalidReply(ValueError):
    pass


def extract_json(text):
    """First JSON object in an LLM reply (fenced or bare)."""
    text = text or ""
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    candidates = [fence.group(1)] if fence else []
    start = text.find("{")
    if start >= 0:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    candidates.append(text[start:i + 1])
                    break
    for c in candidates:
        try:
            obj = json.loads(c)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            continue
    raise InvalidReply("reply contained no JSON object")


def ask_json(services, messages, check=None, retries=1, **kw):
    """Ask for a JSON object; `check(obj)` raises ValueError on a bad object. One corrective retry."""
    msgs = list(messages)
    last = None
    for _ in range(retries + 1):
        text = services.llm(msgs, **kw)
        try:
            obj = extract_json(text)
            if check:
                check(obj)
            return obj
        except ValueError as e:
            last = e
            msgs = msgs + [{"role": "assistant", "content": (text or "")[:2000]},
                           {"role": "user", "content": f"That reply was not usable: {str(e)[:300]}. Reply again with only the corrected JSON object."}]
    raise InvalidReply(str(last))
