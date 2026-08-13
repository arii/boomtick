import { describe, expect, it } from 'vitest';

const resolvePrNumber = (
  eventPrNumber?: number | string,
  inputPrNumber?: number | string,
  headPrNumber?: number | string
): string => {
  if (eventPrNumber) return String(eventPrNumber);
  if (inputPrNumber) return String(inputPrNumber);
  if (headPrNumber) return String(headPrNumber);
  return '';
};

describe('resolvePrNumber', () => {
  it('prioritizes direct pull_request event number', () => {
    expect(resolvePrNumber(101, 202, 303)).toBe('101');
  });

  it('falls back to inputPrNumber when event number is missing', () => {
    expect(resolvePrNumber('', 202, 303)).toBe('202');
  });

  it('falls back to head branch PR lookup when event and input are missing', () => {
    expect(resolvePrNumber('', '', 303)).toBe('303');
  });

  it('returns empty string when no PR context exists', () => {
    expect(resolvePrNumber('', '', '')).toBe('');
  });
});
