/** Reject a VIP-flap payload that would replace a real fleet with 1 node. */

export function fleetCount(value: unknown): number {
  if (Array.isArray(value)) return value.length;
  if (value && typeof value === 'object') {
    const v = value as { nodes?: unknown; node_status?: { total?: number } };
    if (Array.isArray(v.nodes) && v.nodes.length) return v.nodes.length;
    const t = Number(v.node_status?.total);
    return Number.isFinite(t) ? t : 0;
  }
  return 0;
}

export function isImplausibleFleetShrink(next: unknown, prev: unknown): boolean {
  const oldN = fleetCount(prev);
  const newN = fleetCount(next);
  if (oldN < 3 || newN >= oldN) return false;
  if (newN <= 1) return true;
  return newN < Math.max(2, Math.floor(oldN * 0.5));
}
