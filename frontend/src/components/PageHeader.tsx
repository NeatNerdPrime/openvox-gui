/**
 * Consistent page title row used across operator surfaces.
 */
import { ReactNode } from 'react';
import { Group, Stack, Text, Title } from '@mantine/core';
import { LiveStatus } from './LiveStatus';

export function PageHeader({
  title,
  description,
  live,
  refreshing,
  updatedAt,
  extra,
}: {
  title: string;
  description?: string;
  live?: boolean;
  refreshing?: boolean;
  updatedAt?: Date | null;
  extra?: ReactNode;
}) {
  return (
    <Group justify="space-between" align="flex-start" mb="md" wrap="wrap" gap="sm">
      <Stack gap={4}>
        <Group gap="sm" align="center">
          <Title order={2}>{title}</Title>
          <LiveStatus live={live} refreshing={refreshing} updatedAt={updatedAt} />
        </Group>
        {description && (
          <Text size="sm" c="dimmed" maw={640}>
            {description}
          </Text>
        )}
      </Stack>
      {extra ? <Group gap="sm">{extra}</Group> : null}
    </Group>
  );
}
