import type {EVSignal} from './types';

/** An athlete receipt when present; names are only a fallback for older records. */
export function playerIdentity(signal:Pick<EVSignal,'sport'|'player'|'player_id'>):string {
  return `${signal.sport}:${signal.player_id ? `id:${signal.player_id}` : `name:${signal.player}`}`;
}
