/** Public display metadata. Qualification and deadline calculation belong to the producer. */
export const FORECAST_DISPLAY_PROTOCOL='linework-forecast-display-v1';
export type ForecastDisplayView='library'|'qualified'|'candidates';
export type ForecastDisplayRow={row_index:number;id:string;state:'live'|'watchlist'|'research';
  gated:boolean;gate_reason:string|null;role:'primary'|'alternative'|'library';
  primary_index:number|null;group_rank:number|null;actionable_until:string|null;
  visible_until:string|null;lock_at:string};
export type ForecastDisplayAuthority={protocol:typeof FORECAST_DISPLAY_PROTOCOL;evaluated_at:string;
  revision:string;view:ForecastDisplayView;complete:boolean;invalid_signals:number;rows:ForecastDisplayRow[]};
export type ForecastDisplayBinding=Pick<ForecastDisplayAuthority,'revision'|'view'|'complete'|'invalid_signals'>;

const object=(value:unknown):value is Record<string,unknown>=>Boolean(value)&&typeof value==='object'&&!Array.isArray(value);
const stamp=(value:unknown):value is string=>typeof value==='string'&&value.length<=64
  && /([zZ]|[+-]\d\d:\d\d)$/.test(value)&&Number.isFinite(Date.parse(value));
const count=(value:unknown,maximum=5000):value is number=>Number.isSafeInteger(value)&&Number(value)>=0&&Number(value)<=maximum;
const reason=(value:unknown):value is string=>typeof value==='string'&&value.length>0&&value.length<=300&&!/[\u0000-\u001f]/.test(value);

/** Validate authority metadata against its ordered rows; do not calculate or return signal metrics. */
export function readForecastDisplayAuthority(value:unknown,signals:unknown,binding:ForecastDisplayBinding):ForecastDisplayAuthority|null {
  if(!object(value)||value.protocol!==FORECAST_DISPLAY_PROTOCOL||!stamp(value.evaluated_at)
    ||typeof value.revision!=='string'||!/^[a-f0-9]{64}$/.test(value.revision)
    ||!['library','qualified','candidates'].includes(String(value.view))||typeof value.complete!=='boolean'
    ||!count(value.invalid_signals)||!Array.isArray(signals)||signals.length>5000
    ||!Array.isArray(value.rows)||value.rows.length!==signals.length||!object(binding)
    ||value.revision!==binding.revision||value.view!==binding.view||value.complete!==binding.complete
    ||value.invalid_signals!==binding.invalid_signals) return null;
  const view=value.view as ForecastDisplayView,rows:ForecastDisplayRow[]=[];
  for(let index=0;index<signals.length;index++) {
    const signal=signals[index],row=value.rows[index];
    if(!object(signal)||!object(row)||typeof signal.id!=='string'||signal.id.length<1||signal.id.length>128
      ||/[\u0000-\u001f]/.test(signal.id)||typeof signal.gated!=='boolean'||row.gated!==signal.gated
      ||row.id!==signal.id||row.row_index!==index||!stamp(row.lock_at)
      ||row.gate_reason!==(signal.gate_reason ?? null)
      ||(row.gated ? row.gate_reason!==null&&!reason(row.gate_reason) : row.gate_reason!==null)) return null;
    if(view==='library') {
      if(row.state!=='research'||row.role!=='library'||row.primary_index!==null||row.group_rank!==null
        ||row.actionable_until!==null||row.visible_until!==null) return null;
    } else {
      if(!count(row.primary_index,signals.length-1)||row.primary_index>index||!count(row.group_rank)
        ||(row.role!=='primary'&&row.role!=='alternative')||(row.role==='primary')!==(row.primary_index===index)) return null;
      if(view==='qualified') {
        if(row.state!=='live'||row.gated||!stamp(row.actionable_until)||row.visible_until!==row.actionable_until
          ||Date.parse(row.actionable_until)>Date.parse(row.lock_at)) return null;
      } else if(row.state!=='watchlist'||!row.gated||row.actionable_until!==null||row.visible_until!==row.lock_at) return null;
    }
    rows.push({row_index:index,id:row.id as string,state:row.state as ForecastDisplayRow['state'],
      gated:row.gated as boolean,gate_reason:row.gate_reason as string|null,role:row.role as ForecastDisplayRow['role'],
      primary_index:row.primary_index as number|null,group_rank:row.group_rank as number|null,
      actionable_until:row.actionable_until as string|null,visible_until:row.visible_until as string|null,lock_at:row.lock_at as string});
  }
  if(view!=='library') {
    let rank=-1,lastPrimary=-1;
    for(const row of rows) {
      if(row.role==='primary') {rank++;lastPrimary=row.row_index;}
      if(row.primary_index!==lastPrimary||row.group_rank!==rank) return null;
    }
  }
  return {protocol:FORECAST_DISPLAY_PROTOCOL,evaluated_at:value.evaluated_at,revision:value.revision,
    view,complete:value.complete,invalid_signals:value.invalid_signals as number,rows};
}

/** Only withhold elapsed approvals. Supplied primary/alternative order is never changed. */
export function currentLiveForecastRows(value:unknown,signals:unknown,binding:ForecastDisplayBinding,now=Date.now()):ForecastDisplayRow[] {
  const authority=readForecastDisplayAuthority(value,signals,binding);
  if(!authority||!Number.isSafeInteger(now)||now<Date.parse(authority.evaluated_at)||authority.view!=='qualified'
    ||!authority.complete||authority.invalid_signals!==0) return [];
  return authority.rows.filter(row=>{
    if(row.state!=='live'||row.gated||row.primary_index===null) return false;
    const primary=authority.rows[row.primary_index];
    return primary?.role==='primary'&&primary.state==='live'&&!primary.gated
      &&now<Date.parse(primary.actionable_until ?? '')&&now<Date.parse(primary.lock_at)
      &&now<Date.parse(row.actionable_until ?? '')&&now<Date.parse(row.lock_at);
  });
}
