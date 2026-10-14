'use client';
import {useState} from 'react';
import Image from 'next/image';
import {motion,useReducedMotion} from 'motion/react';
import {WEEK_ONE_DEMO,demoResult,demoHistory,DEFAULT_DEMO_INDEX,DEMO_HISTORY_CAPTURED_AT} from '@/lib/weekOneDemo';
import styles from './HistoricalFlowDemo.module.css';

export default function HistoricalFlowDemo() {
  const [player,setPlayer]=useState(DEFAULT_DEMO_INDEX);
  const reduce=useReducedMotion(),record=WEEK_ONE_DEMO[player],result=demoResult(record),history=demoHistory(record);
  return <section id="demo" className={styles.demo} aria-label="Week 1 historical walkthrough">
    <header><div><span className={styles.badge}>PAST-GAME DEMO · NFL WEEK 1</span><h3>The forecast. The final result.</h3></div>
      <label>Compare a replay<select aria-label="Demo player" value={player} onChange={event=>setPlayer(Number(event.target.value))}>
        {WEEK_ONE_DEMO.map((item,index)=><option key={item.player} value={index}>{item.player} · {demoResult(item).correct ? 'Correct' : 'Missed'}</option>)}
      </select></label></header>
    <motion.div key={record.player} initial={reduce ? false : {opacity:0,y:8}} animate={{opacity:1,y:0}} transition={{duration:.2}} aria-live="polite">
      <div className={styles.pickGrid}>
        <div className={styles.pick}><div className={styles.player}>
          <Image src={`https://a.espncdn.com/i/headshots/nfl/players/full/${record.athlete}.png`} alt="" width={80} height={80} unoptimized referrerPolicy="no-referrer" />
          <div><small>{record.team} vs {record.opponent} · {record.date}</small><h4>{record.player}</h4></div>
        </div><span className={styles.eyebrow}>RETROSPECTIVE MODEL FORECAST</span><h4 className={styles.pickTitle}>Over {record.threshold}<span>passing yards</span></h4>
          <p>A fixed research threshold, evaluated against the final game stat.</p></div>
        <div className={`${styles.result} ${result.correct ? '' : styles.resultMissed}`}><span>Verified final passing yards</span><strong>{record.actual}<small> yd</small></strong>
          <b className={result.correct ? styles.correct : styles.missed}>{result.correct ? '✓ Correct forecast' : 'Missed forecast'}</b>
          <p>{result.outcome}</p>
          <a href={`https://site.api.espn.com/apis/site/v2/sports/football/nfl/summary?event=${record.event}`} target="_blank" rel="noreferrer">View final-stat source ↗</a>
        </div>
      </div>
      <div className={styles.metrics}><div><span>Recorded model baseline</span><strong>{(record.probability*100).toFixed(1)}%</strong><small>Above the research threshold</small></div>
        <div><span>History behind it</span><strong>{record.sample} games</strong><small>Before the target game date</small></div>
        <div><span>Evidence</span><strong>Final stat verified</strong><small>Exact player and game match</small></div></div>
      <div className={styles.reason}><span className={styles.eyebrow}>HISTORY IN THIS REPLAY</span>
        <p><strong>{record.player} exceeded {record.threshold} yards in {history.above} of {record.sample} prior games.</strong> The median was {history.median} yards, {(history.median-record.threshold).toFixed(1)} above the threshold.</p>
      </div>
      <details className={styles.explanation}><summary>See the history behind the forecast</summary>
        <div className={styles.historyStats}><p><strong>{history.above} above / {history.below} below</strong><br />{(history.above/record.sample*100).toFixed(1)}% observed rate across the full sample.</p>
          <p><strong>{history.recentAbove} of {history.recent.length} latest prior games above</strong><br />{history.recentAbove/history.recent.length<history.above/record.sample ? 'These games had a lower observed rate than the full sample.' : 'These games had a higher observed rate than the full sample.'}</p></div>
        <table className={styles.historyTable}><caption>Latest five games before {record.date} / newest first</caption><thead><tr><th scope="col">Date</th><th scope="col">Opponent</th><th scope="col">Passing yards</th><th scope="col">vs {record.threshold}</th></tr></thead>
          <tbody>{history.recent.map(game=><tr key={game.date}><td>{game.date}</td><td>{game.opponent}</td><td>{game.yards}</td><td className={game.yards>record.threshold ? styles.correct : styles.missed}>{game.yards>record.threshold ? 'Above' : 'Below'}</td></tr>)}</tbody></table>
        <p>This replay retains a model baseline of {(record.probability*100).toFixed(1)}%. Observed history and model probability are separate measurements. No opponent, injury or teammate adjustment was retained for this example.</p>
        <p>History covered {history.first_date} through {history.last_date}, and was retrieved on {DEMO_HISTORY_CAPTURED_AT}, after the target game. These older games do not describe current form.</p>
        <details className={styles.methodology}><summary>Replay method and limitations</summary>
          <p>This walkthrough displays a fixed forecast from a replay assembled after the game. Its descriptive history contains only games dated before the target; the target game&apos;s final stat grades the forecast. No timestamped pregame sportsbook recommendation was retained.</p>
          <p>Historical sportsbook prices, a retained uncertainty interval and timestamped injury evidence are absent, so this replay cannot establish betting value, stake, ROI or CLV. Demo records remain separate from live picks and performance totals.</p>
          <small>Retained final-stat source commitment</small><code>{record.source_sha256}</code>
        </details>
      </details>
    </motion.div>
    <footer><span>Retrospective research replay · September 10–13, 2026</span><a href="#waitlist">Join the waitlist →</a></footer>
  </section>;
}
