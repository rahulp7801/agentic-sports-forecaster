'use client';
import {useEffect,useMemo,useState} from 'react';
import type {EVSignal} from '@/lib/types';
import {pickCardFormRequest,pickCardFormSnapshot,pickCardFormSummary} from '@/lib/pickCardForm';

export function usePickCardForm(signal:EVSignal) {
  const request=pickCardFormRequest(signal);
  const key=JSON.stringify([request,pickCardFormSnapshot(signal)]);
  const capturedSignal=useMemo(()=>JSON.parse(key)[1] as EVSignal,[key]);
  const [result,setResult]=useState<{key:string;summary:string}|null>(null);
  useEffect(()=>{
    if(!request) return;
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
  },[key,request,capturedSignal]);
  return !request ? 'Recorded current-team form is unavailable.'
    : result?.key===key ? result.summary : 'Checking recorded current-team form...';
}
