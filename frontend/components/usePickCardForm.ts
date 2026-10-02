'use client';
import {useEffect,useState} from 'react';
import type {EVSignal} from '@/lib/types';
import {pickCardFormRequest,pickCardFormSummary} from '@/lib/pickCardForm';

export function usePickCardForm(signal:EVSignal) {
  const request=pickCardFormRequest(signal);
  const {player,player_id:playerId,sport,forecast_cutoff:cutoff,snapped_at:quote,
    prop_type:prop,line,direction}=signal;
  const rosterStatus=signal.availability?.status;
  const rosterConfirmed=signal.availability?.roster_confirmed;
  const team=signal.availability?.team;
  const key=JSON.stringify([request,player,playerId,sport,cutoff,quote,prop,line,direction,
    rosterStatus,rosterConfirmed,team]);
  const [result,setResult]=useState<{key:string;summary:string}|null>(null);
  useEffect(()=>{
    if(!request) return;
    const capturedSignal={player,player_id:playerId,sport,forecast_cutoff:cutoff,snapped_at:quote,
      prop_type:prop,line,direction,availability:{status:rosterStatus,roster_confirmed:rosterConfirmed,team}} as EVSignal;
    const controller=new AbortController();
    fetch(request,{cache:'no-store',signal:AbortSignal.any([controller.signal,AbortSignal.timeout(15_000)])})
      .then(async response=>{
        if(!response.ok) throw new Error('History unavailable');
        return response.json();
      })
      .then(data=>{
        if(!controller.signal.aborted) setResult({key,summary:pickCardFormSummary(data.logs,capturedSignal)});
      })
      .catch(()=>{
        if(!controller.signal.aborted) setResult({key,summary:'Recorded current-team form is unavailable.'});
      });
    return ()=>controller.abort();
  },[key,request,player,playerId,sport,cutoff,quote,prop,line,direction,
    rosterStatus,rosterConfirmed,team]);
  return !request ? 'Recorded current-team form is unavailable.'
    : result?.key===key ? result.summary : 'Checking recorded current-team form...';
}
