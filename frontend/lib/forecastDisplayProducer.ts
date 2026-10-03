import {groupAlternateLines} from './bestPicks.ts';
import {FORECAST_DISPLAY_PROTOCOL,readForecastDisplayAuthority,
  type ForecastDisplayAuthority,type ForecastDisplayRow,type ForecastDisplayView} from './forecastDisplayAuthority.ts';
import type {EVSignal} from './types';

/** Private producer: bind unchanged server selections to explicit display lifetimes and order. */
export function forecastDisplayAuthority(signals:EVSignal[],view:ForecastDisplayView,revision:string,
  complete:boolean,invalidSignals:number,now:number):ForecastDisplayAuthority {
  const positions=new Map<number,{primary:number;rank:number}>();
  if(view!=='library') {
    let index=0;
    for(const [rank,group] of groupAlternateLines(signals).entries()) {
      const primary=index;
      for(const signal of [group.pick,...group.alternatives]) {
        if(signal!==signals[index]) throw Error('Display selection order changed');
        positions.set(index++,{primary,rank});
      }
    }
    if(index!==signals.length) throw Error('Display selection coverage changed');
  }
  const rows:ForecastDisplayRow[]=signals.map((signal,index)=>{
    const lock=Date.parse(signal.game_start_time ?? '')-3_600_000;
    const position=positions.get(index);
    // Original source-age gates are inclusive at equality; Date.now uses integer
    // milliseconds. The first excluded millisecond is the display deadline.
    const live=view==='qualified' ? Math.min(lock,Date.parse(signal.snapped_at)+300_001,
      Date.parse(signal.availability?.captured_at ?? '')+3_600_001) : null;
    return {row_index:index,id:signal.id,state:view==='qualified' ? 'live' : view==='candidates' ? 'watchlist' : 'research',
      gated:signal.gated as boolean,gate_reason:signal.gate_reason ?? null,
      role:position ? position.primary===index ? 'primary' : 'alternative' : 'library',
      primary_index:position?.primary ?? null,group_rank:position?.rank ?? null,
      actionable_until:live===null ? null : new Date(live).toISOString(),
      visible_until:view==='candidates' ? new Date(lock).toISOString() : live===null ? null : new Date(live).toISOString(),
      lock_at:new Date(lock).toISOString()};
  });
  const value={protocol:FORECAST_DISPLAY_PROTOCOL,evaluated_at:new Date(now).toISOString(),revision,
    view,complete,invalid_signals:invalidSignals,rows};
  const projected=readForecastDisplayAuthority(value,signals,{revision,view,complete,invalid_signals:invalidSignals});
  if(!projected) throw Error('Invalid forecast display authority');
  return projected;
}
