import type {NextGenStatsEvidence} from './types';

/** Explain the retained weeks; source download time is not performance recency. */
export function trackingSampleSummary(evidence:NextGenStatsEvidence) {
  const periods=evidence.sample_periods;
  if(!periods?.length || !evidence.roster_team) return {
    range:'Exact sample weeks and teams were not retained in this forecast.',
    composition:'The source download time alone does not establish recent form.',
    teams:null,limitation:null,
  };
  const sorted=[...periods].sort((a,b)=>b.season-a.season || b.week-a.week);
  const latest=sorted[0],oldest=sorted[sorted.length-1];
  const current=periods.filter(p=>p.season===evidence.cutoff_season);
  const currentTeam=current.filter(p=>p.team===evidence.roster_team);
  const unknown=periods.filter(p=>p.team===null).length;
  const teams=[...new Set(periods.flatMap(p=>p.team ? [p.team] : []))].sort();
  const limitations=[];
  if(!current.length) limitations.push(`No ${evidence.cutoff_season} tracking weeks are included; this sample does not establish current-season form.`);
  else if(!currentTeam.length) limitations.push(`No included week is from ${evidence.roster_team} in the ${evidence.cutoff_season} season.`);
  if(latest.season===evidence.cutoff_season && evidence.cutoff_week-latest.week>1)
    limitations.push(`The latest record is ${evidence.cutoff_week-latest.week} NFL weeks before the target game. Gaps can include byes or missing records.`);
  return {
    range:`Recorded sample: ${oldest.season} Week ${oldest.week} to ${latest.season} Week ${latest.week}.`,
    composition:`${current.length} of ${periods.length} weeks are from the ${evidence.cutoff_season} season; ${currentTeam.length} with ${evidence.roster_team} that season.`,
    teams:`Teams represented: ${teams.join(', ') || 'unavailable'}${unknown ? `; ${unknown} week${unknown===1?'':'s'} with unknown team` : ''}.`,
    limitation:limitations.join(' ') || null,
  };
}
