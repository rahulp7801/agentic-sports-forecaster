'use client';

import { useCallback, useEffect, useState } from 'react';
import type { GameLog, Sport } from '@/lib/types';
import { gameLog, gameLogSelection, overFrequency } from '@/lib/gameLogMetrics';
import {gameLogRequest,publicGameLogs} from '@/lib/publicGameLogs';
import styles from './ResearchViews.module.css';

interface GameLogsProps { sport: Sport }

const NBA_COLS = ['points', 'rebounds', 'assists', 'threes', 'steals', 'blocks', 'minutes'] as const;
const CFB_COLS = ['pass_yds', 'rush_yds', 'rec_yds', 'receptions'] as const;
const NFL_COLS = ['pass_yds', 'pass_tds', 'rush_yds', 'rec_yds', 'receptions'] as const;

function StatCell({ value, line }: { value?: number; line?: number }) {
  if (value === undefined) return <td style={{ color: 'var(--text-dim)' }}>—</td>;
  const beat = line !== undefined && value !== line ? value > line : undefined;
  return (
    <td style={{
      color: beat === true ? 'var(--accent-mint)' : beat === false ? 'var(--accent-red)' : 'var(--text-primary)',
      fontWeight: beat !== undefined ? 600 : 400,
      fontVariantNumeric: 'tabular-nums',
    }}>
      {value}
    </td>
  );
}

