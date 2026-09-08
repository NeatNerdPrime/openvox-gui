import { afterEach, describe, expect, it } from 'vitest';
import {
  IDLE_PREFETCH_PATHS,
  loaderForPath,
  prefetchRoute,
  resetPrefetchState,
} from './routePrefetch';

describe('routePrefetch', () => {
  afterEach(() => {
    resetPrefetchState();
  });

  it('maps operator paths to loaders', () => {
    expect(loaderForPath('/enc')?.id).toBe('enc');
    expect(loaderForPath('/enc/nodes')?.id).toBe('enc');
    expect(loaderForPath('/nodes')?.id).toBe('nodes');
    expect(loaderForPath('/nodes/web01.example.com')?.id).toBe('node-detail');
    expect(loaderForPath('/reports')?.id).toBe('reports');
    expect(loaderForPath('/insights')?.id).toBe('insights-monitor');
    expect(loaderForPath('/insights/compliance')?.id).toBe('insights-compliance');
    expect(loaderForPath('/nope')).toBeUndefined();
    expect(loaderForPath('')).toBeUndefined();
  });

  it('dedupes in-flight prefetch by loader id', () => {
    const first = prefetchRoute('/enc');
    const second = prefetchRoute('/enc/nodes');
    expect(first).toBe('enc');
    expect(second).toBe('enc');
    expect(prefetchRoute('/nope')).toBeNull();
  });

  it('idle list covers Classification and the fleet pages', () => {
    expect(IDLE_PREFETCH_PATHS).toEqual([
      '/nodes',
      '/enc',
      '/reports',
      '/certificates',
      '/deployment',
      '/insights',
    ]);
  });
});
