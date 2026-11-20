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

TIMEOUT = 15


class ApiError(Exception):
    def __init__(self, status, body):
        super().__init__(f"HTTP {status}: {str(body)[:200]}")
        self.status = status
        self.body = body


def http_json(method, url, headers=None, body=None, timeout=TIMEOUT, retries=1):
    data = json.dumps(body).encode() if body is not None else None
    h = {"Content-Type": "application/json", **(headers or {})}
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
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2) + "\n")


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
    """POST /api/v1/remember, /add, /cognify, /search on COGNEE_API_URL.
    Body field names are UNVERIFIED (spec gives endpoints only)."""
    label = "Cognee (live)"

    def __init__(self):
        self.base = config.base_url("cognee")
        key = config.get("COGNEE_API_KEY")
        self.headers = {"Authorization": f"Bearer {key}"} if key else {}

    def _post(self, path, body):
        return http_json("POST", f"{self.base}{path}", self.headers, body, timeout=60)[1]

    def ingest(self, sessions, extra_docs=()):
        for s in sessions:
            self._post("/api/v1/remember", {"data": json.dumps(s)})
        docs = [json.dumps(s) for s in sessions] + [t for _, t in extra_docs]
        self._post("/api/v1/add", {"data": docs})
        self._post("/api/v1/cognify", {})
        return {"remembered": len(sessions)}

    def search(self, query):
        res = self._post("/api/v1/search", {"query": query})
        items = res if isinstance(res, list) else res.get("results", [])
        out = []
        for it in items:
            text = it if isinstance(it, str) else json.dumps(it)
            sids = re.findall(r"sess_\d{4}_\d{2}_\d{2}_[a-z]", text)
            out.append({"type": "constraint", "text": text[:300], "session_ids": sorted(set(sids))})
        return out


def cognee():
    return CogneeLive() if config.mode("cognee") == "live" else CogneeStub()


# ---------------------------------------------------------------- Jev
def jev_stub(state):
    """Deterministic threshold gate. Same output shape as the live gate."""
    base, cand = state["baseline_pass_rate"], state["candidate_pass_rate"]
    total_checks = max(1, state.get("total_checks", 1))
    cp = round(state["constraint_violations_after"] / total_checks, 2)
    if cand < base:
        choice = "reject_and_refine"
    elif cand > base and cp < 0.3:
        choice = "promote"
    else:
        choice = "hold"
    delta = cand - base
    confidence = round(min(0.99, max(0.5, 0.6 + abs(delta) * 0.6 + (0.1 if cp < 0.3 else 0))), 2)
    utility = round(max(0.0, min(1.0, cand - 0.5 * cp * (1 if cand < 1 else 0))), 2)
    return {"model": "jev-stub-threshold-gate", "choice": choice, "confidence": confidence,
            "constraints_prob": cp, "utility_score": utility, "source": "stub"}


def jev_gate(state):
    if config.mode("jev") == "stub":
        return jev_stub(state)
    body = {  # UNVERIFIED field names: spec specifies model, state, typed questions
        "model": config.JEV_MODEL,
        "state": state,
        "questions": [
            {"type": "Choice", "id": "decision", "options": ["promote", "reject_and_refine", "hold"],
             "prompt": "Should this skill mutation be promoted?"},
            {"type": "Score", "id": "confidence", "range": [0, 1], "prompt": "Confidence in the decision."},
            {"type": "Noul", "id": "constraints", "outputs": ["constraints_prob", "utility_score"],
             "prompt": "Probability the mutation violates a stored constraint; utility of the mutation."},
        ],
    }
    headers = {"Authorization": f"Bearer {config.get('TYPESAFE_API_KEY')}"}
    _, res = http_json("POST", f"{config.base_url('jev')}/v1/systemone", headers, body, timeout=15, retries=1)
    return _parse_jev(res)


def _find(obj, key):
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for v in obj.values():
            r = _find(v, key)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = _find(v, key)
            if r is not None:
                return r
    return None


