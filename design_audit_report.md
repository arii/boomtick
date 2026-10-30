# Design Issue Discovery Audit: arii/remote-server

## 1. Repository Discovery & Synthesis

**Directory Structure & Core Modules:**
The `arii/remote-server` repository is primarily a home server bootstrap project using bash scripts and Docker Compose. The `buttons/` directory contains a single-file UI `server.py` serving a basic HTML interface to interact with GitHub Actions, PRs, and Jules agent sessions.

**Design System & UI Components:**
- There is no formal design system. The UI is implemented as inline CSS in a `<style>` block within `server.py` (lines 1496-1768).
- The CSS defines a dark theme using CSS variables (`--bg-app: #0b1120`, `--primary: #3b82f6`, `--danger: #ef4444`).
- Common components are basic HTML buttons, tabs, drawer (`#outputDrawer`), and cards (`.prcard`).
- **Responsive design:** Some media queries exist (e.g. max-width: 520px for tab bar), but many elements lack proper touch targets or responsive collapsing.

## 2. Issue Backlog (Discovered & Expanded)

**Track A: Expand Existing Issues (Missing Specifications)**
1. **Issue #20: Drawer header buttons are 28px tall** (Expand to formal specification)
2. **Issue #21: Make Report bug discoverable outside failed runs** (Expand to formal specification)
3. **Issue #16: Collapse per-section explainer text so controls are above the fold on phone** (Expand to formal specification)

**Track B: Generate Discovered Issues (New Gaps)**
1. **Discovered Issue: Inconsistent Focus States & Keyboard Accessibility**
   - *Gap:* The current inline CSS lacks `:focus-visible` or clear `:focus` indicators across interactive elements (buttons, inputs). Keyboard navigation is not supported well.
2. **Discovered Issue: Lack of Loading Skeletons in PR / Issues view**
   - *Gap:* When switching repos or fetching data, the UI is either cleared abruptly or uses a raw text spinner.

---


## Expanded Issue: Drawer Header Buttons Touch Target (Issue #20)

**Context & Motivation:**
The "Report bug", "Clear output", and "Close" buttons in the `#outputDrawer` header are currently styled with `font-size: 0.85em` and `padding: 0.7em 1em`, resulting in a rendered height of ~28px. On mobile devices, this violates the minimum touch target guideline (44px), making the buttons extremely difficult to tap reliably without zooming.

**Current State:**
- File: `buttons/server.py`
- CSS Rule: `#drawerHead button { width: auto; margin: 0; padding: 0.7em 1em; font-size: 0.85em; }`

**Design Specification & Desired Behavior:**
- **Token usage:** Maintain existing background and border tokens (`var(--bg-card)` for base buttons, `var(--text-main)` for text).
- **Component hierarchy:** The `.dbactions` span holding these buttons should use flex gap to separate them.
- **Responsive / viewport adaptations:** Increase `font-size` to `0.95em` and `padding` to `0.8em 1em` to yield a button height of at least ~36px (matching `.tab-btn`), ideally 44px on mobile via a `@media (max-width: 520px)` query.
- **Interactive states:** Hover states remain as-is (`background: var(--bg-card-hover); border-color: var(--primary);`).

**Scope & Non-Goals:**
- Do not restyle the entire drawer, only the buttons inside `#drawerHead`.
- Do not introduce new CSS classes.

**Accessibility (a11y):**
- Ensures WCAG 2.1 Target Size (Success Criterion 2.5.5) compliance for mobile users.

**Affected Files & Dependencies:**
- `buttons/server.py` (inline `<style>` block).

**Acceptance Criteria:**
- [ ] `#drawerHead button` elements have a minimum computed height of 36px on desktop and 44px on mobile.
- [ ] Buttons are visually distinct and spaced evenly.

**Test & Validation Plan:**
- Manual verification: Open the drawer in Chrome DevTools using the mobile device toolbar (iPhone 12/13). Verify computed height of the "Close" button.


