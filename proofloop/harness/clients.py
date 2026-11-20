"""Sponsor clients. Each has a live implementation and a stub with the same
return shape. Endpoints are the ones named in the spec; request/response field
names that the spec does not pin down are marked UNVERIFIED and parsed
tolerantly. Verify them against the sponsor docs once keys are available.
"""
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

import config
from atomic import atomic_write_json

TIMEOUT = 15
# Python's default urllib User-Agent is blocked by Cloudflare (Senso returns 403 "error code: 1010").
USER_AGENT = "proofloop-harness/0.1 (+https://github.com/arii/boomtick)"


class ApiError(Exception):
    def __init__(self, status, body):
        super().__init__(f"HTTP {status}: {str(body)[:200]}")
        self.status = status
        self.body = body


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


def _load(path, default):
    p = Path(path)
    return json.loads(p.read_text()) if p.exists() else default


def _save(path, obj):
    atomic_write_json(path, obj)


def _tokens(text):
    return set(re.findall(r"[a-z0-9]+", text.lower()))


# ---------------------------------------------------------------- Cognee
class CogneeStub:
    """Local graph built from session constraints (cognee_stub.json)."""
    label = "Cognee stub (local graph) - live Cognee pending"

    def __init__(self):
        self.path = config.STATE_DIR / "cognee_stub.json"

    def ingest(self, sessions, extra_docs=()):
        nodes, edges = [], []
        constraints = {}
        for s in sessions:
            sid = s["session_id"]
            nodes.append({"id": sid, "type": "session", "text": f'{s["query_or_task"]} {s["outcome_or_error"]}'})
            cid = "constraint:" + re.sub(r"\W+", "_", s["constraint"].lower())[:60]
            if cid not in constraints:
                constraints[cid] = {"id": cid, "type": "constraint", "text": s["constraint"]}
            edges.append({"from": sid, "to": cid, "rel": "learned_constraint"})
        nodes += list(constraints.values())
        for name, text in extra_docs:
            nodes.append({"id": f"skill:{name}", "type": "local_skill", "text": text[:2000]})
        _save(self.path, {"nodes": nodes, "edges": edges})
        return {"nodes": len(nodes), "edges": len(edges)}

    def search(self, query):
        g = _load(self.path, {"nodes": [], "edges": []})
        q = _tokens(query)
        hits = []
        for n in g["nodes"]:
            score = len(q & _tokens(n["text"]))
            if score:
                hits.append((score, n))
        hits.sort(key=lambda x: -x[0])
        out = []
        for _, n in hits:
            if n["type"] == "constraint":
                srcs = [e["from"] for e in g["edges"] if e["to"] == n["id"]]
                out.append({"type": "constraint", "text": n["text"], "session_ids": srcs})
            elif n["type"] == "session":
                out.append({"type": "session", "session_id": n["id"], "text": n["text"]})
        return out


class CogneeLive:
    """Cognee HTTP API (docs.cognee.ai/cognee-cloud/http-api).
    Cloud auth: X-Api-Key (+ X-Tenant-Id if COGNEE_TENANT_ID set). Self-hosted with auth: Bearer.
    add = multipart (datasetName + repeated raw_data); cognify = JSON {"datasets": [...]};
    search = JSON {"query", "search_type"}. We use add + cognify (remember is the combined call)."""
    label = "Cognee (enabled; live execution requires evidence)"
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


def cognee():
    return CogneeLive() if config.mode("cognee") == "live" else CogneeStub()


