/**
 * Session gate — single-flight handling of HTTP 401 for the SPA.
 *
 * Before 3.12, every fetchJSON 401 did window.location.reload(), which
 * behind a multi-console VIP turned intermittent backend 401s into a
 * full-page refresh / logout storm.
 *
 * Policy:
 *   1. Pause (callers stop polling via isSessionSuspect / isSessionExpired)
 *   2. Probe GET /api/auth/me once (no reload)
 *   3. If still unauthenticated → notify listeners once (AuthContext → login)
 *   4. If probe OK → clear suspect flag (transient blip / peer recovered)
 */

type SessionListener = (event: 'expired' | 'recovered') => void;

let handling = false;
let expired = false;
let suspect = false;
const listeners = new Set<SessionListener>();

export function onSessionEvent(cb: SessionListener): () => void {
  listeners.add(cb);
  return () => {
    listeners.delete(cb);
  };
}

export function isSessionExpired(): boolean {
  return expired;
}

export function isSessionSuspect(): boolean {
  return suspect || expired;
}

/** Call after a successful login so polls resume. */
export function resetSessionGate(): void {
  handling = false;
  expired = false;
  suspect = false;
}

function emit(event: 'expired' | 'recovered'): void {
  listeners.forEach((cb) => {
    try {
      cb(event);
    } catch {
      /* ignore listener errors */
    }
  });
}

/**
 * Handle a 401 from an authenticated API call.
 * Safe to call concurrently — only one probe runs.
 */
export async function handleUnauthorized(): Promise<void> {
  if (expired) return;
  if (handling) {
    // Wait briefly for the in-flight probe rather than stacking reloads.
    const start = Date.now();
    while (handling && Date.now() - start < 8000) {
      await new Promise((r) => setTimeout(r, 50));
    }
    return;
  }

  handling = true;
  suspect = true;

  try {
    const response = await fetch('/api/auth/me', {
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
    });
    if (response.ok) {
      suspect = false;
      handling = false;
      emit('recovered');
      return;
    }
  } catch {
    // Network blip — do not force logout; leave suspect so polls pause
    // until the next successful call clears it via reset or recovery.
    handling = false;
    return;
  }

  expired = true;
  suspect = true;
  try {
    localStorage.removeItem('openvox_token');
  } catch {
    /* ignore */
  }
  handling = false;
  emit('expired');
}
