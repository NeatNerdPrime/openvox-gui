/**
 * Shared Recharts defaults for OpenVox GUI performance.
 *
 * Recharts animates every series on mount/update by default. On pages that
 * render many Area/Line charts (Run Performance, Server/DB health, Monitoring
 * wallboard) that costs tens of ms of main-thread work *per chart* and is the
 * main reason graphs feel "laggy" after data arrives.
 *
 * Spread CHART_SERIES_PROPS onto Area / Line / Bar / Pie:
 *   <Area type="monotone" dataKey="x" {...CHART_SERIES_PROPS} />
 *
 * Prefer keeping animations off for operational dashboards; tooltips still work.
 */

/** Disable enter/update animations on series components. */
export const CHART_SERIES_PROPS = {
  isAnimationActive: false,
  animationDuration: 0,
} as const;

/** Safer default for dense live series — cap points before bind to Recharts. */
export const MAX_CHART_POINTS = 180;

/**
 * Downsample an ordered time series to at most *max* points (keep first/last,
 * stride the middle). Cheap and preserves trend shape for wallboard charts.
 */
export function downsampleSeries<T>(points: T[] | null | undefined, max = MAX_CHART_POINTS): T[] {
  if (!points || points.length === 0) return [];
  if (points.length <= max) return points;
  const out: T[] = [];
  const last = points.length - 1;
  const step = last / (max - 1);
  for (let i = 0; i < max; i++) {
    out.push(points[Math.round(i * step)]);
  }
  return out;
}

/** Linear interpolation — natural/monotone cubics overshoot noisy ops series. */
export const CHART_LINE_TYPE = 'linear' as const;

/**
 * Recharts 2 treats a string dataKey as a lodash path (`a.b` → obj.a.b).
 * Production certnames are FQDNs, so they must not be used as dataKeys.
 */
export function safeChartKey(id: string): string {
  return `k_${String(id).replace(/[^A-Za-z0-9]+/g, '_')}`;
}

export type TimedNodeRun = {
  time?: string;
  certname?: string;
  total?: number;
};

/**
 * Hourly averages keyed by safeChartKey(certname).
 * Every hour in the sample is a row so sparse production series still share an X axis.
 */
export function buildHourlyNodeSeries(
  runs: TimedNodeRun[] | null | undefined,
  certnames: string[],
): Array<Record<string, string | number | null>> {
  if (!runs?.length || !certnames.length) return [];
  const keys = certnames.map(safeChartKey);
  const nameToKey = new Map(certnames.map((n, i) => [n, keys[i]]));
  const hours = new Set<string>();
  const buckets: Record<string, Record<string, number[]>> = {};
  for (const run of runs) {
    const hour = (run.time || '').substring(0, 13);
    if (!hour) continue;
    hours.add(hour);
    const key = nameToKey.get(run.certname || '');
    if (!key) continue;
    const v = Number(run.total);
    if (!Number.isFinite(v)) continue;
    if (!buckets[hour]) buckets[hour] = {};
    if (!buckets[hour][key]) buckets[hour][key] = [];
    buckets[hour][key].push(v);
  }
  return [...hours].sort().map((hour) => {
    const point: Record<string, string | number | null> = { time: hour };
    for (const key of keys) {
      const vals = buckets[hour]?.[key];
      point[key] = vals?.length
        ? Number((vals.reduce((a, b) => a + b, 0) / vals.length).toFixed(2))
        : null;
    }
    return point;
  });
}

const TIME_KEYS = new Set([
  'time', 'timestamp', 'ts', 'hour', 'label', 'name', 'certname',
]);

/** Window length that tracks trend without washing out a short series. */
export function defaultMaWindow(n: number): number {
  if (n < 4) return 1;
  if (n < 12) return 3;
  if (n < 40) return 5;
  if (n < 120) return 7;
  return 11;
}

/**
 * Trailing simple moving average over *keys*.
 * Non-finite values are skipped in the window. Labels/time fields are copied through.
 */
export function movingAverageSeries<T extends Record<string, unknown>>(
  points: T[] | null | undefined,
  keys: string[],
  window?: number,
): T[] {
  if (!points || points.length === 0) return [];
  if (!keys.length) return points;
  const w = Math.max(1, window ?? defaultMaWindow(points.length));
  if (w === 1 || points.length < 2) return points;

  return points.map((row, i) => {
    const start = Math.max(0, i - w + 1);
    const next: Record<string, unknown> = { ...row };
    for (const key of keys) {
      let sum = 0;
      let count = 0;
      for (let j = start; j <= i; j++) {
        const v = points[j][key];
        if (typeof v === 'number' && Number.isFinite(v)) {
          sum += v;
          count += 1;
        }
      }
      if (count > 0) next[key] = sum / count;
    }
    return next as T;
  });
}

/**
 * SMA every numeric field except time/label keys. Use this before binding
 * live JMX / hourly trend rows to Recharts.
 */
export function smoothTimeSeries<T extends Record<string, unknown>>(
  points: T[] | null | undefined,
  window?: number,
): T[] {
  if (!points || points.length === 0) return [];
  const keys = new Set<string>();
  for (const row of points) {
    for (const [k, v] of Object.entries(row)) {
      if (TIME_KEYS.has(k)) continue;
      if (typeof v === 'number' && Number.isFinite(v)) keys.add(k);
    }
  }
  return movingAverageSeries(points, [...keys], window);
}
