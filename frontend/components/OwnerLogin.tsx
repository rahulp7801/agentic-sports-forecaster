'use client';
import {useState} from 'react';
import {signIn} from 'next-auth/react';
import styles from './WaitlistForm.module.css';
export default function OwnerLogin({configured}:{configured:boolean}) {
  const [busy,setBusy]=useState(false),[failed,setFailed]=useState(false);
  return <><button className={styles.button} disabled={!configured || busy} onClick={async()=>{
    setBusy(true);setFailed(false);
    try {await signIn('github',{callbackUrl:'/terminal'});} catch {setBusy(false);setFailed(true);}
  }}>{busy ? 'Opening GitHub…' : 'Continue with GitHub'}</button>
  {!configured && <p>Owner sign-in is being configured. The private dashboard remains locked.</p>}
  {failed && <p role="alert">Sign-in could not start. Please try again.</p>}</>;
}
