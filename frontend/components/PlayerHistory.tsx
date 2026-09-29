'use client';
import {useEffect,useState} from 'react';
import type {EVSignal} from '@/lib/types';
import {forecastHistory,historyCutoff,recentForm} from '@/lib/forecastHistory';
import styles from './ResearchViews.module.css';

export default function PlayerHistory({signal}:{signal:EVSignal}) {
  const [logs,setLogs]=useState<unknown>([]);
  const [loading,setLoading]=useState(true);
  const [error,setError]=useState('');
  const [count,setCount]=useState(20);
  const [refresh,setRefresh]=useState(0);
  const {sport,player,player_id}=signal;
  let cutoff:string|undefined;
  try {cutoff=historyCutoff(signal);} catch { /* Older forecasts may lack timing evidence. */ }
  useEffect(()=>{
    const controller=new AbortController();
    const timer=window.setTimeout(()=>{
      if(!cutoff) {setError('This forecast has no valid historical cutoff and price-capture time.');setLoading(false);return;}
      const params=new URLSearchParams({sport,player,before:cutoff,exact:'1',limit:'20'});
      if(player_id) params.set('player_id',player_id);
      fetch(`/api/gamelogs?${params}`,{cache:'no-store',signal:AbortSignal.any([controller.signal,AbortSignal.timeout(15_000)])})
        .then(async response=>{
          if(!response.ok) throw new Error('Recorded player history is temporarily unavailable.');
          return response.json();
        }).then(data=>{if(!controller.signal.aborted) setLogs(data.logs);})
        .catch(()=>{if(!controller.signal.aborted) setError('Recorded player history is temporarily unavailable.');})
        .finally(()=>{if(!controller.signal.aborted) setLoading(false);});
    },0);
    return ()=>{window.clearTimeout(timer);controller.abort();};
  },[sport,player,player_id,cutoff,refresh]);
  const refreshHistory=()=>{setError('');setLoading(true);setRefresh(value=>value+1);};
  let history:ReturnType<typeof forecastHistory>|undefined;
  let form:ReturnType<typeof recentForm>|undefined;
  let invalid='';
  if(!loading && !error) {
    try {history=forecastHistory(logs,signal,count);form=recentForm(logs,signal);} catch {invalid='Recorded history could not be validated for this forecast.';}
  }
  const formWindows=form ? [{label:'Latest 5 recorded games',sample:form.recent},{label:'Previous 5 recorded games',sample:form.previous}] : [];
  return <section className={styles.playerHistory} aria-label="Player history before forecast">
    <div className={styles.historyHeader}><div><h3>History behind the line</h3><p>Recorded games before {cutoff ?? 'an unavailable cutoff'}, compared with {signal.direction} {signal.line} {signal.prop_type.replaceAll('_',' ')}. A conservative one-day gap before price capture excludes overnight games.</p></div>
      <div className={styles.historyActions}><button className={styles.uxButton} type="button" disabled={loading || !cutoff} onClick={refreshHistory}>{loading ? 'Loading history...' : error ? 'Retry history' : 'Refresh history'}</button><div className={styles.viewSwitch} aria-label="History window">{[10,20].map(n=><button type="button" key={n} aria-pressed={count===n} onClick={()=>setCount(n)}>Last {n}</button>)}</div></div>
    </div>
    {loading ? <p role="status">Loading recorded history…</p> : error || invalid ? <p role="status">{error || invalid}</p>
      : !history?.rows.length ? <p>No exact-player games are available before this forecast cutoff.</p> : <>
        {form && <section className={styles.recentForm} aria-label="Recent form before forecast">
          <h4>Recent form before this forecast</h4>
          <p>Latest recorded game: <strong>{form.recent.newest}</strong> &middot; {form.daysBeforeForecast} days before the target game.
            {form.daysBeforeForecast!==null && form.daysBeforeForecast>30 ? ' This is an older sample, not evidence of current form.' : ''}</p>
          <div className={styles.evidenceMetrics}>{formWindows.map(({label,sample})=>{
            return <div key={label}><span>{label}</span><strong>{sample.mean?.toFixed(1) ?? 'Unavailable'}</strong>
              <small>{sample.observed} observed stats in {sample.games} recorded games &middot; {sample.missing} missing</small>
              <small>{sample.oldest && sample.newest ? `${sample.oldest} to ${sample.newest}` : 'No prior comparison window'}</small>
              <small>{sample.decided ? `${sample.wins}/${sample.decided} matched this direction, excluding ties` : 'Direction rate unavailable'}{sample.teams.length ? ` | ${sample.teams.join(', ')}` : ''}</small></div>;
          })}</div>
          <p className={styles.historyDisclaimer}>These are available pre-cutoff records, not a complete participation census. Windows may cross seasons or teams; dates and missing stats matter. Later source corrections may be reflected here. This comparison does not adjust the recorded forecast probability.</p>
        </section>}
        <div className={styles.evidenceMetrics}>
          <div><span>Shown-game direction rate</span><strong>{history.rate===null ? 'Unavailable' : `${(history.rate*100).toFixed(0)}%`}</strong><small>{history.wins} of {history.decided} decided games</small></div>
          <div><span>Shown-game average</span><strong>{history.mean?.toFixed(1) ?? 'Unavailable'}</strong><small>Compared with line {signal.line}</small></div>
          <div><span>Recorded games shown</span><strong>{history.rows.length}</strong><small>{history.ties} ties · {history.missing} missing stats</small></div>
        </div>
        <div className={styles.historyOutcomes} aria-hidden="true">{[...history.rows].reverse().map(row=><span key={`${row.date}:${row.team}:${row.opponent}`} data-outcome={row.outcome} title={`${row.date}: ${row.stat ?? 'missing'} · ${row.outcome}`} />)}</div>
        <p className={styles.historyDisclaimer}>Descriptive history, not betting returns or a new probability. Ties and missing stats are excluded from the direction rate. This limited recent-game window does not reproduce the model’s full historical sample; no historical bookmaker prices are assumed.</p>
        <div className={styles.historyTable} tabIndex={0} aria-label="Pre-forecast game results"><table className="data-table"><caption>Recorded results at this forecast’s line</caption><thead><tr><th>Date</th><th>Matchup</th><th>Stat</th><th>At this line</th></tr></thead><tbody>{history.rows.map(row=><tr key={`${row.date}:${row.team}:${row.opponent}`}><td>{row.date}</td><td>{row.team} vs {row.opponent}</td><td>{row.stat ?? 'Unavailable'}</td><td>{row.outcome}</td></tr>)}</tbody></table></div>
      </>}
  </section>;
}
