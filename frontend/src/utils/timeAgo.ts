/** Relative timestamp for Nodes / Compliance / tooltips. */
export function timeAgo(
  timestamp: string | null | undefined,
  empty = 'Never',
): string {
  if (!timestamp) return empty;
  const diff = Date.now() - new Date(timestamp).getTime();
  if (Number.isNaN(diff)) return empty;
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'Just now';
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}