## Expanded Issue: Report Bug Button Discoverability (Issue #21)

**Context & Motivation:**
The "Report bug" feature generates a pre-filled GitHub issue with terminal output when a run fails. Currently, the button (`#bugBtn`) is hidden inside the `#outputDrawer` header and only becomes enabled/visible if a failed run is actively being viewed. Users cannot discover this capability beforehand, and it forces a reactive UX.

**Current State:**
- File: `buttons/server.py`
- HTML: `<button id="bugBtn" title="File the failed run as a GitHub issue">Report bug</button>` (inside `#drawerHead`).
- JS Logic: `if (bugBtn) bugBtn.disabled = !(run.done && run.exit_code !== 0);`

**Design Specification & Desired Behavior:**
- **Component hierarchy:**
  1. Keep `#bugBtn` in the drawer header, but ensure it is always visually present. When disabled, use a muted appearance (`opacity: 0.4` or `color: var(--text-muted)`).
  2. Add a persistent, secondary entry point for "Report Issue" in the footer of the Actions tab.
- **Interactive states:**
  - `disabled`: Grayed out with `cursor: not-allowed` and tooltip explaining "Available when a run fails".
  - `active`: Uses `var(--primary)` text color to indicate readiness.
- **Responsive / viewport adaptations:** The footer button should be full-width on mobile.

**Scope & Non-Goals:**
- Do not change the backend API route (`/buttons/api/create-issue`).
- Only modify the UI placement and disabled state styling of the button.

**Accessibility (a11y):**
- Ensure the `disabled` attribute is set correctly so screen readers announce it as unavailable.
- Provide `aria-label` or `title` explaining why it is disabled.

**Affected Files & Dependencies:**
- `buttons/server.py` (HTML structure, CSS, and JS state update logic).

**Acceptance Criteria:**
- [ ] The "Report bug" button in the drawer header is always visible, but disabled when there is no failed run.
- [ ] A tooltip/title explains the disabled state.

**Test & Validation Plan:**
- Manual verification: Load the UI with no failed runs. Open the drawer (e.g. by starting a successful run). Ensure "Report bug" is visible but unclickable.


## Discovered Issue: Inconsistent Focus States & Keyboard Accessibility

**Context & Motivation:**
The custom inline CSS in `buttons/server.py` heavily customizes button styles (`background`, `border`, `color`) but entirely omits `:focus` or `:focus-visible` pseudo-classes. When users navigate the UI using a keyboard (Tab key), it is impossible to tell which button or tab is currently active. This severely breaks accessibility.

**Current State:**
- File: `buttons/server.py`
- CSS Rules: `button { ... }`, `button:hover { ... }`, `input { ... }` lack focus styles.

**Design Specification & Desired Behavior:**
- **Token usage:** Introduce a standard focus ring using `var(--primary)`.
- **Desired Behavior:** Add a global CSS rule for interactive elements:
  ```css
  button:focus-visible, input:focus-visible, select:focus-visible {
    outline: 2px solid var(--primary);
    outline-offset: 2px;
  }
  ```
- **Interactive states:** `focus-visible` will display a blue ring around the focused element, without affecting mouse users (unlike `:focus`).

**Scope & Non-Goals:**
- Do not implement complex custom focus management in JavaScript. Rely on native browser `:focus-visible`.

**Accessibility (a11y):**
- Directly satisfies WCAG 2.1 Focus Visible (Success Criterion 2.4.7).

**Affected Files & Dependencies:**
- `buttons/server.py` (inline `<style>` block).

**Acceptance Criteria:**
- [ ] Tabbing through the UI displays a clear 2px primary-colored outline around focused buttons and inputs.
- [ ] Mouse clicks do not trigger the focus outline (due to `:focus-visible`).

**Test & Validation Plan:**
- Manual verification: Open the interface, press the `Tab` key repeatedly, and verify that the focus indicator moves sequentially and is clearly visible against the dark background.
