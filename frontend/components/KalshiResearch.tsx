'use client';
import {useEffect,useState} from 'react';
import type {Sport} from '@/lib/types';
import {upcomingMarketEvents} from '@/lib/marketResearchWindow';
import styles from './ResearchViews.module.css';

type Contract={ticker:string;title:string;url:string;yes_bid:number|null;
  yes_ask:number|null;yes_ask_size:number|null};
type Event={ticker:string;title:string;starts_at:string;markets:Contract[]};
type Listing={observed_at:string;scope:string;events:Event[]};
const cents=(value:number|null)=>value===null ? '—' : (value*100).toFixed(1)+'¢';

export default function KalshiResearch({sport}:{sport:Sport}) {
  return <KalshiResearchForSport key={sport} sport={sport}/>;
}

function KalshiResearchForSport({sport}:{sport:Sport}) {
  const [listing,setListing]=useState<Listing|null>(null);
  const [selected,setSelected]=useState('');
  const [error,setError]=useState('');
  const [now,setNow]=useState(()=>Date.now());
  useEffect(()=>{
    const update=()=>setNow(Date.now());
    const timer=setInterval(update,5000);
    document.addEventListener('visibilitychange',update);window.addEventListener('focus',update);
    return ()=>{clearInterval(timer);document.removeEventListener('visibilitychange',update);window.removeEventListener('focus',update);};
  },[]);
  useEffect(()=>{
    const controller=new AbortController();
    async function load(){
      try {
        const response=await fetch('/api/kalshi-research?sport='+sport,
          {signal:controller.signal,cache:'no-store'});
        if(!response.ok) throw new Error('Unavailable');
        const body=await response.json() as Listing;
        if(!controller.signal.aborted){setListing(body);setSelected(body.events[0]?.ticker ?? '');}
      } catch {
        if(!controller.signal.aborted) setError('Kalshi game research is temporarily unavailable.');
      }
    }
    void load();
    return ()=>controller.abort();
  },[sport]);
  const events=listing && now ? upcomingMarketEvents(listing.events,now) : [];
  const event=events.find(item=>item.ticker===selected);
  return <section className={styles.predictionResearch} aria-labelledby="kalshi-research-title">
    <header className={styles.predictionHeader}>
      <div><small>Public prediction market research</small><h3 id="kalshi-research-title">Kalshi · {sport.toUpperCase()}</h3></div>
      <p>Browse open game winner contracts and their reported YES quotes. Quotes and displayed sizes are snapshots; check the venue for depth, fees, and settlement rules.</p>
    </header>
    {error && <div className={styles.notice} role="status">{error}</div>}
    {!listing && !error && <div className={styles.notice}>Loading Kalshi games…</div>}
    {listing && <>
      <p className={styles.predictionScope}>{listing.scope} Retrieved {new Date(listing.observed_at).toLocaleString()}.</p>
      {!events.length && <div className={styles.emptyInline}>No upcoming open games appeared in this series sample.</div>}
      {!!events.length && <div className={styles.predictionEvents} aria-label="Kalshi league events">
        {events.map(item=><button key={item.ticker} type="button" aria-pressed={selected===item.ticker}
          onClick={()=>setSelected(item.ticker)}>
          <strong>{item.title}</strong><span>{new Date(item.starts_at).toLocaleString(undefined,{weekday:'short',month:'short',day:'numeric',hour:'numeric',minute:'2-digit'})}</span>
        </button>)}
      </div>}
      {selected && !event && !!events.length && <div className={styles.notice}>Selected game has started. Choose another upcoming game.</div>}
    </>}
    {event && <div className={styles.predictionDetail}>
      <div className={styles.predictionDetailHead}>
        <div><strong>{event.title}</strong><span>Observed {new Date(listing!.observed_at).toLocaleString()}</span></div>
      </div>
      <div className={styles.predictionTerms}>Each YES contract has its own settlement rule. A listed ask and size do not establish a fill, profit, or model edge.</div>
      <div className={styles.predictionContracts}>
        {event.markets.map(market=><article key={market.ticker} className={styles.predictionContract}>
          <strong>{market.title}</strong>
          <div><span>YES bid <b>{cents(market.yes_bid)}</b></span>
            <span>YES ask <b>{cents(market.yes_ask)}</b></span>
            <span>Displayed ask size <b>{market.yes_ask_size===null ? '—' : market.yes_ask_size.toFixed(2)}</b></span></div>
          <a href={market.url} target="_blank" rel="noopener noreferrer">View contract and rules at Kalshi ↗</a>
        </article>)}
      </div>
    </div>}
  </section>;
}
