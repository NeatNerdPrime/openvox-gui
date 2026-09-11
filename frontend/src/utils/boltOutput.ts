/** Parse Bolt --format json even when SSH noise is mixed in. */
import { isPuppetAgentCommand, isPuppetAgentSuccess } from './puppetAgentExit';
import { cleanCliOutput } from './cleanCliOutput';

export type BoltItem = {
  target?: string;
  action?: string;
  object?: string;
  status?: string;
  value?: {
    stdout?: string;
    stderr?: string;
    merged_output?: string;
    exit_code?: number;
    _error?: { msg?: string; kind?: string; issue_code?: string };
  };
};

const AUTH_NOISE = /all authorization methods failed[^\n]*/gi;

function stripNoise(text: string): string {
  return String(text || '')
    .replace(/\x00/g, '')
    .replace(AUTH_NOISE, '')
    .trim();
}

function extractJsonObjectsWithTarget(text: string): BoltItem[] {
  const items: BoltItem[] = [];
  const hay = text;
  let i = 0;
  while (i < hay.length) {
    const start = hay.indexOf('{"target"', i);
    if (start < 0) break;
    let depth = 0;
    let inStr = false;
    let esc = false;
    let end = -1;
    for (let j = start; j < hay.length; j++) {
      const c = hay[j];
      if (inStr) {
        if (esc) {
          esc = false;
        } else if (c === '\\') {
          esc = true;
        } else if (c === '"') {
          inStr = false;
        }
        continue;
      }
      if (c === '"') {
        inStr = true;
        continue;
      }
      if (c === '{') depth += 1;
      else if (c === '}') {
        depth -= 1;
        if (depth === 0) {
          end = j;
          break;
        }
      }
    }
    if (end < 0) break;
    const slice = hay.slice(start, end + 1);
    try {
      const obj = JSON.parse(slice);
      if (obj && typeof obj === 'object' && obj.target) items.push(obj);
    } catch {
      /* skip */
    }
    i = end + 1;
  }
  return items;
}

export function parseBoltJsonPayload(
  outputText: string,
): { items: BoltItem[]; meta?: any } | null {
  const text = stripNoise(outputText);
  if (!text) return null;

  const tryParse = (raw: string) => {
    const data = JSON.parse(raw);
    if (data && Array.isArray(data.items)) return { items: data.items as BoltItem[], meta: data };
    if (Array.isArray(data)) return { items: data as BoltItem[], meta: { items: data } };
    return null;
  };

  try {
    const got = tryParse(text);
    if (got) return got;
  } catch {
    /* mixed SSH noise */
  }

  const start = text.indexOf('{');
  const end = text.lastIndexOf('}');
  if (start >= 0 && end > start) {
    try {
      const got = tryParse(text.slice(start, end + 1));
      if (got) return got;
    } catch {
      /* still mixed */
    }
  }

  const items = extractJsonObjectsWithTarget(text);
  if (!items.length) return null;
  return { items, meta: { items, target_count: items.length } };
}

function boltItemSucceeded(item: BoltItem): boolean {
  const statusOk = (item.status || '').toLowerCase() === 'success';
  const cmd = String(item.object || '');
  const exitCode = item.value?.exit_code;
  if (isPuppetAgentCommand(cmd) && isPuppetAgentSuccess(exitCode)) {
    return true;
  }
  return statusOk;
}

/** True when Bolt items are a puppet agent run (object or exit 0/2). */
export function boltItemsArePuppetAgent(items: BoltItem[]): boolean {
  return items.some(
    (i) =>
      isPuppetAgentCommand(String(i.object || '')) ||
      isPuppetAgentSuccess(i.value?.exit_code),
  );
}

/**
 * CLI-shaped puppet agent output: Info/Notice/Error lines from stdout.
 * Drops the Bolt JSON wrapper. Use this on success; keep JSON for errors.
 */
export function formatPuppetAgentConsole(outputText: string): string {
  const parsed = parseBoltJsonPayload(outputText);
  if (!parsed?.items.length) {
    const cleaned = cleanCliOutput(outputText);
    if (cleaned.trim().startsWith('{') && cleaned.includes('"items"')) {
      return '';
    }
    return cleaned;
  }
  return parsed.items
    .map((item) => {
      const val = item.value || {};
      return cleanCliOutput(String(val.stdout || val.merged_output || ''));
    })
    .filter(Boolean)
    .join('\n\n')
    .trim();
}

export function formatBoltItemsAsHuman(
  items: BoltItem[],
  meta?: any,
): string {
  if (!items.length) return '';
  const ok = items.filter((i) => boltItemSucceeded(i));
  const fail = items.filter((i) => !boltItemSucceeded(i));
  const lines: string[] = [
    `Successful on ${ok.length} / ${items.length} target(s)` +
      (fail.length ? `, failed on ${fail.length}` : '') +
      (meta?.elapsed_time != null ? ` (${meta.elapsed_time}s)` : ''),
    '',
  ];

  const show = [...fail, ...ok];
  for (const item of show) {
    const target = item.target || '(unknown)';
    const val = item.value || {};
    const succeeded = boltItemSucceeded(item);
    const stdout = String(val.stdout || val.merged_output || '').replace(/\x00/g, '').trim();
    const stderr = String(val.stderr || '').replace(/\x00/g, '').trim();
    const errMsg = val._error?.msg ? String(val._error.msg).trim() : '';
    if (succeeded) {
      const extra = val.exit_code === 2 ? ' (changes applied; Puppet exit 2 = success)' : '';
      lines.push(`Finished on ${target}${extra}`);
    } else {
      lines.push(`Failed on ${target}`);
    }
    if (!succeeded && errMsg) lines.push(`  ${errMsg}`);
    if (stdout && succeeded) lines.push(`  ${stdout.replace(/\s+/g, ' ')}`);
    if (stderr && !errMsg.includes(stderr)) lines.push(`  ${stderr}`);
    if (val.exit_code != null && !succeeded) {
      lines.push(`  exit ${val.exit_code}`);
    }
    lines.push('');
  }
  return lines.join('\n').trim();
}
