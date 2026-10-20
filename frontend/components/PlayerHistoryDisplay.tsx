'use client';
import {useState} from 'react';
import {readForecastHistoryDisplay,type ForecastHistoryDisplay,type ForecastHistoryDisplayBinding} from '../lib/forecastHistoryDisplay';
import styles from './ResearchViews.module.css';

type Props={display:ForecastHistoryDisplay;expected:ForecastHistoryDisplayBinding;initialWindow?:10|20};
const rateText=(value:number|null)=>value===null ? 'Unavailable' : `${(value*100).toFixed(0)}%`;

/** Prepared display consumer; the caller supplies independently bound descriptive outputs. */
export default function PlayerHistoryDisplay({display,expected,initialWindow=20}:Props) {
  const [count,setCount]=useState<10|20>(initialWindow===10 ? 10 : 20);
  const value=readForecastHistoryDisplay(display,expected);
  if(!value || value.status!=='available') return <section className={styles.playerHistory} aria-label="Player history before forecast">
    <h3>History behind the line</h3>
    <p role="status">Recorded player history is unavailable for this forecast.</p>
    <p className={styles.historyDisclaimer}>Descriptive history does not change the recorded forecast probability.</p>
  </section>;
  const {subject,scope,recent,calendar}=value,history=value.windows[String(count) as '10'|'20'];
  const sourceWindow=scope.source_cutoff_kind==='model_selection' ? 'the recorded model-selection cutoff' : 'forecast capture';
  const formWindows=[{label:'Latest 5 recorded games',sample:recent.recent},{label:'Previous 5 recorded games',sample:recent.previous}];
  return <section className={styles.playerHistory} aria-label="Player history before forecast">
    <div className={styles.historyHeader}>
      <div><h3>History behind the line</h3><p>{subject.player}: recorded games before {scope.game_date_before}, compared with {subject.direction} {subject.line} {subject.prop_type.replaceAll('_',' ')}. Only source records available by {sourceWindow} ({scope.source_observed_before}) are shown.</p></div>
      <div className={styles.viewSwitch} aria-label="History window">{([10,20] as const).map(n=><button type="button" key={n} aria-pressed={count===n} onClick={()=>setCount(n)}>Last {n}</button>)}</div>
    </div>
    <section className={styles.recentForm} aria-label="Last 30 days before forecast">
      <h4>The 30 days before the target game</h4>
      <p>Available records from {calendar.from}, before {calendar.before}, with source receipt no later than {sourceWindow}.</p>
      <div className={styles.evidenceMetrics}>{[
        {label:'All recorded teams',sample:calendar.allTeams},
        {label:calendar.capturedTeam ? `${calendar.capturedTeam} | roster team at capture` : 'Roster team unavailable',sample:calendar.capturedTeamSample},
      ].map(({label,sample})=><div key={label}><span>{label}</span><small>Average recorded stat</small><strong>{sample?.mean?.toFixed(1) ?? 'Unavailable'}</strong>
        <small>{sample ? `${sample.observed} observed stats in ${sample.games} recorded games | ${sample.missing} missing` : 'The forecast did not retain a confirmed roster team.'}</small>
        {sample && <small>{rateText(sample.rate)} matched this direction; {sample.wins}/{sample.decided} decided games, excluding ties.</small>}
        {sample?.oldest && <small>{sample.oldest} to {sample.newest}</small>}
      </div>)}</div>
      {!calendar.allTeams.games && <p>No recorded games fall inside this window. Older games below do not establish current form.</p>}
      {calendar.capturedTeamSample && !calendar.capturedTeamSample.games && calendar.allTeams.games>0 && <p>No recorded games in this window match the roster team captured with this forecast.</p>}
      <p className={styles.historyDisclaimer}>{calendar.limitedToLatest20 ? 'This window reaches the 20-game display limit and may omit additional games. ' : ''}Available records only; missing games are unknown. The captured roster team can differ from the team today. Later source corrections are excluded; earlier versions of corrected rows may no longer be retained. These descriptive results do not change the recorded probability.</p>
    </section>
    <section className={styles.recentForm} aria-label="Recent form before forecast">
      <h4>Recent form before this forecast</h4>
      <p>Latest recorded game: <strong>{recent.recent.newest ?? 'Unavailable'}</strong>
        {recent.daysBeforeForecast!==null ? ` · ${recent.daysBeforeForecast} days before the target game.` : '.'}
        {' '}Latest observed stat in these five games: <strong>{recent.recent.newestObserved ?? 'Unavailable'}</strong>
        {recent.observedDaysBeforeForecast!==null ? ` · ${recent.observedDaysBeforeForecast} days before the target game.` : '.'}
        {recent.observedDaysBeforeForecast===null || recent.observedDaysBeforeForecast>30 ? ' This group does not establish current stat form.' : ''}</p>
      <div className={styles.evidenceMetrics}>{formWindows.map(({label,sample})=><div key={label}><span>{label}</span><strong>{sample.mean?.toFixed(1) ?? 'Unavailable'}</strong>
        <small>{sample.observed} observed stats in {sample.games} recorded games · {sample.missing} missing</small>
        <small>{sample.oldest && sample.newest ? `${sample.oldest} to ${sample.newest}` : 'No prior comparison window'}</small>
        <small>{rateText(sample.rate)} matched this direction; {sample.wins}/{sample.decided} decided games, excluding ties.{sample.teams.length ? ` | ${sample.teams.join(', ')}` : ''}</small>
      </div>)}</div>
      <p className={styles.historyDisclaimer}>These are available pre-cutoff records, not a complete participation census. Windows may cross seasons or teams; dates and missing stats matter. Later source corrections are excluded; earlier versions of corrected rows may no longer be retained. This comparison does not adjust the recorded forecast probability.</p>
    </section>
    <p>{value.card_summary}</p>
    {value.context_labels.length>0 && <section aria-label="Recorded participation context"><h4>Recorded participation</h4>{value.context_labels.map((label,index)=><div key={index}>
      <p>{label.player} · {label.team} · {label.relationship} · {label.unit}</p>
      {label.window.map((text,position)=><p key={position}>{text}</p>)}<p>{label.recent}</p>
    </div>)}</section>}
    {!history.rows.length ? <p>No exact-player game records were available by this forecast capture time.</p> : <>
      <div className={styles.evidenceMetrics}>
        <div><span>Shown-game direction rate</span><strong>{rateText(history.rate)}</strong><small>{history.wins} of {history.decided} decided games</small></div>
        <div><span>Shown-game average</span><strong>{history.mean?.toFixed(1) ?? 'Unavailable'}</strong><small>Compared with line {subject.line}</small></div>
        <div><span>Recorded games shown</span><strong>{history.rows.length}</strong><small>{history.ties} ties · {history.missing} missing stats</small></div>
      </div>
      <div className={styles.historyOutcomes} aria-hidden="true">{[...history.rows].reverse().map(row=><span key={`${row.date}:${row.team}:${row.opponent}`} data-outcome={row.outcome} title={`${row.date}: ${row.stat ?? 'missing'} · ${row.outcome}`} />)}</div>
      <div className={styles.historyTable} tabIndex={0} aria-label="Pre-forecast game results"><table className="data-table"><caption>Recorded results at this forecast&apos;s line</caption><thead><tr><th>Date</th><th>Matchup</th><th>Stat</th><th>At this line</th></tr></thead><tbody>{history.rows.map(row=><tr key={`${row.date}:${row.team}:${row.opponent}`}><td>{row.date}</td><td>{row.team} vs {row.opponent}</td><td>{row.stat ?? 'Unavailable'}</td><td>{row.outcome}</td></tr>)}</tbody></table></div>
    </>}
    <p className={styles.historyDisclaimer}>Descriptive history, not betting returns or a new probability. Ties and missing stats are excluded from the direction rate. This limited recent-game window does not reproduce the model&apos;s full historical sample; no historical bookmaker prices are assumed.</p>
  </section>;
}
