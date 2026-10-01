'use client';
import {useEffect,useState} from 'react';
import type {Sport} from '@/lib/types';
import styles from './ResearchViews.module.css';

type Event={slug:string;title:string;starts_at:string};
type Market={question:string;outcome:string;best_bid:number|null;best_ask:number|null;
  liquidity_usd:number|null;accepting_orders:boolean};
type Listing={observed_at:string;scope:string;events:Event[]};
type Detail={observed_at:string;event:{slug:string;title:string;starts_at:string;url:string};markets:Market[]};
const cents=(value:number|null)=>value===null ? '—' : (value*100).toFixed(1)+'¢';

export default function PolymarketResearch({sport}:{sport:Sport}) {
  const [listing,setListing]=useState<Listing|null>(null);
  const [selected,setSelected]=useState('');
  const [detail,setDetail]=useState<Detail|null>(null);
  const [error,setError]=useState('');
  const [detailError,setDetailError]=useState('');
  useEffect(()=>{
    const controller=new AbortController();
    setListing(null);setSelected('');setDetail(null);setError('');
    async function load() {
      try {
        const response=await fetch('/api/polymarket?sport='+sport,
          {signal:controller.signal,cache:'no-store'});
        if(!response.ok) throw new Error('Polymarket events are temporarily unavailable.');
        const body=await response.json() as Listing;
        if(!controller.signal.aborted) {setListing(body);setSelected(body.events[0]?.slug ?? '');}
      } catch {
        if(!controller.signal.aborted) setError('Polymarket events are temporarily unavailable.');
      }
    }
    void load();
    return ()=>controller.abort();
  },[sport]);
  useEffect(()=>{
    if(!selected)return;
    const controller=new AbortController();
    setDetail(null);setDetailError('');
    async function load() {
      try {
        const response=await fetch('/api/polymarket?sport='+sport+'&event='+encodeURIComponent(selected),
          {signal:controller.signal,cache:'no-store'});
        if(!response.ok) throw new Error('Contract details unavailable.');
        const body=await response.json() as Detail;
        if(!controller.signal.aborted) setDetail(body);
      } catch {
        if(!controller.signal.aborted) setDetailError('Contract details are temporarily unavailable.');
      }
    }
    void load();
    return ()=>controller.abort();
  },[sport,selected]);
  return <section className={styles.predictionResearch} aria-labelledby="polymarket-title">
    <header className={styles.predictionHeader}>
      <div><small>Public prediction market research</small><h3 id="polymarket-title">Polymarket · {sport.toUpperCase()}</h3></div>
      <p>Browse league events and open outcome contracts. Prices and liquidity are source snapshots. Check the venue for depth, fees, and settlement terms before drawing a conclusion.</p>
    </header>
    {error && <div className={styles.notice} role="status">{error}</div>}
    {!listing && !error && <div className={styles.notice}>Loading Polymarket events…</div>}
    {listing && <>
      <p className={styles.predictionScope}>{listing.scope} Retrieved {new Date(listing.observed_at).toLocaleString()}.</p>
      {!listing.events.length && <div className={styles.emptyInline}>No upcoming events appeared in this league-series sample.</div>}
      {!!listing.events.length && <div className={styles.predictionEvents} aria-label="Polymarket league events">
        {listing.events.map(event=><button key={event.slug} type="button" aria-pressed={selected===event.slug}
          onClick={()=>setSelected(event.slug)}>
          <strong>{event.title}</strong><span>{new Date(event.starts_at).toLocaleString(undefined,{weekday:'short',month:'short',day:'numeric',hour:'numeric',minute:'2-digit'})}</span>
        </button>)}
      </div>}
    </>}
    {detailError && <div className={styles.notice} role="status">{detailError}</div>}
    {selected && !detail && !detailError && <div className={styles.notice}>Loading contract quotes…</div>}
    {detail && <div className={styles.predictionDetail}>
      <div className={styles.predictionDetailHead}>
        <div><strong>{detail.event.title}</strong><span>Observed {new Date(detail.observed_at).toLocaleString()}</span></div>
        <a href={detail.event.url} target="_blank" rel="noopener noreferrer">View event and rules at Polymarket ↗</a>
      </div>
      <div className={styles.predictionTerms}>Bid and ask refer to the labeled first outcome of each contract and are Gamma-reported snapshots. The indicative outcome price is excluded because it may differ sharply from the ask. No fill, profit, or model edge is implied.</div>
      {!detail.markets.length && <div className={styles.emptyInline}>No open contracts with valid terms were returned for this event.</div>}
      {!!detail.markets.length && <div className={styles.predictionContracts}>
        {detail.markets.map((market,index)=><article key={index} className={styles.predictionContract}>
          <strong>{market.question}</strong>
          <div><span>{market.outcome} bid <b>{cents(market.best_bid)}</b></span><span>{market.outcome} ask <b>{cents(market.best_ask)}</b></span>
            <span>Liquidity <b>{market.liquidity_usd===null ? '—' : '$'+market.liquidity_usd.toFixed(0)}</b></span>
            <span>{market.accepting_orders ? 'Accepting orders at capture' : 'Orders unavailable at capture'}</span></div>
        </article>)}
      </div>}
    </div>}
  </section>;
}