#!/usr/bin/env python3
import re,sys
TRIVIAL_PATTERNS=[r"import/order",r"no-trailing-spaces",r"prettier",r"semi\b",r"quotes\b",r"eol-last"]
COMPLEX_PATTERNS=[r"TS\d{4}",r"Cannot find module",r"Build failed",r"jest.*failed",r"vitest.*failed",r"playwright.*failed"]
def classify(log_text:str)->str:
    for p in COMPLEX_PATTERNS:
        if re.search(p,log_text,re.IGNORECASE): return "complex"
    for p in TRIVIAL_PATTERNS:
        if re.search(p,log_text,re.IGNORECASE): return "trivial"
    return "moderate"
if __name__=='__main__': print(classify(sys.stdin.read()))
