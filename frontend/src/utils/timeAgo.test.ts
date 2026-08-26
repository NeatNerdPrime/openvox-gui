import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { timeAgo } from './timeAgo';

describe('timeAgo', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-08-26T12:00:00Z'));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('returns the empty label when timestamp is missing or invalid', () => {
    expect(timeAgo(null)).toBe('Never');
    expect(timeAgo(undefined, 'n/a')).toBe('n/a');
    expect(timeAgo('not-a-date')).toBe('Never');
  });

  it('formats recent through multi-day deltas', () => {
    expect(timeAgo('2026-08-26T11:59:30Z')).toBe('Just now');
    expect(timeAgo('2026-08-26T11:45:00Z')).toBe('15m ago');
    expect(timeAgo('2026-08-26T09:00:00Z')).toBe('3h ago');
    expect(timeAgo('2026-08-24T12:00:00Z')).toBe('2d ago');
  });
});
