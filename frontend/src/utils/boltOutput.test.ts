import { describe, it, expect } from 'vitest';
import { parseBoltJsonPayload, formatBoltItemsAsHuman } from './boltOutput';

const messy = `
\x00{ "items": [
all authorization methods failed (tried none, publickey, password)
{"target":"ok.example.com","action":"command","object":"whoami","status":"success","value":{"stdout":"bolt\\r\\n","stderr":"","exit_code":0}}
,
{"target":"bad.example.com","action":"command","object":null,"status":"failure","value":{"_error":{"msg":"Authentication failed for user bolt@bad.example.com","issue_code":"AUTH_ERROR"}}}
],
"target_count": 2, "elapsed_time": 10 }
`;

describe('parseBoltJsonPayload', () => {
  it('extracts items when SSH auth noise is mixed into the JSON', () => {
    const parsed = parseBoltJsonPayload(messy);
    expect(parsed).not.toBeNull();
    expect(parsed!.items).toHaveLength(2);
    expect(parsed!.items.map((i) => i.target)).toEqual([
      'ok.example.com',
      'bad.example.com',
    ]);
  });
});

describe('formatBoltItemsAsHuman', () => {
  it('does not dump raw JSON', () => {
    const parsed = parseBoltJsonPayload(messy)!;
    const human = formatBoltItemsAsHuman(parsed.items, parsed.meta);
    expect(human).not.toContain('"items"');
    expect(human).toContain('Successful on 1 / 2');
    expect(human).toContain('Failed on bad.example.com');
    expect(human).toContain('Finished on ok.example.com');
    expect(human).toContain('bolt');
  });

  it('treats Puppet agent exit 2 as success even when Bolt status is failure', () => {
    const items = [
      {
        target: '1pass-vault-bot.example.com',
        action: 'command',
        object: '/opt/puppetlabs/bin/puppet agent -t',
        status: 'failure',
        value: {
          exit_code: 2,
          stdout: 'Notice: Applied catalog in 3.14 seconds',
          stderr: '',
          _error: { msg: 'The command failed with exit code 2' },
        },
      },
    ];
    const human = formatBoltItemsAsHuman(items);
    expect(human).toContain('Successful on 1 / 1');
    expect(human).toContain('Finished on 1pass-vault-bot.example.com');
    expect(human).toContain('changes applied');
    expect(human).not.toContain('Failed on');
    expect(human).not.toContain('The command failed with exit code 2');
  });
});
