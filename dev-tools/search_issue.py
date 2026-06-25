#!/usr/bin/env python3
import urllib.request
import urllib.parse
import sys

def search_duckduckgo(query):
    url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(query)
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
    try:
        html = urllib.request.urlopen(req, timeout=10).read().decode('utf-8')
        print(html[:2000])
    except Exception as e:
        print("Error:", e)

if __name__ == '__main__':
    if len(sys.argv) > 1:
        search_duckduckgo(" ".join(sys.argv[1:]))
    else:
        print("Usage: python search_issue.py <query>")
