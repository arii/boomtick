#!/usr/bin/env bash
OVERLAP_FILE="pr_overlaps.txt"

if [[ ! -f "$OVERLAP_FILE" ]]; then
    echo "Error: $OVERLAP_FILE not found. Run analyze_overlaps.sh first."
else
    awk -F' overlaps in: ' '/^\.github\/workflows\// {
        f=$1; p=$2;
        print "File: " f "\nRelated PRs: " p "\n---"
    }' "$OVERLAP_FILE" > workflow_overlaps.txt

    cat workflow_overlaps.txt
fi
