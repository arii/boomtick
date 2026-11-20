#!/usr/bin/env python3
"""Offline protocol mock of Cognee and Senso, built from their public docs.
Used only to exercise the harness's LIVE client code paths without keys. Not for the demo.
    python3 mock_sponsors.py 9001
"""
import json
import re
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

DOCS, NODES, POLLS = [], {}, {}


class H(BaseHTTPRequestHandler):
    def _j(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def _body(self):
        return self.rfile.read(int(self.headers.get("Content-Length", 0)))

    def do_GET(self):
        if self.path == "/api/v1/org/me":
            return self._j(200, {"org_id": "mock", "name": "mock"}) if self.headers.get("X-API-Key") else self._j(401, {})
        m = re.match(r"/api/v1/org/kb/nodes/(.+)", self.path)
        if m and m.group(1) in NODES:
            nid = m.group(1); POLLS[nid] = POLLS.get(nid, 0) + 1
            st = "complete" if POLLS[nid] >= 2 else "processing"
            return self._j(200, {"kb_node_id": nid, "type": "content", "content": {"processing_status": st}})
        self._j(404, {})

    def do_POST(self):
        raw, p = self._body(), self.path
        if p == "/api/v1/add":
            if not (self.headers.get("X-Api-Key") or self.headers.get("Authorization")):
                return self._j(401, {})
            added = 0
            for part in raw.decode().split("--")[1:]:
                # Real Cognee only stores file uploads under "data"; plain fields are ignored.
                m = re.search(r'name="data"; filename="[^"]*"\r\n(?:[^\r\n]+\r\n)*\r\n(.*)\r\n$', part, re.S)
                if m: DOCS.append(m.group(1)); added += 1
            return self._j(200, {"status": "PipelineRunCompleted", "data_ingestion_info": [{}] * added, "data_ids": [], "n": len(DOCS)})
        if p == "/api/v1/cognify":
            return self._j(200, {"status": "done"})
        if p == "/api/v1/search":
            q = set(re.findall(r"[a-z0-9]+", json.loads(raw)["query"].lower()))
            hits = [d for d in DOCS if len(q & set(re.findall(r"[a-z0-9]+", d.lower()))) >= 3]
            return self._j(200, [{"text": d} for d in hits[:5]])
        if p == "/api/v1/chat/completions":
            return self._j(200, {"choices": [{"message": {"content": "hi"}}]})
        if p == "/api/v1/org/kb/raw":
            b = json.loads(raw)
            if any(n["text"] == b["text"] for n in NODES.values()):
                return self._j(409, {"detail": "duplicate"})
            nid = f"kb-{len(NODES) + 1}"; cid = f"content-{len(NODES) + 1}"
            NODES[nid] = {"cid": cid, "text": b["text"], "title": b["title"]}
            return self._j(202, {"id": cid, "kb_node_id": nid, "type": "raw", "title": b["title"], "processing_status": "processing"})
        if p == "/api/v1/org/search":
            q = json.loads(raw)["query"].lower()
            res = [{"content_id": n["cid"], "title": n["title"], "score": .9, "rank": 1}
                   for n in NODES.values() if n["title"].lower() in q or q in n["title"].lower()]
            return self._j(200, {"query": q, "results": res, "total_results": len(res)})
        self._j(404, {})

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    HTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
