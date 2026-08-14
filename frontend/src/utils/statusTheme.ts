/**
 * Single status contract for badges, chips, rings, and charts.
 * changed = successful apply with changes (attention, not an incident).
 */
export const STATUS_MANTINE: Record<string, string> = {
  unchanged: 'teal',
  changed: 'orange',
  failed: 'red',
  unreported: 'gray',
  noop: 'blue',
  active: 'teal',
  inactive: 'red',
  unknown: 'gray',
};

export const STATUS_HEX: Record<string, string> = {
  unchanged: '#12b886',
  changed: '#e67700',
  failed: '#e03131',
  unreported: '#868e96',
  noop: '#228be6',
  compliant: '#12b886',
  drifted: '#e67700',
};

export const STATUS_FILTER_CHIPS = [
  { value: 'failed', label: 'Failed', color: 'red' },
  { value: 'changed', label: 'Changed', color: 'orange' },
  { value: 'unchanged', label: 'Unchanged', color: 'teal' },
  { value: 'unreported', label: 'Unreported', color: 'gray' },
  { value: 'noop', label: 'Noop', color: 'blue' },
];

export function statusMantine(status: string | null | undefined): string {
  const s = (status || 'unreported').toString().toLowerCase();
  return STATUS_MANTINE[s] || STATUS_MANTINE.unknown;
}
