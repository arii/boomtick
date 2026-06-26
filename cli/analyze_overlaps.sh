#!/usr/bin/env bash
OVERLAP_FILE="pr_overlaps.txt"

if [[ ! -f "$OVERLAP_FILE" ]]; then
    gh pr list --json number --jq '.[].number' | xargs -I{} sh -c "gh pr diff {} --name-only | sed 's|^|{} |'" | \
    awk '{file=$2; pr=$1; count[file]++; prs[file] = prs[file] " PR #" pr} END {for (f in count) if (count[f] > 1) print f " overlaps in:" prs[f]}' > "$OVERLAP_FILE"
fi

awk -F' overlaps in: ' '{
    f=$1; p=$2;
    split(f, path, "/");
    dir = (path[2] == "") ? "root" : path[1] "/";
    results[dir] = results[dir] "File: " f "\n  PRs: " p "\n"
} 
END {
    for (d in results) {
        print "=== Directory: " d " ===";
        print results[d];
    }
}' "$OVERLAP_FILE"
