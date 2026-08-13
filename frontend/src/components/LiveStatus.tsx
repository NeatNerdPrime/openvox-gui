/**
 * Quiet “the page is live” chip — AJAX refresh, not a full reload.
 */
import { Group, Text } from '@mantine/core';

export function LiveStatus({
  refreshing,
  live = true,
  updatedAt,
}: {
  refreshing?: boolean;
  live?: boolean;
  updatedAt?: Date | null;
}) {
  if (!live && !refreshing && !updatedAt) return null;
  return (
    <Group gap={8} wrap="nowrap">
      {(live || refreshing) && (
        <span
          className={`ov-live-dot${refreshing ? ' is-refreshing' : ''}`}
          aria-hidden
        />
      )}
      <Text size="xs" c="dimmed">
        {refreshing
          ? 'Updating…'
          : live
            ? (updatedAt ? `Live · ${updatedAt.toLocaleTimeString()}` : 'Live')
            : updatedAt
              ? `Updated ${updatedAt.toLocaleTimeString()}`
              : null}
      </Text>
    </Group>
  );
}
