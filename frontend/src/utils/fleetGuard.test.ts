import { describe, expect, it } from 'vitest';
import { fleetCount, isImplausibleFleetShrink } from './fleetGuard';

describe('fleetGuard', () => {
  it('counts list and dashboard shapes', () => {
    expect(fleetCount([{ certname: 'a' }, { certname: 'b' }])).toBe(2);
    expect(fleetCount({ nodes: [{}, {}, {}], node_status: { total: 3 } })).toBe(3);
  });

  it('rejects a 1-node probe against a real fleet', () => {
    const prev = Array.from({ length: 10 }, (_, i) => ({ certname: `n${i}` }));
    expect(isImplausibleFleetShrink([{ certname: 'x' }], prev)).toBe(true);
    expect(isImplausibleFleetShrink(prev, prev)).toBe(false);
  });
});
