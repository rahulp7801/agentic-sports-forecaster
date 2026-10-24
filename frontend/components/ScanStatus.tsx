'use client';

import { useEffect, useState } from 'react';
import type {Sport} from '@/lib/types';
import {scanRailRows,type PublicScanStatus} from '@/lib/scanRail';
import styles from './TerminalChrome.module.css';

type Status = PublicScanStatus;

function tone(state: string) {
  if (state === 'healthy' || state === 'complete') return styles.scanGood;
  if (['degraded','stale','overdue','interrupted','failed','blocked','unknown'].includes(state)) return styles.scanWarning;
  return styles.scanQuiet;
}

export default function ScanStatus({sport}:{sport?:Sport}) {
  return <SportScanStatus key={sport ?? 'all'} sport={sport} />;
}

function SportScanStatus({sport}:{sport?:Sport}) {
  const [data, setData] = useState<[Sport, Status][] | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      try {
        const response = await fetch('/api/scans', { cache: 'no-store', signal: AbortSignal.any([controller.signal,AbortSignal.timeout(15_000)]) });
        if (!response.ok) throw new Error('Daily scan status unavailable');
        const rows=scanRailRows(await response.json(),sport);
        if(!rows) throw new Error('Invalid daily scan status');
        if(!controller.signal.aborted) setData(rows);
        if(!controller.signal.aborted) setError('');
      } catch {
        if (!controller.signal.aborted) {
          setData(null);
          setError('Daily scan status unavailable');
        }
      }
    }
    void load();
    const timer = setInterval(() => void load(), 60_000);
    return () => {
      controller.abort();
      clearInterval(timer);
    };
  }, [sport]);

  return (
    <div className={styles.scanRail} data-single-league={sport ? true : undefined} aria-live="polite" aria-label="Daily model pipeline status" tabIndex={0}>
      <span className={styles.scanRailLabel}>Pipeline</span>
      {error ? (
        <div className={`${styles.scanCard} ${styles.scanWarning}`}><strong>{error}</strong></div>
      ) : !data ? (
        <div className={`${styles.scanCard} ${styles.scanQuiet}`}><strong>Checking daily scans…</strong></div>
      ) : data.map(([key, status]) => (
        <article className={`${styles.scanCard} ${tone(status.state)}`} key={key}>
          <div className={styles.scanIdentity}>
            <span>{key.toUpperCase()}</span>
            <strong>{status.label}</strong>
          </div>
          <div className={styles.scanMetrics}>
            {status.eligible !== null && status.completed !== null && (
              <span title="Game evaluations, not betting recommendations"><b>{status.completed}/{status.eligible}</b> games evaluated</span>
            )}
            {status.selections !== null && status.selections > 0 && (
              <span><b>{status.model_estimates ?? '?'}/{status.selections}</b> modeled</span>
            )}
            {status.unresolved_selections !== null && status.unresolved_selections > 0 && (
              <span><b>{status.unresolved_selections}</b> unmatched</span>
            )}
            {status.missing_estimates !== null && status.missing_estimates > 0 && (
              <span><b>{status.missing_estimates}</b> unavailable</span>
            )}
          </div>
          {status.overdue_at ? <time dateTime={status.overdue_at} title="This quote check was due, but a newer completed scan has not been recorded">Quote check overdue since {new Date(status.overdue_at).toLocaleString([], { month:"short", day:"numeric", hour:"2-digit", minute:"2-digit" })}</time> : status.next_refresh_at ? <time dateTime={status.next_refresh_at} title="Earliest quote check; actual collection depends on the scheduled worker and remaining credits">Next quote check: {new Date(status.next_refresh_at).toLocaleString([], { month:'short', day:'numeric', hour:'2-digit', minute:'2-digit' })}</time> : status.updated_at && <time dateTime={status.updated_at} title="Last scan check">{new Date(status.updated_at).toLocaleString([], { month:'short', day:'numeric', hour:'2-digit', minute:'2-digit' })}</time>}
          {status.recorded_budget_label && <div className={styles.scanPlan}>
            <span>Last recorded plan: {status.recorded_budget_label.toLowerCase()}.</span>
            {status.reserve_release_at && <span>{status.reserve_release_passed ? 'Recorded reserve release passed' : 'Earliest recorded reserve release'}: <time dateTime={status.reserve_release_at}>{new Date(status.reserve_release_at).toLocaleString([], {month:'short',day:'numeric',hour:'2-digit',minute:'2-digit',timeZoneName:'short'})}</time>. {status.reserve_release_passed ? 'Awaiting a new scan.' : 'Collection still depends on the next worker run and available allowance.'}</span>}
            {status.rolling_release_at && <span>{status.rolling_release_passed ? 'Recorded rolling allowance estimate passed' : 'Earliest recorded rolling allowance estimate'}: <time dateTime={status.rolling_release_at}>{new Date(status.rolling_release_at).toLocaleString([], {month:'short',day:'numeric',hour:'2-digit',minute:'2-digit',timeZoneName:'short'})}</time>. New usage or daily limits can delay it; game and quote availability still require a new scan.</span>}
          </div>}
        </article>
      ))}
    </div>
  );
}