export default function GameLogs({ sport }: GameLogsProps) {
  const [playerFilter, setPlayerFilter] = useState('');
  const [activeProp, setActiveProp] = useState<string>(sport === 'nba' ? 'points' : 'pass_yds');
  const [activeLine, setActiveLine] = useState('');
  const [selectedPlayerId, setSelectedPlayerId] = useState('');
  const [allLogs, setAllLogs] = useState<GameLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [refresh,setRefresh]=useState(0);
  const [error, setError] = useState('');
  const [checkedAt,setCheckedAt]=useState<string|null>(null);

  const fetchLogs = useCallback(async (signal: AbortSignal) => {
    setLoading(true);
    setAllLogs([]);
    setSelectedPlayerId('');
    setError('');
    setCheckedAt(null);
    try {
      const params = new URLSearchParams({ sport, limit: '40' });
      if (playerFilter.trim()) params.set('player', playerFilter.trim().normalize('NFC'));
      try {gameLogRequest(params);} catch {
        if(!signal.aborted) setError('Use a player name with letters, spaces, apostrophes, periods or hyphens (up to 80 characters).');
        return;
      }
      const response = await fetch(`/api/gamelogs?${params}`, { cache: 'no-store', signal:AbortSignal.any([signal,AbortSignal.timeout(15_000)]) });
      if (!response.ok) throw new Error('Game logs unavailable');
      const data = await response.json();
      const logs: GameLog[] = publicGameLogs(data.logs,sport).map((row,index)=>gameLog(row,sport,String(index)));
      if (!signal.aborted) {setAllLogs(logs);setCheckedAt(new Date().toISOString());}
    } catch {
      if (!signal.aborted) {
        setAllLogs([]);
        setError('Recorded game logs are temporarily unavailable. Try again.');
      }
    } finally {
      if (!signal.aborted) setLoading(false);
    }
  }, [sport, playerFilter]);

  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(() => void fetchLogs(controller.signal), 250);
    return () => { controller.abort(); clearTimeout(timer); };
  }, [fetchLogs,refresh]);

  const refreshLogs=()=>{setError('');setAllLogs([]);setCheckedAt(null);setLoading(true);setRefresh(value=>value+1);};

  const cols = sport === 'nba' ? NBA_COLS : sport==='cfb' ? CFB_COLS : NFL_COLS;
  const numericLine = activeLine.trim() === '' ? NaN : Number(activeLine);
  const lineValue = Number.isFinite(numericLine) && numericLine >= 0 ? numericLine : undefined;
  const {athletes, selectedAthlete, unidentifiedRows, displayLogs} = gameLogSelection(allLogs, selectedPlayerId);
  const frequency = selectedAthlete ? overFrequency(displayLogs, activeProp, lineValue) : null;

  return (
    <section className={styles.toolView} aria-labelledby="logs-title">
      <header className={styles.toolHeader}>
        <div>
          <small>Recorded outcomes</small>
          <h2 id="logs-title">Game logs</h2>
        </div>
        <p>Inspect stored player outcomes and calculate a descriptive over frequency for the rows shown. Ties and missing values are excluded; this view does not produce a forecast.</p>
      </header>

      <div className={styles.controlBar}>
        <div className={styles.controlGroup} style={{ minWidth: 190 }}>
          <label htmlFor="log-player">Player filter</label>
          <input id="log-player" className="term-input" placeholder="Search recorded players" value={playerFilter} maxLength={80} onChange={event => {setAllLogs([]);setSelectedPlayerId('');setCheckedAt(null);setError('');setLoading(true);setPlayerFilter(event.target.value);}} />
        </div>
        <button type="button" className={styles.uxButton} onClick={refreshLogs} disabled={loading}>{loading ? 'Loading logs...' : error ? 'Retry logs' : 'Refresh logs'}</button>
        {athletes.length > 0 && (athletes.length > 1 || unidentifiedRows > 0) && (
          <div className={styles.controlGroup} style={{ minWidth: 190 }}>
            <label htmlFor="log-athlete">Athlete to inspect</label>
            <select id="log-athlete" className="term-select" value={selectedAthlete?.playerId ?? ''}
              onChange={event => setSelectedPlayerId(event.target.value)}>
              <option value="">Select an athlete</option>
              {athletes.map(athlete => <option key={athlete.playerId} value={athlete.playerId}>
                {athlete.player} | {[...athlete.teams].join('/')} | {athlete.playerId}
              </option>)}
            </select>
          </div>
        )}
        <div className={styles.controlSpacer} />
        <div className={styles.controlGroup}>
          <label htmlFor="log-prop">Stat</label>
          <select id="log-prop" className="term-select" value={activeProp} onChange={event => setActiveProp(event.target.value)}>
            {cols.map(column => <option key={column} value={column}>{column.replace('_', ' ').toUpperCase()}</option>)}
          </select>
        </div>
        <div className={styles.controlGroup} style={{ minWidth: 90 }}>
          <label htmlFor="log-line">Over line</label>
          <input id="log-line" className="term-input" value={activeLine} onChange={event => setActiveLine(event.target.value)} placeholder="Enter line" type="number" min="0" step="0.5" />
        </div>
        {frequency && frequency.rate !== null && (
          <div className={styles.analysisReadout}>
            <span>{selectedAthlete?.player} | shown-row over rate</span>
            <strong>{(frequency.rate * 100).toFixed(0)}%</strong>
            <span>{frequency.wins}/{frequency.decided}</span>
          </div>
        )}
      </div>

      {error && <div className={styles.notice} role="alert">{error}</div>}
      {checkedAt && !loading && !error && <p className={styles.contextNote}>History loaded <time dateTime={checkedAt}>{new Date(checkedAt).toLocaleString()}</time>. This response may include a recent cache; source updates can arrive later.</p>}
      {lineValue !== undefined && !loading && !error && allLogs.length > 0 && !selectedAthlete && (
        <p className={styles.contextNote}>Select one identified athlete to calculate an individual over rate. Unidentified rows cannot be assigned safely.</p>
      )}
      {frequency && <p className={styles.contextNote}><b>Descriptive only</b> · {frequency.pushes} ties and {frequency.missing} missing stats excluded from this athlete&apos;s shown-row rate.{unidentifiedRows > 0 ? ` ${unidentifiedRows} rows without a player ID excluded.` : ''}</p>}

      <div className={styles.tableViewport} tabIndex={0} aria-label="Recorded player game logs">
        <table className={`data-table ${styles.toolTable}`}>
          <thead>
            <tr>
              <th>Player</th><th>Date</th><th>Matchup</th><th>H/A</th><th>Result</th>
              {cols.map(column => <th key={column} style={{ color: column === activeProp ? 'var(--accent-cyan)' : undefined }}>{column.replace('_', ' ').toUpperCase()}</th>)}
            </tr>
          </thead>
          <tbody>
            {displayLogs.map(log => (
              <tr key={log.id}>
                <td><strong style={{ color: 'var(--text-primary)', fontSize: 11 }}>{log.player}</strong><br /><small style={{ color: 'var(--text-muted)' }}>{log.team}</small></td>
                <td style={{ color: 'var(--text-secondary)' }}>{log.date}</td>
                <td style={{ color: 'var(--text-secondary)' }}>{log.team} vs {log.opponent}</td>
                <td><span className={`badge ${log.home_away === 'home' ? 'badge-blue' : 'badge-dim'}`}>{log.home_away === 'home' ? 'HOME' : log.home_away === 'away' ? 'AWAY' : '—'}</span></td>
                <td><span className={`badge ${log.result === 'W' ? 'badge-mint' : 'badge-red'}`}>{log.result ?? '—'}</span></td>
                {cols.map(column => <StatCell key={column} value={log[column as keyof GameLog] as number | undefined} line={column === activeProp ? lineValue : undefined} />)}
              </tr>
            ))}
            {allLogs.length === 0 && (
              <tr><td colSpan={5+cols.length} style={{ textAlign: 'center', color: 'var(--text-muted)', padding: 48 }}>{loading ? 'Loading recorded game logs…' : error ? 'Game logs unavailable' : 'No recorded game logs found.'}</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
