'use client';
import Link from 'next/link';
import {ChartNoAxesCombined,ChartSpline,ClipboardCheck,ClipboardList,FlaskConical,Gauge,LayoutDashboard,ReceiptText} from 'lucide-react';
import type {Sport} from '@/lib/types';
import styles from './TerminalChrome.module.css';
interface SidebarProps {activeView:string;onViewChange:(view:string)=>void;sport:Sport;onSportChange:(sport:Sport)=>void;}
const NAV=[{id:'dashboard',label:'Picks',icon:LayoutDashboard},{id:'parlay',label:'Slip builder',icon:ReceiptText},{id:'results',label:'Past results',icon:ClipboardCheck},{id:'props',label:'Players',icon:ChartSpline},{id:'arbitrage',label:'Markets',icon:ChartNoAxesCombined},{id:'backtest',label:'Backtesting',icon:FlaskConical}];
const TOOLS=[{id:'gamelogs',label:'Game logs',icon:ClipboardList},{id:'kelly',label:'Stake calculator',icon:Gauge}];
export default function Sidebar({activeView,onViewChange,sport}:SidebarProps) {
  const button=(item:typeof NAV[number],visibility?:string)=>{const Icon=item.icon;return <button key={item.id} type="button" className={[activeView===item.id ? styles.sideNavActive : '',visibility].filter(Boolean).join(' ')} aria-current={activeView===item.id ? 'page' : undefined} onClick={event=>{onViewChange(item.id);event.currentTarget.closest('details')?.removeAttribute('open');}}><Icon aria-hidden="true" /><span>{item.label}</span></button>;};
  return <aside className={styles.sidebar}><Link className={styles.terminalBrand} href="/" aria-label="Return to Linework home"><span>L</span><div><strong>Linework</strong><small>Player prop desk</small></div></Link>
    <nav className={styles.sideNav} aria-label="Research views">{(sport==='cfb' ? NAV.filter(item=>['dashboard','parlay','results','props','arbitrage'].includes(item.id)) : NAV).map(item=>button(item,['arbitrage','backtest'].includes(item.id) ? styles.desktopOnly : undefined))}<details className={styles.advancedNav}><summary>More tools</summary><div>{NAV.filter(item=>['arbitrage','backtest'].includes(item.id) && (sport!=='cfb' || item.id==='arbitrage')).map(item=>button(item,styles.mobileOnly))}{TOOLS.filter(item=>sport!=='cfb' || item.id==='gamelogs').map(item=>button(item))}</div></details></nav>
    <div className={styles.sidebarFoot}><span>Evidence before action</span><p>Recheck the exact line and price with the book. No orders are placed here.</p></div></aside>;
}
