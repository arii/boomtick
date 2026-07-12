# pylint: disable=line-too-long
"""DuckDuckGo Search tool."""
import json
import sys

try:
    from duckduckgo_search import DDGS
except ImportError:
    print(json.dumps({"error": "duckduckgo_search package not found. Please install it using 'pip install duckduckgo-search' (preferably in a virtual environment)."}), file=sys.stderr)
    sys.exit(1)

if len(sys.argv) != 3:
    print(json.dumps({"error": f"Invalid argument count. Expected 2 (query, max_results), got {len(sys.argv) - 1}."}), file=sys.stderr)
    sys.exit(1)

try:
    query = sys.argv[1]
    max_results = int(sys.argv[2])
    results = DDGS().text(query, max_results=max_results)
    print(json.dumps(list(results)))
except Exception as e:
    print(json.dumps({"error": str(e)}), file=sys.stderr)
    sys.exit(1)
