"""Live clients for Cognee, Senso and the LLM backends. There are no stubs here: tests inject fakes.

Request and response field names that the sponsor docs do not pin down are marked UNVERIFIED and
parsed tolerantly. Error messages pass through _redact_secrets so key values never reach logs.
"""
import json
import re
import time
import urllib.error
import urllib.request

import config

TIMEOUT = 15
# Python's default urllib User-Agent is blocked by Cloudflare (Senso returns 403 "error code: 1010").
USER_AGENT = "proofloop-harness/0.1 (+https://github.com/arii/boomtick)"


class ApiError(Exception):
    def __init__(self, status, body):
        self.status = status
        self.body = _redact_secrets(body)[:500]
        super().__init__(f"HTTP {status}: {self.body[:200]}")


def http_json(method, url, headers=None, body=None, timeout=TIMEOUT, retries=1):
    data = json.dumps(body).encode() if body is not None else None
    h = {"Content-Type": "application/json", "User-Agent": USER_AGENT, **(headers or {})}
    last = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, data=data, headers=h, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read().decode() or "{}"
                return r.status, json.loads(raw)
        except urllib.error.HTTPError as e:
            raw = e.read().decode()
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                parsed = {"raw": raw}
            if e.code >= 500 and attempt < retries:
                last = ApiError(e.code, parsed)
                time.sleep(1)
                continue
            raise ApiError(e.code, parsed)
        except (urllib.error.URLError, TimeoutError) as e:
            last = ApiError(0, str(e))
            if attempt < retries:
                time.sleep(1)
                continue
            raise last
    raise last


def _redact_secrets(text):
    """Remove configured key values from text that may end up in logs or exceptions (S3)."""
    text = str(text)
    for k in config.KEY_NAMES:
        v = config.get(k)
        if v and len(v) >= 8:
            text = text.replace(v, "[REDACTED]")
    return re.sub(r"(?i)(bearer\s+|x-api-key[\"':\s]+)[A-Za-z0-9._-]{12,}", r"\1[REDACTED]", text)


# ---------------------------------------------------------------- Cognee
class CogneeLive:
    """Cognee HTTP API (docs.cognee.ai/cognee-cloud/http-api).
    Cloud auth: X-Api-Key (+ X-Tenant-Id if COGNEE_TENANT_ID set). Self-hosted with auth: Bearer.
    add = multipart (datasetName + repeated raw_data); cognify = JSON {"datasets": [...]};
    search = JSON {"query", "search_type"}. We use add + cognify (remember is the combined call)."""
    label = "Cognee (live)"
    DATASET = "proofloop_sessions"

    def __init__(self):
        self.base = config.base_url("cognee")
        key = config.get("COGNEE_API_KEY")
        tenant = config.get("COGNEE_TENANT_ID")
        self.headers = {}
        if key and tenant:
            self.headers = {"X-Api-Key": key, "X-Tenant-Id": tenant}
        elif key:
            self.headers = {"X-Api-Key": key} if "cognee.ai" in self.base else {"Authorization": f"Bearer {key}"}

    def _post_json(self, path, body):
        return http_json("POST", f"{self.base}{path}", self.headers, body, timeout=120)[1]

    def _post_multipart(self, path, fields, files=()):
        """fields: (name, value) form fields. files: (field, filename, text) uploads."""
        boundary = "----proofloop" + str(int(time.time() * 1000))
        body = b""
        for name, value in fields:
            body += f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
        for name, filename, text in files:
            body += (f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
                     f'Content-Type: text/plain\r\n\r\n').encode() + text.encode() + b"\r\n"
        body += f"--{boundary}--\r\n".encode()
        req = urllib.request.Request(f"{self.base}{path}", data=body, method="POST",
                                     headers={"User-Agent": USER_AGENT, **self.headers, "Content-Type": f"multipart/form-data; boundary={boundary}"})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read().decode() or "{}")
        except urllib.error.HTTPError as e:
            raise ApiError(e.code, e.read().decode())
        except (urllib.error.URLError, TimeoutError) as e:
            raise ApiError(0, str(e))

    def ingest(self, sessions, extra_docs=()):
        # Cognee ignores plain form fields; each item must be a file upload under "data".
        files = [("data", f"session_{i}.txt", json.dumps(s)) for i, s in enumerate(sessions)]
        files += [("data", f"doc_{i}.txt", t[:4000]) for i, (_, t) in enumerate(extra_docs)]
        res = self._post_multipart("/api/v1/add", [("datasetName", self.DATASET)], files)
        if not res.get("data_ingestion_info") and not res.get("data_ids"):
            raise ApiError(0, f"Cognee stored no data: {str(res)[:300]}")
        self._post_json("/api/v1/cognify", {"datasets": [self.DATASET]})
        # cognify runs in the background: wait until the dataset is searchable (max ~120 s).
        deadline = time.time() + 120
        while True:
            try:
                self.search("ready")
                break
            except ApiError as e:
                if e.status != 404 or time.time() > deadline:
                    raise
                time.sleep(5)
        return {"added": len(files)}

    def search(self, query):
        # CHUNKS returns raw passages, which contain the session JSON (we regex the session ids out).
        res = self._post_json("/api/v1/search", {"query": query, "search_type": "CHUNKS", "datasets": [self.DATASET]})
        items = res if isinstance(res, list) else res.get("results", [])
        out = []
        for it in items:
            text = it if isinstance(it, str) else json.dumps(it)
            sids = re.findall(r"sess_\d{4}_\d{2}_\d{2}_[a-z0-9_]+", text)
            out.append({"type": "constraint", "text": text[:300], "session_ids": sorted(set(sids))})
        return out


