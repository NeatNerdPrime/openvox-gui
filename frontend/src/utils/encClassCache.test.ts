import { afterEach, describe, expect, it, vi } from 'vitest';

const getAvailableClasses = vi.fn();

vi.mock('../services/api', () => ({
  enc: {
    getAvailableClasses: (...args: unknown[]) => getAvailableClasses(...args),
  },
}));

import {
  clearEncClassCache,
  loadAvailableClasses,
  readEncClassCache,
  writeEncClassCache,
} from './encClassCache';

const PRODUCTION_CLASSES = {
  roles: ['role::web'],
  profiles: ['profile::base'],
  modules: ['apache'],
  all: ['role::web', 'profile::base', 'apache'],
  message: null,
  source: 'compiler',
  host: 'ovcompiler1.example.com',
};

const STAGING_CLASSES = {
  roles: ['role::db'],
  profiles: [],
  modules: [],
  all: ['role::db'],
  message: null,
  source: 'compiler',
  host: 'ovcompiler1.example.com',
};

describe('encClassCache', () => {
  afterEach(() => {
    clearEncClassCache();
    getAvailableClasses.mockReset();
    vi.useRealTimers();
  });

  it('round-trips by environment', () => {
    writeEncClassCache('production', { all: ['role::web'] });
    expect(readEncClassCache<{ all: string[] }>('production')).toEqual({ all: ['role::web'] });
    expect(readEncClassCache('staging')).toBeNull();
  });

  it('treats blank and whitespace env as production', () => {
    writeEncClassCache('   ', { all: ['profile::base'] });
    expect(readEncClassCache<{ all: string[] }>('production')?.all).toEqual(['profile::base']);
    expect(readEncClassCache<{ all: string[] }>('')?.all).toEqual(['profile::base']);
  });

  it('expires after 90s', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-09-08T12:00:00Z'));
    writeEncClassCache('production', PRODUCTION_CLASSES);
    vi.setSystemTime(new Date('2026-09-08T12:01:31Z'));
    expect(readEncClassCache('production')).toBeNull();
  });

  it('loadAvailableClasses hits the API once per environment', async () => {
    getAvailableClasses
      .mockResolvedValueOnce(PRODUCTION_CLASSES)
      .mockResolvedValueOnce(STAGING_CLASSES);

    const first = await loadAvailableClasses('production');
    const second = await loadAvailableClasses('production');
    const staging = await loadAvailableClasses('staging');

    expect(first).toEqual(PRODUCTION_CLASSES);
    expect(second).toEqual(PRODUCTION_CLASSES);
    expect(staging).toEqual(STAGING_CLASSES);
    expect(getAvailableClasses).toHaveBeenCalledTimes(2);
    expect(getAvailableClasses).toHaveBeenNthCalledWith(1, 'production', undefined);
    expect(getAvailableClasses).toHaveBeenNthCalledWith(2, 'staging', undefined);
    expect(readEncClassCache('production')).toEqual(PRODUCTION_CLASSES);
  });

  it('does not cache an aborted fetch', async () => {
    let resolveFn: (value: typeof PRODUCTION_CLASSES) => void = () => {};
    getAvailableClasses.mockImplementation(
      () => new Promise((resolve) => { resolveFn = resolve; }),
    );
    const ac = new AbortController();
    const pending = loadAvailableClasses('production', ac.signal);
    ac.abort();
    resolveFn(PRODUCTION_CLASSES);
    await pending;
    expect(readEncClassCache('production')).toBeNull();
  });
});