# ---------------------------------------------------------------- Senso
class SensoStub:
    """JSON file store mimicking POST /kb/raw, GET /kb/nodes/{id}, POST /search."""
    label = "Senso (local stub - live API pending key)"

    def __init__(self):
        self.path = config.STATE_DIR / "senso_stub.json"

    def _db(self):
        return _load(self.path, {"nodes": {}})

    def health(self):
        return {"status": 200, "org": "local-stub"}

    def post_raw(self, title, text, version):
        db = self._db()
        if any(n["text"] == text for n in db["nodes"].values()):
            raise ApiError(409, "conflict: same text already stored")
        nid = f"stub-node-{len(db['nodes']) + 1:04d}"
        db["nodes"][nid] = {"id": nid, "title": title, "text": text, "version": version}
        _save(self.path, db)
        return 202, {"id": nid, "kb_node_id": nid, "processing_status": "processing"}

    def get_node(self, nid):
        n = self._db()["nodes"][nid]
        return {"kb_node_id": nid, "name": n["title"], "content": {"processing_status": "complete"}}

    def search(self, query):
        q = _tokens(query)
        res = []
        for n in self._db()["nodes"].values():
            s = len(q & _tokens(n["title"] + " " + n["text"]))
            if s:
                res.append((s, {"content_id": n["id"], "title": n["title"]}))
        res.sort(key=lambda x: -x[0])
        return [r for _, r in res]


class SensoLive:
    """Senso API (docs.senso.ai quickstart): base https://apiv2.senso.ai, header X-API-Key.
    POST /org/kb/raw {title,text} -> 202 {id, kb_node_id}; poll GET /org/kb/nodes/{kb_node_id}
    until content.processing_status == complete; POST /org/search -> results[].content_id == id.
    Identical text returns 409, so promoted text always carries version, cycle and timestamp."""
    label = "Senso (enabled; live execution requires evidence)"

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
        return [{"content_id": r.get("content_id"), "title": r.get("title", "")} for r in b.get("results", [])]


def senso():
    return SensoLive() if config.mode("senso") == "live" else SensoStub()


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
        time.sleep(0 if config.mode("senso") == "stub" else float(config.get("SENSO_POLL_S", "5")))
    else:
        raise ApiError(0, f"node {nid} not complete after {max_polls} polls")
    hits = client.search(title)
    if not any(h.get("content_id") == content_id for h in hits):
        raise ApiError(0, "promotion search readback did not find uploaded content; active skill unchanged")
    return {"node_id": nid, "verified": True, "mode": config.mode("senso")}


# ---------------------------------------------------------------- LLM
def _mutation_prompt(failures, known_steps, current_steps):
    # Only check names, failure counts and step ids: no session text, URLs or personal data.
    return ("A skill is an ordered list of step ids. Known step ids and meanings: "
            + json.dumps(known_steps) + ". Current steps: " + json.dumps(current_steps)
            + ". Replay failures (check -> count): " + json.dumps(failures)
            + '. Reply with JSON only: {"add": ["step_id", ...]} using known ids not already present.')


def llm_chat(prompt, max_tokens=400):
    """One chat completion through the active backend (config.llm_backend()). Returns text.
    twt: local Tokens with Taste gateway (OpenAI-compatible, loopback, no key; it holds provider keys).
    openrouter: OpenRouter with OPENROUTER_API_KEY."""
    backend = config.llm_backend()
    messages = [{"role": "user", "content": prompt}]
    if backend == "twt":
        url = f"{config.twt_base_url()}/chat/completions"
        headers = {"X-Session-Id": "proofloop-mutation"}
        body = {"model": "default", "messages": messages, "max_tokens": max_tokens}
        timeout = 90  # waterfall may try several providers
    elif backend == "openrouter":
        url = f"{config.base_url('openrouter')}/api/v1/chat/completions"
        headers = {"Authorization": f"Bearer {config.get('OPENROUTER_API_KEY')}"}
        body = {"model": config.get("OPENROUTER_MODEL", config.DEFAULT_LLM_MODEL),
                "messages": messages, "max_tokens": max_tokens}
        timeout = 60
    else:
        raise ApiError(0, "no LLM backend enabled")
    _, res = http_json("POST", url, headers, body, timeout=timeout, retries=0 if backend == "twt" else 1)
    return (res["choices"][0]["message"].get("content") or "") if res.get("choices") else None


def llm_propose_steps(failures, known_steps, current_steps):
    """Ask the active LLM backend for step ids to add. Returns list or raises ApiError."""
    content = llm_chat(_mutation_prompt(failures, known_steps, current_steps)) or ""
    m = re.search(r"\{.*\}", content, re.S)
    try:
        add = json.loads(m.group(0)).get("add", []) if m else []
    except json.JSONDecodeError:
        add = []
    return [a for a in add if a in known_steps and a not in current_steps]
