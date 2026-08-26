import { describe, expect, it } from 'vitest';
import { cleanCliOutput } from './cleanCliOutput';

describe('cleanCliOutput', () => {
  it('returns empty for nullish input', () => {
    expect(cleanCliOutput(null)).toBe('');
    expect(cleanCliOutput(undefined)).toBe('');
  });

  it('strips ANSI color and NUL bytes', () => {
    expect(cleanCliOutput('\x1b[31mred\x1b[0m')).toBe('red');
    expect(cleanCliOutput('ok\x00done')).toBe('okdone');
  });

  it('drops spinner-only lines and collapses blank runs', () => {
    const raw = 'start\n|/\n\n\nend\n';
    expect(cleanCliOutput(raw)).toBe('start\n\nend');
  });
});
