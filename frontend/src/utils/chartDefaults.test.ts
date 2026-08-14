import { describe, it, expect } from 'vitest';
import {
  defaultMaWindow,
  movingAverageSeries,
  smoothTimeSeries,
} from './chartDefaults';

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
