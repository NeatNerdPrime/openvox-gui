import { describe, it, expect } from 'vitest';
import { isNeedsAttention } from './needsAttention';

const now = Date.parse('2026-08-25T12:00:00Z');

describe('isNeedsAttention', () => {
  it('flags failed, unreported, and empty status', () => {
    expect(isNeedsAttention({ latest_report_status: 'failed' }, now)).toBe(true);
    expect(isNeedsAttention({ latest_report_status: 'unreported' }, now)).toBe(true);
    expect(isNeedsAttention({ latest_report_status: '' }, now)).toBe(true);
    expect(isNeedsAttention({}, now)).toBe(true);
  });

  it('flags unchanged older than 24h', () => {
    expect(
      isNeedsAttention(
        {
          latest_report_status: 'unchanged',
          report_timestamp: '2026-08-23T11:00:00Z',
        },
        now,
      ),
    ).toBe(true);
  });

  it('leaves a fresh unchanged node off the list', () => {
    expect(
      isNeedsAttention(
        {
          latest_report_status: 'unchanged',
          report_timestamp: '2026-08-25T10:00:00Z',
        },
        now,
      ),
    ).toBe(false);
  });
});
