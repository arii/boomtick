"""Constants for dev_tools."""

# Robust placeholder detection using regex to handle minor variants
REVIEW_PLACEHOLDERS = [
    r"<findings\s*/?>",
    r"<summary\s*/?>",
    r"<filename\s*/?>",
    r"<feedback\s*/?>",
    r"<Approved\s*\|\s*Approved\s*with\s*Minor\s*Changes\s*\|\s*Not\s*Approved>",
    r"##\s+ANTI-AI-SLOP",
    r"##\s+FINDINGS",
    r"##\s+FINAL RECOMMENDATION",
    r"<!--\s*td-review-manager-comment\s*-->",
]
