import { beforeEach, describe, expect, it } from 'vitest';
import { clearSessionCache, readSessionCache, writeSessionCache } from './sessionCache';

describe('sessionCache', () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  it('round-trips JSON payloads', () => {
    writeSessionCache('k', { n: 1 });
    expect(readSessionCache<{ n: number }>('k')).toEqual({ n: 1 });
  });

  it('returns null for missing or invalid JSON', () => {
    expect(readSessionCache('missing')).toBeNull();
    sessionStorage.setItem('bad', '{not-json');
    expect(readSessionCache('bad')).toBeNull();
  });

  it('honors the isValid predicate and clear', () => {
    writeSessionCache('k', { n: 1 });
    expect(readSessionCache<{ n: number }>('k', (v) => v.n > 5)).toBeNull();
    clearSessionCache('k');
    expect(readSessionCache('k')).toBeNull();
  });
});
