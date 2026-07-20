/**
 * Design token layout maps for layout primitives.
 * Consolidates arbitrary spacing values into semantic tokens.
 */

export const SPACING_MAP = {
  'viewport-half': 'var(--spacing-viewport-half)',
  '96': '24rem',
} as const;

export type SpacingToken = keyof typeof SPACING_MAP;
