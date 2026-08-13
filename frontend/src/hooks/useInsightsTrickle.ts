/**
 * Background trickle: keep Insights session cache warm so Node Health /
 * Compliance paint instantly and stay current while the operator is in the app.
 */
import { useEffect } from 'react';
import { metrics, dashboard } from '../services/api';
import { writeSessionCache } from '../utils/sessionCache';

const NODE_HEALTH_KEY = 'openvox_metrics_node_health_v1';
const COMPLIANCE_KEY = 'openvox_metrics_compliance_v2_24_';

async function warmOnce(): Promise<void> {
  if (typeof document !== 'undefined' && document.hidden) return;
  const jobs: Array<Promise<void>> = [
    metrics.nodeHealth()
      .then((d) => { writeSessionCache(NODE_HEALTH_KEY, d); })
      .catch(() => {}),
    metrics.compliance(24)
      .then((d) => { writeSessionCache(COMPLIANCE_KEY, d); })
      .catch(() => {}),
    dashboard.getData()
      .then((d) => { writeSessionCache('openvox_dashboard_data_v2', d); })
      .catch(() => {}),
  ];
  await Promise.allSettled(jobs);
}

/** Call from AppShell — runs immediately and every 45s while the tab is visible. */
export function useInsightsTrickle(intervalMs = 45000): void {
  useEffect(() => {
    void warmOnce();
    const id = window.setInterval(() => { void warmOnce(); }, Math.max(15000, intervalMs));
    const onVis = () => {
      if (!document.hidden) void warmOnce();
    };
    document.addEventListener('visibilitychange', onVis);
    return () => {
      window.clearInterval(id);
      document.removeEventListener('visibilitychange', onVis);
    };
  }, [intervalMs]);
}
