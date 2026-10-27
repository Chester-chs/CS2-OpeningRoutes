import { describe, expect, it } from 'vitest';
import { filterThrows, pistolSummary, visibleRounds, mediaUrl } from '../src/data';
import type { Catalog } from '../src/types';

const data = {schema_version: 1, matches: [{id:'m', map:'de_test', source:{verified:true, event:'Synthetic', match:'A v B', date:'2025-01-01'}}],
  throws:[{id:'t', round_id:'r', match_id:'m', map:'de_test', kind:'smoke', side:'CT', player:'Alice', team:'A', time:70, teaching:{area:'Mid'}}],
  rounds:[{id:'r', match_id:'m', number:1, is_pistol:true, complete:true, winner:'T', equipment:[{player:'Alice', side:'CT', team:'A',inventory:['Smoke Grenade']}]}], plans:[]} as unknown as Catalog;

describe('shared desktop and web query rules', () => {
  it('finds later throws without a 30 second cutoff', () => {
    expect(filterThrows(data, {query:'Alice', side:'CT'}).length).toBe(1);
    expect(filterThrows(data, {query:'missing'}).length).toBe(0);
  });
  it('keeps losing pistol cases and counts the selected side once', () => {
    const rounds = visibleRounds(data, {side:'CT'}, true);
    expect(rounds.length).toBe(1);
    expect(pistolSummary(rounds, 'CT')).toMatchObject({samples:1, wins:0, losses:1});
  });
  it('does not count unverified matches in professional summaries', () => {
    const unverified = structuredClone(data);
    unverified.matches[0].source.verified=false;
    expect(visibleRounds(unverified, {}, true)).toHaveLength(0);
  });
  it('blocks unsafe media URLs and supports relative subpath deployments', () => {
    expect(mediaUrl('javascript:alert(1)', 'web')).toBe('');
    expect(mediaUrl('media/abc.png', 'web')).toBe('./content/media/abc.png');
  });
});
