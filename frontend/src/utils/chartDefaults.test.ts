import { describe, it, expect } from 'vitest';
import {
  buildHourlyNodeSeries,
  defaultMaWindow,
  movingAverageSeries,
  safeChartKey,
  smoothTimeSeries,
} from './chartDefaults';

describe('safeChartKey', () => {
  it('strips dots so Recharts will not treat the key as a nested path', () => {
    const cn = 'ovca1.pdxc-it.corp.int-x.ai';
    const key = safeChartKey(cn);
    expect(key).toMatch(/^k_[A-Za-z0-9_]+$/);
    expect(key).not.toContain('.');
    const row = { time: '2026-09-03T12', [key]: 8.5 };
    expect(row[key]).toBe(8.5);
  });
});

describe('buildHourlyNodeSeries', () => {
  it('averages per hour under safe keys and leaves missing hours null', () => {
    const rows = buildHourlyNodeSeries(
      [
        { time: '2026-09-03T12:10:00', certname: 'web01.corp.int-x.ai', total: 10 },
        { time: '2026-09-03T12:40:00', certname: 'web01.corp.int-x.ai', total: 20 },
        { time: '2026-09-03T13:05:00', certname: 'db01.corp.int-x.ai', total: 30 },
      ],
      ['web01.corp.int-x.ai', 'db01.corp.int-x.ai'],
    );
    const kWeb = safeChartKey('web01.corp.int-x.ai');
    const kDb = safeChartKey('db01.corp.int-x.ai');
    expect(rows).toHaveLength(2);
    expect(rows[0].time).toBe('2026-09-03T12');
    expect(rows[0][kWeb]).toBe(15);
    expect(rows[0][kDb]).toBeNull();
    expect(rows[1][kDb]).toBe(30);
    expect(rows[1][kWeb]).toBeNull();
  });
});

describe('movingAverageSeries', () => {
  it('averages the trailing window and keeps time labels', () => {
    const rows = [
      { time: 'a', v: 0 },
      { time: 'b', v: 10 },
      { time: 'c', v: 20 },
    ];
    const out = movingAverageSeries(rows, ['v'], 2);
    expect(out.map((r) => r.time)).toEqual(['a', 'b', 'c']);
    expect(out[0].v).toBe(0);
    expect(out[1].v).toBe(5);
    expect(out[2].v).toBe(15);
  });

  it('skips non-finite values in the window', () => {
    const rows = [
      { time: 'a', v: 10 },
      { time: 'b', v: Number.NaN },
      { time: 'c', v: 20 },
    ];
    const out = movingAverageSeries(rows, ['v'], 3);
    expect(out[2].v).toBe(15);
  });
});

describe('smoothTimeSeries', () => {
  it('smooths numeric keys and leaves timestamp alone', () => {
    const rows = [
      { timestamp: 't0', failed: 0, compliant: 10 },
      { timestamp: 't1', failed: 10, compliant: 0 },
    ];
    const out = smoothTimeSeries(rows, 2);
    expect(out[1].timestamp).toBe('t1');
    expect(out[1].failed).toBe(5);
    expect(out[1].compliant).toBe(5);
  });
});

describe('defaultMaWindow', () => {
  it('grows with series length', () => {
    expect(defaultMaWindow(2)).toBe(1);
    expect(defaultMaWindow(8)).toBe(3);
    expect(defaultMaWindow(20)).toBe(5);
    expect(defaultMaWindow(80)).toBe(7);
    expect(defaultMaWindow(200)).toBe(11);
  });
});
