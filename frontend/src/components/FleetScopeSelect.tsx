/**
 * Shared host-scope selector for Insights metrics (location + REGEX packs).
 */
import { useEffect, useMemo, useState } from 'react';
import { Group, Select, MultiSelect, Text, Badge, Loader } from '@mantine/core';
import { metrics } from '../services/api';

const SCOPE_KEY = 'openvox-gui-metric-scope-v1';

export type ScopeSelection = {
  scope: string;
  certnames?: string[];
};

export function loadStoredScope(): ScopeSelection {
  try {
    const raw = localStorage.getItem(SCOPE_KEY);
    if (!raw) return { scope: 'all' };
    const parsed = JSON.parse(raw) as ScopeSelection;
    if (parsed && typeof parsed.scope === 'string') return parsed;
  } catch {
    /* ignore */
  }
  return { scope: 'all' };
}

export function storeScope(sel: ScopeSelection) {
  try {
    localStorage.setItem(SCOPE_KEY, JSON.stringify(sel));
  } catch {
    /* ignore */
  }
}

type ScopeOption = {
  id: string;
  label: string;
  kind: string;
  count?: number | null;
  pattern?: string;
  location?: string;
};

export function FleetScopeSelect({
  value,
  onChange,
  size = 'sm',
  showCount = true,
}: {
  value: ScopeSelection;
  onChange: (v: ScopeSelection) => void;
  size?: 'xs' | 'sm' | 'md';
  showCount?: boolean;
}) {
  const [options, setOptions] = useState<ScopeOption[]>([]);
  const [allCertnames, setAllCertnames] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    metrics
      .scopes()
      .then((data: any) => {
        if (cancelled) return;
        setOptions(data.scopes || []);
      })
      .catch(() => {
        if (!cancelled) setOptions([{ id: 'all', label: 'All live fleet', kind: 'all' }]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    // Lazy-load certnames for custom multi-select from scopes isn't enough —
    // use inventory-ish path: scopes doesn't return all names. Fetch nodes list.
    import('../services/api').then(({ nodes }) => {
      nodes
        .list()
        .then((data: any) => {
          if (cancelled) return;
          const names = (Array.isArray(data) ? data : [])
            .map((n: any) => n.certname || n)
            .filter(Boolean)
            .sort((a: string, b: string) => a.localeCompare(b));
          setAllCertnames(names);
        })
        .catch(() => {});
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const selectData = useMemo(
    () =>
      options
        .filter((o) => o.id !== 'custom')
        .map((o) => ({
          value: o.id,
          label:
            showCount && o.count != null
              ? `${o.label} (${o.count})`
              : o.label,
        }))
        .concat([{ value: 'custom', label: 'Custom selection…' }]),
    [options, showCount]
  );

  const current = options.find((o) => o.id === value.scope);
  const isCustom = value.scope === 'custom';

  if (loading && selectData.length === 0) {
    return <Loader size="xs" />;
  }

  return (
    <Group gap="xs" align="flex-end" wrap="wrap">
      <Select
        size={size}
        label="Host scope"
        description="location fact or REGEX pack"
        data={selectData}
        value={value.scope || 'all'}
        onChange={(v) => {
          const next: ScopeSelection = { scope: v || 'all' };
          if (v === 'custom') next.certnames = value.certnames || [];
          onChange(next);
          storeScope(next);
        }}
        searchable
        allowDeselect={false}
        w={260}
      />
      {isCustom && (
        <MultiSelect
          size={size}
          label="Hosts"
          placeholder="Select certnames"
          data={allCertnames}
          value={value.certnames || []}
          onChange={(certnames) => {
            const next = { scope: 'custom', certnames };
            onChange(next);
            storeScope(next);
          }}
          searchable
          clearable
          w={360}
          maxDropdownHeight={280}
        />
      )}
      {current && current.kind !== 'custom' && current.count != null && showCount && (
        <Badge variant="light" color="blue" mb={4}>
          {current.count} hosts
        </Badge>
      )}
      {isCustom && (
        <Text size="xs" c="dimmed" mb={6}>
          {(value.certnames || []).length} selected
        </Text>
      )}
    </Group>
  );
}

/** Build query string fragment for metrics/performance APIs. */
export function scopeQuery(sel: ScopeSelection): string {
  const qs = new URLSearchParams();
  qs.set('scope', sel.scope || 'all');
  if (sel.scope === 'custom' && sel.certnames?.length) {
    qs.set('certnames', sel.certnames.join(','));
  }
  return qs.toString();
}
