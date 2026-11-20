"""Test-only fakes for the LLM, Cognee and Senso. Never imported by runtime code.

FakeLLM routes by the system prompt of each request:
- executor: answers "GOOD ..." (with the task's must_include values) when the rendered rules mention one
  of the task's check values, otherwise repeats the recorded mistake (its must_not_include values)
- judge: passes iff the answer starts with GOOD
- task generator / mutator: pops scripted replies
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import rules as rules_mod  # noqa: E402


class FakeLLM:
    def __init__(self, mutator_replies=(), task_replies=(), executor=None):
        self.mutator_replies = list(mutator_replies)
        self.task_replies = list(task_replies)
        self.calls = []
        self.executor = executor or self.default_executor
        self.suite = None

    def __call__(self, messages, **kw):
        system = messages[0]["content"]
        self.calls.append({"system": system[:80], "messages": messages, "kw": kw})
        if system.startswith("You are an agent acting"):
            return self.executor(messages)
        if system.startswith("You grade one agent answer"):
            answer = messages[1]["content"].split("<<<ANSWER\n", 1)[1]
            return json.dumps({"pass": answer.startswith("GOOD"), "reason": "fake"})
        if system.startswith("You improve a user's rule set"):
            return self._pop(self.mutator_replies, "mutator")
        if system.startswith("You turn a recorded agent session"):
            return self._pop(self.task_replies, "tasks")
        raise AssertionError("unexpected prompt: " + system[:80])

    @staticmethod
    def _pop(queue, what):
        if not queue:
            raise AssertionError(f"no scripted {what} reply left")
        r = queue.pop(0)
        return r if isinstance(r, str) else json.dumps(r)

    def default_executor(self, messages):
        system, user = messages[0]["content"], messages[1]["content"]
        query = re.search(r"Task: (.*)", user).group(1)
        task = next(t for t in self.suite["tasks"] if t["query"] == query)
        values = [c["value"] for c in task["checks"]]
        rules_text = rules_mod.norm(system)
        good = any(rules_mod.norm(v) in rules_text for v in values) or "(no rules yet)" not in system and task.get("_good_with_any_rule")
        inc = " ".join(c["value"] for c in task["checks"] if c["type"] == "must_include")
        bad = " ".join(c["value"] for c in task["checks"] if c["type"] == "must_not_include")
        return f"GOOD {inc}" if good else f"BAD {bad}"

    def mutator_prompts(self):
        return [c["messages"][1]["content"] for c in self.calls if c["system"].startswith("You improve")]


class FakeCognee:
    DATASET = "proofloop_test"

    def __init__(self, sessions):
        self.sessions = sessions
        self.ingested = 0
        self.queries = []

    def ingest(self, sessions, extra_docs=()):
        self.ingested += 1
        return {"added": len(sessions)}

    def search(self, query):
        self.queries.append(query)
        q = set(re.findall(r"[a-z0-9]+", query.lower()))
        scored = []
        for s in self.sessions:
            words = set(re.findall(r"[a-z0-9]+", json.dumps(s).lower()))
            scored.append((len(q & words), s["session_id"]))
        scored.sort(reverse=True)
        return [{"type": "chunk", "text": f"... {sid} ...", "session_ids": [sid]} for n, sid in scored[:3] if n]


class FakeSenso:
    def __init__(self, fail=False):
        self.docs = {}
        self.fail = fail

    def post_raw(self, title, text, version):
        if self.fail:
            return 500, {"error": "fake failure"}
        cid, nid = f"c{len(self.docs)}", f"n{len(self.docs)}"
        self.docs[nid] = {"id": cid, "title": title, "text": text}
        return 202, {"id": cid, "kb_node_id": nid}

    def get_node(self, nid):
        return {"content": {"processing_status": "complete", "text": self.docs[nid]["text"]}}

    def search(self, query):
        return [{"content_id": d["id"], "title": d["title"]} for d in self.docs.values() if d["title"] == query]

    def read_text(self, nid):
        return self.docs[nid]["text"]
