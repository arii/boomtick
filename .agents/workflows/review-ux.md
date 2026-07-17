> Follow `.agents/AGENT_CONTRACT.md` before reading anything else.

## Failure Modes (Read Before Starting)

- **DO NOT** read context from any source other than the files specified below.
- **DO NOT** create new files unless this workflow explicitly says so.
- **DO NOT** skip steps because an earlier step produced no output.
- **DO NOT** submit partial JSON — all placeholder values must be replaced.
- If you are uncertain about a line number, re-read the diff. Never guess.

---

## description: Systematically review and test UI/UX changes interactively using playwright-cli

# Review UX Changes

0. **Prerequisites**:
   Ensure project dependencies and `playwright-cli` are installed, and its skills are available.

```bash
pnpm install
npm install -g @playwright/cli@latest
playwright-cli install --skills
```

1. **Pre-flight validation**:

```bash
node scripts/detect-antipatterns.mjs
```

2. **Start the Application**:

**Interactive (Headed)**:
```bash
pnpm run dev &
```

**Automation-Safe (Headless)**:
```bash
# Start with output piped to logs for process lifecycle management
pnpm run dev > dev-server.log 2>&1 &

# Mandatory health check
curl --silent --fail --retry 5 --retry-connrefused http://localhost:3000/ || exit 1
```

3. **Desktop Visual Audit (1440x900)**:

```bash
playwright-cli open http://localhost:3000/ --headed --viewport-size=1440,900
```

Verify the following routes and features:

- `/`
- `/about`
- `/blog`
- `/gear`
- `/research`
- Search modal
  Verify: Design consistency, typography, Recharts rendering, and ContentCard/GearCard 16:9 aspect ratio.

```bash
playwright-cli snapshot
playwright-cli screenshot --filename=desktop-home.png
```

4. **Mobile Visual Audit (390x844)**:

```bash
playwright-cli open http://localhost:3000/ --headed --viewport-size=390,844
```

Verify the same routes and features, plus:

- Mobile navigation bar (`pb-[safe-area-inset-bottom]`)
- Mobile spacing and tap targets
- Search modal overlay and Z-index collisions (ensure no overlap with header/hamburger menu)

```bash
playwright-cli snapshot
playwright-cli screenshot --filename=mobile-home.png
```

5. **Cleanup**:

**Interactive**:
```bash
playwright-cli close-all
npx kill-port 3000
```

**Automation-Safe (Graceful Shutdown)**:
```bash
# Stop the process gracefully in headless scenarios
kill $(lsof -t -i :3000) 2>/dev/null || true
```

6. **Evaluate Against Core Design Principles**:
   Systematically review your screenshots and interactive sessions against these heuristics:

- **Spatial Design & Layout**: Grouping, whitespace, consistent padding.
- **Typography**: Visual hierarchy, line heights, font weights.
- **Color & Contrast**: Accessibility, interactive states, minimum 4.5:1 contrast ratio.
- **Interaction & Motion**: Hover/focus states, purposeful transitions.
- **Cognitive Load & UX Writing**: Choice architecture, action-oriented labels, empty states.

7. **Structure Your UX Feedback**:
   When logging UX issues from your Playwright snapshots, always use a standardized format:

- **Observation**: What is currently happening in the UI?
- **Heuristic / Principle Violated**: Why is this a problem?
- **Impact**: How does this affect the user experience?
- **Recommendation**: Actionable steps to fix the issue.

_Example Feedback Format_:

> **[Medium] Contrast ratio failure on /blog read-more buttons**
>
> - **Observation**: The "Read More" text is `text-gray-400` on a `bg-gray-50` background.
> - **Principle**: Accessibility (Color & Contrast).
> - **Impact**: Fails WCAG AA standards; difficult for visually impaired users to read.
> - **Recommendation**: Change the text class to `text-gray-600` or darker.

8. **Assign Severity Scores**:
   Categorize your UX feedback so the engineering team knows what to prioritize:

- **Critical (P0)**: Broken functionality, blocking overlap, severe accessibility failures.
- **High (P1)**: Major visual bugs, confusing navigation, high cognitive load.
- **Medium (P2)**: Inconsistent design tokens, missing hover states, minor responsive quirks.
- **Low/Polish (P3)**: Micro-interaction tweaks, slight spacing adjustments.

9. **Consolidate and Share Results**:
   Compile the Playwright artifacts into a comprehensive UX report:

- Create a PR comment or markdown document titled `UX Audit: [Feature Name]`.
- Embed the relevant Playwright screenshots.
- List the structured feedback categorized by severity.
- Provide a checklist of actionable recommendations to address the findings.
