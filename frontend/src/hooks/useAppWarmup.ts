/**
 * After login: prefetch common JS chunks and seed session caches so
 * Classification / Nodes / Reports paint last-good data immediately.
 */
import { useEffect } from 'react';
import { enc, nodes } from '../services/api';
import {
  CACHE_ENC_CATALOG,
  CACHE_ENC_COMMON,
  CACHE_ENC_HIERARCHY,
  CACHE_ENC_NODES,
  CACHE_NODES,
} from '../utils/cacheKeys';
import { loadAvailableClasses } from '../utils/encClassCache';
import { prefetchIdleRoutes } from '../utils/routePrefetch';
import { writeSessionCache } from '../utils/sessionCache';
import { isSessionSuspect } from '../utils/sessionGate';

function isEncPath(path: string): boolean {
  return path === '/enc' || path.startsWith('/enc/');
}

export async function warmSessionCaches(): Promise<void> {
  if (typeof document !== 'undefined' && document.hidden) return;
  if (isSessionSuspect()) return;
  const path = typeof window !== 'undefined' ? window.location.pathname : '';

  const jobs: Array<Promise<void>> = [];

  if (path !== '/nodes') {
    jobs.push(
      nodes.list()
        .then((d) => { if (Array.isArray(d)) writeSessionCache(CACHE_NODES, d); })
        .catch(() => {}),
    );
  }

  if (!isEncPath(path)) {
    jobs.push(
      Promise.all([
        enc.listGroups().catch(() => null),
        enc.listEnvironments().catch(() => null),
        enc.listNodes().catch(() => null),
        enc.getCommon().catch(() => null),
        enc.getHierarchy().catch(() => null),
      ]).then(([groups, envs, classified, common, hierarchy]) => {
        if (Array.isArray(groups) && Array.isArray(envs)) {
          writeSessionCache(CACHE_ENC_CATALOG, { groups, envs });
        }
        if (Array.isArray(classified)) writeSessionCache(CACHE_ENC_NODES, classified);
        if (common) writeSessionCache(CACHE_ENC_COMMON, common);
        if (hierarchy) writeSessionCache(CACHE_ENC_HIERARCHY, hierarchy);
      }),
    );
  }

  // Class picker is the slow ENC modal path (compiler HTTP / Bolt). Pay once idle.
  jobs.push(loadAvailableClasses('production').then(() => undefined).catch(() => {}));

  await Promise.allSettled(jobs);
}

/** Call from AppShell once the operator is authenticated. */
export function useAppWarmup(): void {
  useEffect(() => {
    prefetchIdleRoutes();
    const id = window.setTimeout(() => { void warmSessionCaches(); }, 600);
    return () => window.clearTimeout(id);
  }, []);
}
