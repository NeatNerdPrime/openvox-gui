/**
 * Console access mode (direct node FQDN vs VIP / load balancer).
 *
 * Populated from GET /api/auth/status. VIP mode raises the minimum
 * auto-refresh interval so multi-backend polling is gentler.
 */

export type AccessMode = 'direct' | 'vip';

export interface AccessModeState {
  accessMode: AccessMode;
  sessionTtlSeconds: number;
  sessionMinSeconds: number;
  vipPollFloorMs: number;
  requestHost: string;
  vipHostsConfigured: string[];
  loaded: boolean;
}

const DEFAULT_STATE: AccessModeState = {
  accessMode: 'direct',
  sessionTtlSeconds: 24 * 3600,
  sessionMinSeconds: 4 * 3600,
  vipPollFloorMs: 0,
  requestHost: typeof window !== 'undefined' ? window.location.hostname : '',
  vipHostsConfigured: [],
  loaded: false,
};

let state: AccessModeState = { ...DEFAULT_STATE };
const listeners = new Set<() => void>();

export function getAccessModeState(): AccessModeState {
  return state;
}

export function isVipAccess(): boolean {
  return state.accessMode === 'vip';
}

/** Effective poll interval: VIP enforces a floor; direct keeps caller value. */
export function effectivePollIntervalMs(requestedMs: number | undefined): number | undefined {
  if (requestedMs == null || requestedMs <= 0) return requestedMs;
  if (state.accessMode !== 'vip') return requestedMs;
  const floor = state.vipPollFloorMs > 0 ? state.vipPollFloorMs : 45000;
  return Math.max(requestedMs, floor);
}

export function subscribeAccessMode(cb: () => void): () => void {
  listeners.add(cb);
  return () => {
    listeners.delete(cb);
  };
}

function setState(next: Partial<AccessModeState>): void {
  state = { ...state, ...next, loaded: true };
  listeners.forEach((cb) => {
    try {
      cb();
    } catch {
      /* ignore */
    }
  });
}

/**
 * Load access mode from /api/auth/status (public). Idempotent.
 */
export async function loadAccessMode(): Promise<AccessModeState> {
  try {
    const response = await fetch('/api/auth/status', {
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
    });
    if (!response.ok) {
      setState({ accessMode: 'direct', vipPollFloorMs: 0 });
      return state;
    }
    const data = await response.json();
    const mode: AccessMode = data.access_mode === 'vip' ? 'vip' : 'direct';
    setState({
      accessMode: mode,
      sessionTtlSeconds: Number(data.session_ttl_seconds) || DEFAULT_STATE.sessionTtlSeconds,
      sessionMinSeconds: Number(data.session_min_seconds) || DEFAULT_STATE.sessionMinSeconds,
      vipPollFloorMs: mode === 'vip' ? Number(data.vip_poll_floor_ms) || 45000 : 0,
      requestHost: String(data.request_host || window.location.hostname),
      vipHostsConfigured: Array.isArray(data.vip_hosts_configured)
        ? data.vip_hosts_configured.map(String)
        : [],
    });
  } catch {
    setState({ accessMode: 'direct', vipPollFloorMs: 0 });
  }
  return state;
}
