/**
 * Puppet / OpenVox agent exit codes the GUI treats as a successful run.
 * 0 = no changes, 2 = changes applied. Anything else is a failure.
 */
export const PUPPET_AGENT_SUCCESS_EXIT_CODES = [0, 2] as const;

export function isPuppetAgentSuccess(rc: number | null | undefined): boolean {
  return rc === 0 || rc === 2;
}

export function isPuppetAgentCommand(command: string | null | undefined): boolean {
  return /puppet(\s|-)+agent/i.test(String(command || ''));
}
