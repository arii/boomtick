import os
import sys
from tdw_services.utils import log_info
import json
import glob
from datetime import datetime

def generate_report():
    artifacts_dir = os.path.join(os.getcwd(), 'artifacts', 'ux-audit')
    results_dir = os.path.join(artifacts_dir, 'results')
    lighthouse_dir = os.path.join(artifacts_dir, 'lighthouse')
    issues_dir = os.path.join(artifacts_dir, 'issues')

    os.makedirs(issues_dir, exist_ok=True)

    report_lines = [
        "# UX Audit Report",
        f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n",
        "## Summary",
    ]

    findings = []

    result_files = glob.glob(os.path.join(results_dir, "*.json"))
    report_lines.append(f"- Routes Audited: {len(result_files)}")

    # Aggregate results
    all_results = []
    for rf in result_files:
        with open(rf, 'r') as f:
            all_results.append(json.load(f))

    # Lighthouse summary
    lh_files = glob.glob(os.path.join(lighthouse_dir, "*.report.json"))
    if lh_files:
        report_lines.append("\n## Lighthouse Scores")
        report_lines.append("| Route | Performance | Accessibility | Best Practices | SEO |")
        report_lines.append("|-------|-------------|---------------|----------------|-----|")
        for lhf in lh_files:
            with open(lhf, 'r') as f:
                data = json.load(f)
                cats = data.get('categories', {})
                name = os.path.basename(lhf).replace('.report.json', '')
                perf = int(cats.get('performance', {}).get('score', 0) * 100)
                a11y = int(cats.get('accessibility', {}).get('score', 0) * 100)
                bp = int(cats.get('best-practices', {}).get('score', 0) * 100)
                seo = int(cats.get('seo', {}).get('score', 0) * 100)
                report_lines.append(f"| {name} | {perf} | {a11y} | {bp} | {seo} |")

    # High Severity Findings
    report_lines.append("\n## Key Findings")

    for res in all_results:
        route = res['route']
        vp = res['viewport']
        screenshot = res.get('screenshot', 'N/A')
        is_mobile = 'mobile' in vp.lower()

        # 1. Accessibility (Axe)
        if res.get('accessibility') and res['accessibility'].get('violations'):
            violations = res['accessibility']['violations']
            for v in violations:
                finding = {
                    "title": f"Accessibility Violation: {v['id']} on `{route}` ({vp})",
                    "route": route,
                    "viewport": vp,
                    "category": "Accessibility",
                    "severity": "High" if v['impact'] in ['critical', 'serious'] else "Medium",
                    "evidence": f"Axe violation: {v['description']}. Found on {len(v['nodes'])} elements.",
                    "recommendation": f"Fix {v['id']} issues. Help: {v['helpUrl']}",
                    "screenshot": screenshot,
                    "user_impact": "Users with disabilities may be unable to navigate or interact with the page effectively.",
                    "acceptance_criteria": [
                        "Lighthouse/Axe accessibility audit passes for this category",
                        "Element is keyboard accessible",
                        "Screen reader announcements are clear"
                    ]
                }
                findings.append(finding)

        # 2. Layout Overflow
        if res.get('overflow'):
            finding = {
                "title": f"Horizontal Overflow on `{route}` ({vp})",
                "route": route,
                "viewport": vp,
                "category": "Layout",
                "severity": "High",
                "evidence": f"Detected {len(res['overflow'])} elements overflowing viewport.",
                "recommendation": "Ensure all elements use responsive widths and handle long content with word-wrap or overflow-x: auto.",
                "screenshot": screenshot,
                "user_impact": "Causes janky scrolling and potential content cut-off.",
                "acceptance_criteria": [
                    "No horizontal scrolling at tested width",
                    "All elements are contained within the viewport"
                ]
            }
            findings.append(finding)

        # 3. Small Tap Targets
        if res.get('tapTargets'):
            finding = {
                "title": f"Small Tap Targets on `{route}` ({vp})",
                "route": route,
                "viewport": vp,
                "category": "Mobile UX",
                "severity": "Medium",
                "evidence": f"Found {len(res['tapTargets'])} interactive elements smaller than 44x44px.",
                "recommendation": "Increase padding or dimensions of interactive elements to at least 44x44px for better mobile usability.",
                "screenshot": screenshot,
                "user_impact": "Makes interactive elements difficult to tap on a phone, leading to user frustration.",
                "acceptance_criteria": [
                    "All interactive elements meet the 44x44px minimum target size",
                    "Adequate spacing between adjacent links/buttons"
                ]
            }
            findings.append(finding)

        # 4. Image issues
        oversized_images = [img for img in res.get('images', []) if img['naturalWidth'] > img['renderedWidth'] * 2 and img['naturalWidth'] > 1000]
        if oversized_images:
            finding = {
                "title": f"Oversized Images on `{route}` ({vp})",
                "route": route,
                "viewport": vp,
                "category": "Performance",
                "severity": "Medium",
                "evidence": f"Found {len(oversized_images)} images where natural size is significantly larger than rendered size.",
                "recommendation": "Use responsive image sets (srcset) or serve optimized crops for smaller viewports.",
                "screenshot": screenshot,
                "user_impact": "Increases page load time and consumes excessive bandwidth.",
                "acceptance_criteria": [
                    "Images are appropriately sized for the viewport",
                    "Lighthouse performance score is maintained or improved"
                ]
            }
            findings.append(finding)

        # 5. Above the Fold heuristics
        atf = res.get('aboveTheFold')
        if atf:
            if atf.get('heroViewportPercentage', 0) > 80 and not atf.get('hasPrimaryCTA'):
                finding = {
                    "title": f"Poor Above-the-Fold Visibility on `{route}` ({vp})",
                    "route": route,
                    "viewport": vp,
                    "category": "UX",
                    "severity": "Medium",
                    "evidence": f"Hero occupies {int(atf['heroViewportPercentage'])}% of viewport and no CTA is visible.",
                    "recommendation": "Reduce hero height or move primary CTA higher to ensure it is visible above the fold.",
                    "screenshot": screenshot,
                    "user_impact": "Primary page purpose and next steps are unclear upon initial load.",
                    "acceptance_criteria": [
                        "Primary page purpose is clear above the fold",
                        "Primary CTA is visible without scrolling"
                    ]
                }
                findings.append(finding)

    # List Findings in Report
    if not findings:
        report_lines.append("No major issues detected. ✅")
    else:
        # Sort findings by severity
        severity_map = {"High": 0, "Medium": 1, "Low": 2}
        findings.sort(key=lambda x: severity_map.get(x['severity'], 3))

        for f in findings:
            report_lines.append(f"### {f['title']}")
            report_lines.append(f"- **Category:** {f['category']}")
            report_lines.append(f"- **Severity:** {f['severity']}")
            report_lines.append(f"- **Evidence:** {f['evidence']}")
            report_lines.append(f"- **Screenshot:** `{f['screenshot']}`")
            report_lines.append(f"- **Recommendation:** {f['recommendation']}\n")

            # Generate Issue Draft
            safe_title = f["title"].replace('/', '_').replace('`', '').replace('(', '').replace(')', '').replace(':', '')
            issue_slug = f"{f['category']}-{safe_title}".lower().replace(' ', '-')
            issue_path = os.path.join(issues_dir, f"{issue_slug}.md")
            with open(issue_path, 'w') as issue_file:
                issue_file.write(f"## Problem\n{f['title']}\n\n")
                issue_file.write(f"## Route / viewport\n- Route: {f['route']}\n- Viewport: {f['viewport']}\n\n")
                issue_file.write(f"## Evidence\n- {f['evidence']}\n- Screenshot: `{f['screenshot']}`\n\n")
                issue_file.write(f"## User impact\n{f.get('user_impact', 'N/A')}\n\n")
                issue_file.write(f"## Recommended fix\n{f['recommendation']}\n\n")
                issue_file.write("## Acceptance criteria\n")
                for ac in f.get('acceptance_criteria', []):
                    issue_file.write(f"- [ ] {ac}\n")

                # Add cross-viewport regression check
                other = "mobile" if "desktop" in f['viewport'].lower() else "desktop"
                issue_file.write(f"- [ ] No new {other} regressions\n")

                issue_file.write(f"\n## Severity\n{f['severity']}\n")

    report_path = os.path.join(artifacts_dir, "ux-audit-report.md")
    with open(report_path, 'w') as f:
        f.write("\n".join(report_lines))

    log_info(f"Report generated: {report_path}")
    log_info(f"Issue drafts generated in: {issues_dir}")

if __name__ == "__main__":
    generate_report()
