/**
 * OpenVox GUI - StatusBadge.tsx
 * 
 * Component documentation to be expanded.
 */
import { Badge } from '@mantine/core';
import { statusMantine } from '../utils/statusTheme';

interface StatusBadgeProps {
  status: string | null | undefined;
  size?: 'xs' | 'sm' | 'md' | 'lg' | 'xl';
}

export function StatusBadge({ status, size = 'sm' }: StatusBadgeProps) {
  const s = (status || '').toString().toLowerCase() || 'unreported';
  const label = s === 'unreported' || s === 'unknown' ? 'unreported' : s;
  return (
    <Badge
      color={statusMantine(label)}
      variant="light"
      size={size}
      tt="capitalize"
      fw={600}
    >
      {label}
    </Badge>
  );
}
