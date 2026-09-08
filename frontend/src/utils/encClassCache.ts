/**
 * In-memory TTL for ENC class-picker lists.
 * Backend already caches ~90s; this avoids a round-trip when opening another modal.
 */
import { enc } from '../services/api';

const TTL_MS = 90_000;
const cache = new Map<string, { at: number; data: unknown }>();
const inflight = new Map<string, Promise<unknown>>();

export function readEncClassCache<T = unknown>(environment: string): T | null {
  const env = (environment || 'production').trim() || 'production';
  const hit = cache.get(env);
  if (!hit) return null;
  if (Date.now() - hit.at > TTL_MS) {
    cache.delete(env);
    return null;
  }
  return hit.data as T;
}

export function writeEncClassCache(environment: string, data: unknown): void {
  const env = (environment || 'production').trim() || 'production';
  cache.set(env, { at: Date.now(), data });
}

export function clearEncClassCache(): void {
  cache.clear();
  inflight.clear();
}

export async function loadAvailableClasses(
  environment = 'production',
  signal?: AbortSignal,
): Promise<any> {
  const env = (environment || 'production').trim() || 'production';
  const cached = readEncClassCache<any>(env);
  if (cached != null) return cached;
  const pending = inflight.get(env);
  if (pending) return pending;
  const req = enc.getAvailableClasses(env, signal)
    .then((data) => {
      if (!signal?.aborted) writeEncClassCache(env, data);
      return data;
    })
    .finally(() => {
      inflight.delete(env);
    });
  inflight.set(env, req);
  return req;
}
