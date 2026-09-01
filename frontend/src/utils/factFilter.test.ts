import { describe, it, expect } from 'vitest';
import { collectLeaves, factValueMatches } from './factFilter';

describe('collectLeaves', () => {
  it('flattens hashes and arrays', () => {
    expect(collectLeaves({ family: 'RedHat', release: { major: '9' } })).toEqual([
      'RedHat',
      '9',
    ]);
  });
});

describe('factValueMatches', () => {
  it('empty filter matches everything', () => {
    expect(factValueMatches('RedHat', 'web01', '', '=')).toBe(true);
  });

  it('equals matches a scalar case-insensitively', () => {
    expect(factValueMatches('RedHat', 'web01', 'redhat', '=')).toBe(true);
    expect(factValueMatches('Debian', 'web01', 'redhat', '=')).toBe(false);
  });

  it('equals matches a leaf inside a structured fact', () => {
    expect(factValueMatches({ family: 'RedHat', name: 'Rocky' }, 'web01', 'RedHat', '=')).toBe(
      true,
    );
    expect(factValueMatches({ family: 'RedHat' }, 'web01', 'Debian', '=')).toBe(false);
  });

  it('contains matches certname or value', () => {
    expect(factValueMatches('Linux', 'web01.example.com', 'web01', 'contains')).toBe(true);
    expect(factValueMatches('Linux', 'db01', 'lin', 'contains')).toBe(true);
  });

  it('does not treat IPs as the number 10', () => {
    expect(factValueMatches('10.0.1.5', 'web01', '10.0.1.5', '=')).toBe(true);
    expect(factValueMatches('10.0.2.8', 'web01', '10.0.1.5', '=')).toBe(false);
    expect(factValueMatches('10.0.1.5', 'web01', '10', '=')).toBe(false);
  });

  it('compares whole numeric strings', () => {
    expect(factValueMatches(9, 'web01', '9', '=')).toBe(true);
    expect(factValueMatches('9', 'web01', '8', '>')).toBe(true);
    expect(factValueMatches(4, 'web01', '8', '>')).toBe(false);
  });
});
