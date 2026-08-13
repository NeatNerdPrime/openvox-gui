/**
 * Clean Bolt / r10k / puppet agent TTY capture for display.
 *
 * Spinners are CR-overwritten frames (\\ | / -). Deleting CR concatenates them
 * into ``\\|/-\\|/-``. NUL shows as ``^@``.
 */
const SPINNER_ONLY = /^[\s\\|/.\-]+$/;
const SPINNER_RUN = /(?:\\\|\/\\-){2,}|(?:[\\|/.\-]){8,}/g;

export function cleanCliOutput(text: string | null | undefined): string {
  if (!text) return '';
  let s = String(text).replace(/\x00/g, '');
  s = s.replace(/\x1B\][^\x07\x1B]*(?:\x07|\x1B\\)/g, '');
  s = s.replace(/\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])/g, '');
  s = s.replace(/\x1B/g, '');
  s = s.replace(/\[[\d;?]{1,24}[ -/]*[@A-Za-z-~]/g, '');
  s = s.replace(/[\x01-\x08\x0B\x0C\x0E-\x1F\x7F]/g, '');
  s = s.replace(/\r\n/g, '\n').replace(/\r/g, '\n');
  const lines: string[] = [];
  let blank = false;
  for (let line of s.split('\n')) {
    const stripped = line.trim();
    if (SPINNER_ONLY.test(stripped)) continue;
    line = line.replace(SPINNER_RUN, '');
    if (SPINNER_ONLY.test(line.trim() || '')) continue;
    line = line.replace(/[ \t]+$/g, '');
    if (!line.trim()) {
      if (!blank) lines.push('');
      blank = true;
      continue;
    }
    lines.push(line);
    blank = false;
  }
  return lines.join('\n').replace(/^\n+|\n+$/g, '');
}
