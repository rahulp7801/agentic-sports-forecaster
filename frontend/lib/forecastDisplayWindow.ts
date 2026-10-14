import type {EVSignal} from './types';

export function forecastWindow(signal:Pick<EVSignal,'game_start_time'>,now=Date.now()) {
  const start=Date.parse(signal.game_start_time ?? '');
  return Number.isFinite(start) && start>now ? 'upcoming' : 'archive';
}

export function latestForecastWindow(signals:EVSignal[],now=Date.now()) {
  return signals.some(signal=>forecastWindow(signal,now)==='upcoming') ? 'upcoming' : 'archive';
}
