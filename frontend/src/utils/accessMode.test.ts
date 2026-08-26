import { afterEach, describe, expect, it, vi } from 'vitest';
import { effectivePollIntervalMs, loadAccessMode } from './accessMode';

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('effectivePollIntervalMs', () => {
  it('passes through requested intervals when access is direct', () => {
    expect(effectivePollIntervalMs(15000)).toBe(15000);
    expect(effectivePollIntervalMs(undefined)).toBeUndefined();
  });

  it('raises the interval to the VIP floor', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          access_mode: 'vip',
          vip_poll_floor_ms: 45000,
          session_ttl_seconds: 86400,
          session_min_seconds: 14400,
          request_host: 'openvox.example.com',
          vip_hosts_configured: ['openvox.example.com'],
        }),
      }),
    );
    await loadAccessMode();
    expect(effectivePollIntervalMs(15000)).toBe(45000);
    expect(effectivePollIntervalMs(60000)).toBe(60000);
  });
});
