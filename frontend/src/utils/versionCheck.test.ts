import { describe, expect, it, vi } from 'vitest';

vi.mock('@mantine/notifications', () => ({
  notifications: { show: vi.fn() },
}));

import { isChunkLoadError } from './versionCheck';

describe('isChunkLoadError', () => {
  it('detects Vite / webpack chunk-load failures', () => {
    expect(isChunkLoadError({ message: 'Failed to fetch dynamically imported module' })).toBe(true);
    expect(isChunkLoadError({ message: 'Loading chunk 12 failed' })).toBe(true);
    expect(isChunkLoadError({ name: 'ChunkLoadError' })).toBe(true);
    expect(isChunkLoadError({ message: 'NetworkError' })).toBe(false);
    expect(isChunkLoadError(null)).toBe(false);
  });
});
