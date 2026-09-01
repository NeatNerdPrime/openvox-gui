/** Match Fact Explorer Filter Value against a node fact. */

const STRICT_NUMBER = /^-?\d+(\.\d+)?$/;

export function collectLeaves(value: unknown): unknown[] {
  if (value === null || value === undefined) return [value];
  if (Array.isArray(value)) return value.flatMap(collectLeaves);
  if (typeof value === 'object') return Object.values(value as Record<string, unknown>).flatMap(collectLeaves);
  return [value];
}

function asDisplayString(value: unknown): string {
  if (value === null || value === undefined) return '';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

/**
 * True when this node's fact value (or certname, for contains) matches
 * the operator + filter box. Leaf values of hashes/arrays are compared
 * so `os` + `=` + `RedHat` still hits `os.family`.
 */
export function factValueMatches(
  value: unknown,
  certname: string,
  query: string,
  op: string,
): boolean {
  const q = (query || '').trim();
  if (!q) return true;

  const leaves = collectLeaves(value);
  const valStr = asDisplayString(value);
  const qLower = q.toLowerCase();

  if (op === 'contains') {
    if ((certname || '').toLowerCase().includes(qLower)) return true;
    if (valStr.toLowerCase().includes(qLower)) return true;
    return leaves.some((leaf) => String(leaf ?? '').toLowerCase().includes(qLower));
  }

  const qIsNum = STRICT_NUMBER.test(q);
  if (qIsNum) {
    const qn = Number(q);
    const nums = leaves
      .map((leaf) => {
        if (typeof leaf === 'number' && Number.isFinite(leaf)) return leaf;
        const s = String(leaf ?? '').trim();
        return STRICT_NUMBER.test(s) ? Number(s) : NaN;
      })
      .filter((n) => !Number.isNaN(n));
    if (nums.length > 0) {
      switch (op) {
        case '>':
          return nums.some((n) => n > qn);
        case '>=':
          return nums.some((n) => n >= qn);
        case '<':
          return nums.some((n) => n < qn);
        case '<=':
          return nums.some((n) => n <= qn);
        case '=':
          return nums.some((n) => n === qn);
        case '!=':
          return nums.every((n) => n !== qn);
        default:
          break;
      }
    }
  }

  const leafStrs = leaves.map((leaf) => String(leaf ?? '').toLowerCase().trim());
  if (op === '=') {
    return leafStrs.some((s) => s === qLower) || valStr.toLowerCase().trim() === qLower;
  }
  if (op === '!=') {
    return leafStrs.every((s) => s !== qLower) && valStr.toLowerCase().trim() !== qLower;
  }
  return false;
}
