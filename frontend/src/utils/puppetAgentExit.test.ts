import { describe, it, expect } from 'vitest';
import {
  isPuppetAgentSuccess,
  isPuppetAgentCommand,
} from './puppetAgentExit';

describe('isPuppetAgentSuccess', () => {
  it('treats 0 and 2 as success', () => {
    expect(isPuppetAgentSuccess(0)).toBe(true);
    expect(isPuppetAgentSuccess(2)).toBe(true);
  });

  it('treats other codes as failure', () => {
    expect(isPuppetAgentSuccess(1)).toBe(false);
    expect(isPuppetAgentSuccess(4)).toBe(false);
    expect(isPuppetAgentSuccess(null)).toBe(false);
    expect(isPuppetAgentSuccess(undefined)).toBe(false);
  });
});

describe('isPuppetAgentCommand', () => {
  it('matches common agent invocations', () => {
    expect(isPuppetAgentCommand('puppet agent -t')).toBe(true);
    expect(isPuppetAgentCommand('/opt/puppetlabs/bin/puppet agent -t')).toBe(true);
    expect(isPuppetAgentCommand('sudo -n env PUPPET_CONFDIR=/etc/puppetlabs/puppet /opt/puppetlabs/bin/puppet agent -t')).toBe(true);
    expect(isPuppetAgentCommand('puppet-agent --test')).toBe(true);
  });

  it('does not match unrelated commands', () => {
    expect(isPuppetAgentCommand('whoami')).toBe(false);
    expect(isPuppetAgentCommand('false')).toBe(false);
  });
});
