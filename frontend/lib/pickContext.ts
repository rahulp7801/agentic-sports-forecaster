import type {AvailabilityEvidence,EVSignal,PlayerProfile} from './types';

type InjuryReport=AvailabilityEvidence['teammates'][number];

/** Surface the existing acute-teammate gate first without mutating source order. */
export function orderedInjuryReports(reports:readonly InjuryReport[]):InjuryReport[] {
  const priority=(row:InjuryReport)=>{
    const status=row.status.trim().toLowerCase();
    return ['out','inactive','doubtful'].includes(status)
      && (row.relationship===undefined || row.relationship==='teammate') ? 2
      : status==='active' ? 0 : 1;
  };
  return [...reports].sort((a,b)=>priority(b)-priority(a));
}

/** A later player profile cannot relabel the team captured with a forecast. */
export function capturedRosterTeam(signal:EVSignal):string|null {
  const availability=signal.availability;
  const forecast=Date.parse(signal.captured_at ?? '');
  const captured=Date.parse(availability?.captured_at ?? '');
  return availability?.status==='observed' && availability.roster_confirmed
    && typeof availability.team==='string' && availability.team.trim()
    && Number.isFinite(forecast) && Number.isFinite(captured) && captured<=forecast
    ? availability.team : null;
}

/** Refreshed profile details are presentation-only and need their own as-of proof. */
export function capturedPlayerProfile(signal:EVSignal):PlayerProfile|undefined {
  const team=capturedRosterTeam(signal),profile=signal.player_profile;
  const observed=Date.parse(profile?.captured_at ?? '');
  const forecast=Date.parse(signal.captured_at ?? '');
  return team && typeof signal.availability?.player_id==='string'
    && profile?.team===team && profile.player_id===signal.availability.player_id
    && Number.isFinite(observed) && observed<=forecast
    ? profile : undefined;
}

/** A compact summary of captured context; it never changes a probability. */
export function pickContext(signal:EVSignal) {
  const availability=signal.availability;
  if(!availability || !capturedRosterTeam(signal)) return {
    player:'Forecast-time roster and injury evidence unavailable',
    reports:'Relevant reports could not be placed before this forecast',
    detail:'Open the evidence panel for the recorded source status.',
  };
  const flagged=orderedInjuryReports(availability.teammates).filter(row=>row.status.trim().toLowerCase()!=='active');
  const shown=flagged.slice(0,2).map(row=>`${row.player} (${row.relationship ? `${row.relationship}, ` : ''}${row.status})`);
  const extra=flagged.length>shown.length ? ` and ${flagged.length-shown.length} more` : '';
  const opponentCoverage=availability.opponent_injury_coverage==='observed' ? ''
    : availability.opponent_injury_coverage==='unavailable'
      ? ' Opponent injury-report coverage was unavailable at this forecast.'
      : ' Opponent injury-report coverage was not retained for this forecast.';
  const reports=(flagged.length
    ? 'Reported context: '+shown.join(', ')+extra
    : availability.teammates.length
      ? availability.teammates.length+' relevant report'+(availability.teammates.length===1?'':'s')+' retained; none flagged inactive'
      : availability.opponent_injury_coverage==='observed'
        ? 'No relevant offensive teammate or opposing defender report in the capture'
        : 'No relevant offensive teammate report in the capture.')+opponentCoverage;
  const splits=availability.context_splits?.length ?? 0;
  const tracking=signal.next_gen_stats?.sample_weeks ?? 0;
  const parts=[`${splits} historical participation comparison${splits===1?'':'s'}`];
  if(tracking) parts.push(`${tracking} prior tracking week${tracking===1?'':'s'}`);
  return {
    player:`${availability.subject_status} · ${availability.team} roster confirmed`,
    reports,
    detail:`${parts.join(' · ')}. Injury and tracking context do not add a probability boost.`,
  };
}

/** A captured injury report cannot be presented as current after its one-hour window. */
export function pickContextCapture(signal:EVSignal,now:number) {
  const raw=signal.availability?.captured_at;
  const captured=Date.parse(raw ?? '');
  const forecast=Date.parse(signal.captured_at ?? '');
  if(signal.availability?.status!=='observed' || !signal.availability.roster_confirmed
    || !Number.isFinite(now) || !Number.isFinite(captured) || !Number.isFinite(forecast)
    || captured>forecast || captured>now+60000) {
    return {capturedAt:null,stale:true};
  }
  return {capturedAt:raw ?? null,stale:now-captured>3600000};
}
