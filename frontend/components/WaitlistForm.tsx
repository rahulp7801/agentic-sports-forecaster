'use client';
import {useState,type FormEvent} from 'react';
import styles from './WaitlistForm.module.css';
export default function WaitlistForm() {
  const [state,setState]=useState<'idle'|'busy'|'success'|'error'>('idle'),[message,setMessage]=useState('');
  async function submit(event:FormEvent<HTMLFormElement>) {
    event.preventDefault();if(state==='busy') return;
    const form=event.currentTarget,body=new FormData(form);setState('busy');setMessage('');
    try {
      const response=await fetch('/api/waitlist',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({email:body.get('email'),website:body.get('website'),consent:body.get('consent')==='yes'}),signal:AbortSignal.timeout(12_000)});
      if(response.status===202){setState('success');form.reset();return;}
      setMessage(response.status===429 ? 'Please try again in a minute.' : response.status===400 ? 'Check your email and the consent box.' : 'The waitlist is temporarily unavailable. Please try again later.');setState('error');
    } catch {setMessage('We could not save your request. Please try again.');setState('error');}
  }
  if(state==='success') return <div className={styles.success} role="status"><strong>You’re on the list.</strong><p>We’ll use your email to let you know when access opens.</p><a href="#backtest-demo">Explore the demo →</a></div>;
  return <form className={styles.form} onSubmit={submit}>
    <label htmlFor="waitlist-email">Email address</label>
    <div className={styles.row}><input id="waitlist-email" name="email" type="email" maxLength={254} required autoComplete="email" placeholder="you@example.com" disabled={state==='busy'} />
    <button className={styles.button} disabled={state==='busy'}>{state==='busy' ? 'Saving…' : 'Join the waitlist →'}</button></div>
    <div className={styles.trap} aria-hidden="true"><label htmlFor="waitlist-website">Leave this field empty</label><input id="waitlist-website" name="website" tabIndex={-1} autoComplete="off" /></div>
    <label className={styles.consent}><input type="checkbox" name="consent" value="yes" required disabled={state==='busy'} />I agree to receive an access update. My email stays private and is not sold.</label>
    <p className={styles.notice}>Private preview. Joining does not create an account or grant dashboard access. No payment required.</p>
    {state==='error' && <p role="alert" className={styles.error}>{message}</p>}
  </form>;
}
