import { describe, expect, it } from 'vitest';
import {
  CACHE_ENC_CATALOG,
  CACHE_ENC_COMMON,
  CACHE_ENC_HIERARCHY,
  CACHE_ENC_NODES,
  CACHE_NODES,
} from './cacheKeys';

describe('cacheKeys', () => {
  it('keeps the versioned sessionStorage strings shared by warmup and pages', () => {
    expect(CACHE_NODES).toBe('openvox_nodes_v1');
    expect(CACHE_ENC_CATALOG).toBe('openvox_enc_catalog_v1');
    expect(CACHE_ENC_NODES).toBe('openvox_enc_nodes_v1');
    expect(CACHE_ENC_COMMON).toBe('openvox_enc_common_v1');
    expect(CACHE_ENC_HIERARCHY).toBe('openvox_enc_hierarchy_v1');
  });
});