class SensoLive:
    """Senso API (docs.senso.ai quickstart): base https://apiv2.senso.ai, header X-API-Key.
    POST /org/kb/raw {title,text} -> 202 {id, kb_node_id}; poll GET /org/kb/nodes/{kb_node_id}
    until content.processing_status == complete; POST /org/search -> results[].content_id == id.
    Identical text returns 409, so promoted text always carries version, cycle and timestamp."""
    label = "Senso (live)"

    def __init__(self):
        self.base = config.base_url("senso") + "/api/v1"
        self.headers = {"X-API-Key": config.get("SENSO_API_KEY")}

    def health(self):
        s, b = http_json("GET", f"{self.base}/org/me", self.headers)
        return {"status": s, "org": b}

    def post_raw(self, title, text, version):
        s, b = http_json("POST", f"{self.base}/org/kb/raw", self.headers, {"title": title, "text": text})
        return s, {"id": b.get("id"), "kb_node_id": b.get("kb_node_id")}

    def get_node(self, nid):
        return http_json("GET", f"{self.base}/org/kb/nodes/{nid}", self.headers)[1]

    def search(self, query):
        b = http_json("POST", f"{self.base}/org/search", self.headers, {"query": query})[1]
        return [{"content_id": r.get("content_id"), "title": r.get("title", ""),
                 "text": r.get("chunk_text") or r.get("text") or r.get("content") or ""}
                for r in b.get("results", [])]

    def read_text(self, node_id):
        """Text of a KB node. UNVERIFIED field names: tries content.text, content.raw_text, text, raw."""
        node = self.get_node(node_id)
        content = node.get("content") or {}
        for v in (content.get("text"), content.get("raw_text"), content.get("raw"), node.get("text"), node.get("raw")):
            if isinstance(v, str) and v.strip():
                return v
        raise ApiError(0, f"node {node_id} returned no text field (keys: {sorted(content) or sorted(node)})")


def senso_promote(client, title, text, version, poll_s=None, max_polls=24):
    """POST raw (expect 202) -> poll kb node until complete -> verify via search."""
    status, body = client.post_raw(title, text, version)
    if status != 202:
        raise ApiError(status, body)
    content_id, nid = body.get("id"), body.get("kb_node_id")
    if not content_id or not nid:
        raise ApiError(0, "promotion response missing content/node id")
    for _ in range(max_polls):
        node = client.get_node(nid)
        st = (node.get("content") or {}).get("processing_status")
        if st == "complete":
            break
        if st == "failed":
            raise ApiError(0, f"node {nid} processing failed: {node}")
        time.sleep(poll_s if poll_s is not None else float(config.get("SENSO_POLL_S", "5")))
    else:
        raise ApiError(0, f"node {nid} not complete after {max_polls} polls")
    hits = client.search(title)
    if not any(h.get("content_id") == content_id for h in hits):
        raise ApiError(0, "promotion search readback did not find uploaded content; active skill unchanged")
    return {"node_id": nid, "content_id": content_id, "verified": True}


# ---------------------------------------------------------------- LLM
def llm_chat(messages, max_tokens=600, temperature=0.2, session="proofloop"):
    """One chat completion through the active backend (config.llm_backend()). Returns text.
    twt: local Tokens with Taste gateway (OpenAI-compatible, loopback, no key; it holds provider keys).
    openrouter: OpenRouter with OPENROUTER_API_KEY. Raises config.Blocked when no backend is enabled."""
    if isinstance(messages, str):
        messages = [{"role": "user", "content": messages}]
    backend = config.llm_backend()
    if backend == "twt":
        url = f"{config.twt_base_url()}/chat/completions"
        headers = {"X-Session-Id": session}
        body = {"model": config.get("TWT_MODEL", "default"), "messages": messages, "max_tokens": max_tokens, "temperature": temperature}
        timeout = 120  # the waterfall may try several providers
    elif backend == "openrouter":
        url = f"{config.base_url('openrouter')}/api/v1/chat/completions"
        headers = {"Authorization": f"Bearer {config.get('OPENROUTER_API_KEY')}"}
        body = {"model": config.get("OPENROUTER_MODEL", config.DEFAULT_LLM_MODEL), "messages": messages,
                "max_tokens": max_tokens, "temperature": temperature}
        timeout = 90
    else:
        config.require("llm")
    _, res = http_json("POST", url, headers, body, timeout=timeout, retries=0 if backend == "twt" else 1)
    if not res.get("choices"):
        raise ApiError(0, "completion response missing choices")
    return res["choices"][0]["message"].get("content") or ""
