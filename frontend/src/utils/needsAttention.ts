/** Shared Needs-attention rule for Dashboard and Nodes. */

const STALE_MS = 24 * 3600 * 1000;

export function isNeedsAttention(
  node: {
    latest_report_status?: string | null;
    report_timestamp?: string | null;
  },
  now: number = Date.now(),
  staleMs: number = STALE_MS,
): boolean {
  const st = (node.latest_report_status || '').toLowerCase();
  if (!st || st === 'failed' || st === 'unreported') return true;
  const ts = node.report_timestamp ? new Date(node.report_timestamp).getTime() : 0;
  return Boolean(ts) && ts < now - staleMs;
}