def _parse_jev(res):
    choice = _find(res, "choice") or _find(res, "decision")
    if isinstance(choice, dict):
        choice = choice.get("value") or choice.get("answer")
    if choice not in ("promote", "reject_and_refine", "hold"):
        raise ApiError(200, f"unrecognized Jev response shape: {json.dumps(res)[:200]}")
    num = lambda k: float(_find(res, k) or 0.0)
    return {"model": config.JEV_MODEL, "choice": choice, "confidence": num("confidence"),
            "constraints_prob": num("constraints_prob"), "utility_score": num("utility_score"),
            "source": "live"}


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
        key = f"{title}@{version}"
        if any(n["key"] == key for n in db["nodes"].values()):
            raise ApiError(409, "conflict: duplicate title/version")
        nid = f"stub-node-{len(db['nodes']) + 1:04d}"
        db["nodes"][nid] = {"id": nid, "key": key, "title": title, "text": text, "version": version,
                            "processing_status": "complete"}
        _save(self.path, db)
        return 202, {"id": nid}

    def get_node(self, nid):
        return self._db()["nodes"][nid]

    def search(self, query):
        q = _tokens(query)
        res = []
        for n in self._db()["nodes"].values():
            s = len(q & _tokens(n["title"] + " " + n["text"]))
            if s:
                res.append((s, {"id": n["id"], "title": n["title"], "version": n["version"]}))
        res.sort(key=lambda x: -x[0])
        return [r for _, r in res]


class SensoLive:
    """Endpoints per spec. Body field names are UNVERIFIED."""
    label = "Senso (live)"

    def __init__(self):
        self.base = config.base_url("senso")
        self.headers = {"Authorization": f"Bearer {config.get('SENSO_API_KEY')}"}

    def health(self):
        s, b = http_json("GET", f"{self.base}/api/v1/org/me", self.headers)
        return {"status": s, "org": b}

    def post_raw(self, title, text, version):
        s, b = http_json("POST", f"{self.base}/api/v1/org/kb/raw", self.headers,
                         {"title": title, "text": text, "version": version})
        return s, {"id": b.get("id") or b.get("node_id") or _find(b, "id")}

    def get_node(self, nid):
        return http_json("GET", f"{self.base}/api/v1/org/kb/nodes/{nid}", self.headers)[1]

    def search(self, query):
        b = http_json("POST", f"{self.base}/api/v1/org/search", self.headers, {"query": query})[1]
        items = b if isinstance(b, list) else b.get("results", [])
        return [{"id": i.get("id") or i.get("node_id"), "title": i.get("title", ""), "version": i.get("version", "")}
                for i in items if isinstance(i, dict)]


def senso():
    return SensoLive() if config.mode("senso") == "live" else SensoStub()


def senso_promote(client, title, text, version, poll_s=1.0, max_polls=30):
    """POST raw (expect 202) -> poll until complete -> verify via search."""
    status, body = client.post_raw(title, text, version)
    if status != 202:
        raise ApiError(status, body)
    nid = body["id"]
    for _ in range(max_polls):
        node = client.get_node(nid)
        if node.get("processing_status") == "complete":
            break
        time.sleep(poll_s)
    else:
        raise ApiError(0, f"node {nid} not complete after {max_polls} polls")
    hits = client.search(title)
    verified = any(h.get("id") == nid or h.get("version") == version for h in hits)
    return {"node_id": nid, "verified": verified}


# ---------------------------------------------------------------- LLM
def llm_propose_steps(failures, known_steps, current_steps):
    """Ask OpenRouter for step ids to add. Returns list or raises ApiError."""
    prompt = (
        "A skill is an ordered list of step ids. Known step ids and meanings: "
        + json.dumps(known_steps) + ". Current steps: " + json.dumps(current_steps)
        + ". Replay failures (check -> count): " + json.dumps(failures)
        + '. Reply with JSON only: {"add": ["step_id", ...]} using known ids not already present.')
    body = {"model": "arcee-ai/trinity-large-thinking", "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 200}
    headers = {"Authorization": f"Bearer {config.get('OPENROUTER_API_KEY')}"}
    _, res = http_json("POST", f"{config.base_url('openrouter')}/api/v1/chat/completions", headers, body, timeout=60)
    content = res["choices"][0]["message"]["content"]
    m = re.search(r"\{.*\}", content, re.S)
    add = json.loads(m.group(0)).get("add", []) if m else []
    return [a for a in add if a in known_steps and a not in current_steps]
