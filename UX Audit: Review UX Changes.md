# UX Audit: Review UX Changes

- **Observation**: A hardcoded pixel value (`384px`) was used in `src/layouts/layout-maps.ts` instead of a semantic design token or `rem` equivalent.
- **Heuristic / Principle Violated**: **Spatial Design & Layout** (Avoid arbitrary/hardcoded pixel values; rely on design tokens).
- **Impact**: Breaking the design token system can cause responsive design inconsistencies and makes global layout scaling difficult.
- **Recommendation**: I've changed the layout map value for `96` to `24rem` which natively matches the `384px` value while relying on the standard 16px rem system and eliminating the anti-pattern.

### Severity
- **Low/Polish (P3)**: It's an internal architectural issue in `layout-maps.ts` that violates layout token conventions, without an immediate end-user blocking impact.
