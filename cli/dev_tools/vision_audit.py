#!/usr/bin/env python3
"""
vision_audit.py - Vision-based regression audit via AI API.
"""

import os
import json
import base64
import argparse
from typing import Optional, List, Dict
from dev_tools_sdk.config import load_project_config

PROJECT_CONFIG = load_project_config()
VISION_MODEL = os.environ.get("VISION_MODEL", PROJECT_CONFIG.ai_vision_model)

def call_ai(prompt: str, paths: List[str]) -> Optional[str]:
    images = []
    for p in paths:
        if os.path.exists(p):
            with open(p, "rb") as f:
                images.append(base64.b64encode(f.read()).decode('utf-8'))

    if not images: return None

    try:
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import HumanMessage
    except ImportError:
        print("langchain_openai or langchain_core is not installed.")
        return None

    token = os.getenv("GITHUB_TOKEN")
    if not token:
        print("No GITHUB_TOKEN found.")
        return None

    llm = ChatOpenAI(
        base_url="https://models.inference.ai.azure.com",
        api_key=token,
        model=VISION_MODEL,
        temperature=0.7,
        max_tokens=2048,
    )

    message_content = [{"type": "text", "text": prompt}]
    for img in images:
        message_content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{img}"}
        })

    try:
        response = llm.invoke([HumanMessage(content=message_content)])
        return response.content
    except Exception as e:
        print(f"❌ Vision call failed: {e}")
        return None

def get_project_root() -> str:
    curr = os.path.abspath(os.path.dirname(__file__))
    while curr != os.path.dirname(curr):
        if any(os.path.exists(os.path.join(curr, m)) for m in ['package.json', '.git']): return curr
        curr = os.path.dirname(curr)
    return os.getcwd()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", default="artifacts/visual-review/summary.json")
    parser.add_argument("--project-root")
    args = parser.parse_args()

    root = args.project_root or get_project_root()
    sum_path = os.path.join(root, args.summary) if not os.path.isabs(args.summary) else args.summary

    if not os.path.exists(sum_path):
        print(f"❌ Missing: {sum_path}"); return

    with open(sum_path, 'r') as f: data = json.load(f)
    routes = data.get('routes', [])
    if not routes: return

    results = {}

    for s in routes:
        before, after = s.get('beforeCroppedPath'), s.get('afterCroppedPath')
        if not (before and after): continue

        prompt = f"Analyze visual changes for {s['route']}. Describe what changed between BEFORE and AFTER. Identify bugs vs improvements. Be concise."
        res = call_ai(prompt, [os.path.join(root, before), os.path.join(root, after)])
        if res:
            results[s['route']] = res
            print(f"\n--- {s['route']} ---\n{res}\n")

    if results:
        out = os.path.join(root, "artifacts/visual-review/vision_audit.json")
        with open(out, 'w') as f: json.dump(results, f, indent=2)
        print(f"✅ Results: {out}")

if __name__ == "__main__":
    main()
