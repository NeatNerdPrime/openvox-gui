import { describe, expect, it } from 'vitest';
import { STATUS_FILTER_CHIPS, statusMantine } from './statusTheme';

describe('statusMantine', () => {
  it('maps known statuses and falls back to unreported/unknown', () => {
    expect(statusMantine('unchanged')).toBe('teal');
    expect(statusMantine('changed')).toBe('orange');
    expect(statusMantine('FAILED')).toBe('red');
    expect(statusMantine(null)).toBe('gray');
    expect(statusMantine('not-a-status')).toBe('gray');
  });

  it('exposes the five Nodes filter chips', () => {
    expect(STATUS_FILTER_CHIPS.map((c) => c.value)).toEqual([
      'failed',
      'changed',
      'unchanged',
      'unreported',
      'noop',
    ]);
  });
});
