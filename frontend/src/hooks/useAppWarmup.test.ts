import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const getAvailableClasses = vi.fn();
const listNodes = vi.fn();
const listGroups = vi.fn();
const listEnvironments = vi.fn();
const listEncNodes = vi.fn();
const getCommon = vi.fn();
const getHierarchy = vi.fn();

vi.mock('../services/api', () => ({
  enc: {
    getAvailableClasses: (...args: unknown[]) => getAvailableClasses(...args),
    listGroups: (...args: unknown[]) => listGroups(...args),
    listEnvironments: (...args: unknown[]) => listEnvironments(...args),
    listNodes: (...args: unknown[]) => listEncNodes(...args),
    getCommon: (...args: unknown[]) => getCommon(...args),
    getHierarchy: (...args: unknown[]) => getHierarchy(...args),
  },
  nodes: {
    list: (...args: unknown[]) => listNodes(...args),
  },
}));

import {
  CACHE_ENC_CATALOG,
  CACHE_ENC_COMMON,
  CACHE_ENC_HIERARCHY,
  CACHE_ENC_NODES,
  CACHE_NODES,
} from '../utils/cacheKeys';
import { clearEncClassCache, readEncClassCache } from '../utils/encClassCache';
import { clearSessionCache, readSessionCache } from '../utils/sessionCache';
import { resetSessionGate } from '../utils/sessionGate';
import { warmSessionCaches } from './useAppWarmup';

const FLEET = [
  { certname: 'web01.example.com', status: 'unchanged' },
  { certname: 'db01.example.com', status: 'changed' },
];
const GROUPS = [{ name: 'web' }, { name: 'db' }];
const ENVS = [{ name: 'production' }, { name: 'staging' }];
const CLASSIFIED = [{ certname: 'web01.example.com', environment: 'production' }];
const COMMON = { classes: { 'profile::base': {} }, parameters: {} };
const HIERARCHY = { layers: ['common', 'environment', 'group', 'node'] };
const CLASSES = {
  roles: ['role::web'],
  profiles: ['profile::base'],
  modules: [],
  all: ['role::web', 'profile::base'],
  message: null,
  source: 'compiler',
  host: 'ovcompiler1.example.com',
};

function setPath(path: string): void {
  window.history.replaceState({}, '', path);
}

describe('warmSessionCaches', () => {
  beforeEach(() => {
    resetSessionGate();
    clearEncClassCache();
    [
      CACHE_NODES,
      CACHE_ENC_CATALOG,
      CACHE_ENC_NODES,
      CACHE_ENC_COMMON,
      CACHE_ENC_HIERARCHY,
    ].forEach((key) => clearSessionCache(key));
    listNodes.mockResolvedValue(FLEET);
    listGroups.mockResolvedValue(GROUPS);
    listEnvironments.mockResolvedValue(ENVS);
    listEncNodes.mockResolvedValue(CLASSIFIED);
    getCommon.mockResolvedValue(COMMON);
    getHierarchy.mockResolvedValue(HIERARCHY);
    getAvailableClasses.mockResolvedValue(CLASSES);
    setPath('/reports');
    Object.defineProperty(document, 'hidden', { configurable: true, value: false });
  });

  afterEach(() => {
    vi.clearAllMocks();
    resetSessionGate();
    clearEncClassCache();
  });

  it('seeds fleet, ENC catalog, and class-picker caches', async () => {
    await warmSessionCaches();

    expect(readSessionCache(CACHE_NODES)).toEqual(FLEET);
    expect(readSessionCache(CACHE_ENC_CATALOG)).toEqual({ groups: GROUPS, envs: ENVS });
    expect(readSessionCache(CACHE_ENC_NODES)).toEqual(CLASSIFIED);
    expect(readSessionCache(CACHE_ENC_COMMON)).toEqual(COMMON);
    expect(readSessionCache(CACHE_ENC_HIERARCHY)).toEqual(HIERARCHY);
    expect(readEncClassCache('production')).toEqual(CLASSES);
    expect(listNodes).toHaveBeenCalledTimes(1);
    expect(getAvailableClasses).toHaveBeenCalledWith('production', undefined);
  });

  it('skips the fleet fetch when already on /nodes', async () => {
    setPath('/nodes');
    await warmSessionCaches();
    expect(listNodes).not.toHaveBeenCalled();
    expect(readSessionCache(CACHE_NODES)).toBeNull();
    expect(readSessionCache(CACHE_ENC_CATALOG)).toEqual({ groups: GROUPS, envs: ENVS });
  });

  it('skips ENC catalog fetches on /enc', async () => {
    setPath('/enc');
    await warmSessionCaches();
    expect(listGroups).not.toHaveBeenCalled();
    expect(readSessionCache(CACHE_ENC_CATALOG)).toBeNull();
    expect(readSessionCache(CACHE_NODES)).toEqual(FLEET);
    expect(readEncClassCache('production')).toEqual(CLASSES);
  });

  it('does nothing when the tab is hidden', async () => {
    Object.defineProperty(document, 'hidden', { configurable: true, value: true });
    await warmSessionCaches();
    expect(listNodes).not.toHaveBeenCalled();
    expect(getAvailableClasses).not.toHaveBeenCalled();
  });
});
