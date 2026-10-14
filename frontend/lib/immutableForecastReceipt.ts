import {createHash} from 'node:crypto';
import {Buffer} from 'node:buffer';

export type ImmutableForecastJson=null|boolean|number|string|ImmutableForecastJson[]|{[key:string]:ImmutableForecastJson};
export type ImmutableForecastPayload={[key:string]:ImmutableForecastJson};
export type ImmutableForecastReceipt={id:string;scan_id:string;payload_sha256:string;
  recorded_at:string;payload:ImmutableForecastPayload};
export type ImmutableForecastReceiptExpected={id:string;payload_sha256:string};

const TEXT_BYTES=1024*1024;
const JSON_NODES=50000;
const JSON_DEPTH=32;
const RECEIPT_KEYS=['id','scan_id','payload_sha256','recorded_at','payload'];
const EXPECTED_KEYS=['id','payload_sha256'];

function invalid():never {throw Error('Invalid immutable forecast receipt');}
function plain(value:unknown):Record<string,unknown> {
  if(!value||typeof value!=='object'||Array.isArray(value)) return invalid();
  const prototype=Object.getPrototypeOf(value),descriptors=Object.getOwnPropertyDescriptors(value);
  if(prototype!==Object.prototype&&prototype!==null||Object.getOwnPropertySymbols(value).length
    ||Object.values(descriptors).some(item=>!item.enumerable||!Object.hasOwn(item,'value'))) return invalid();
  return value as Record<string,unknown>;
}
function exact(value:unknown,keys:readonly string[]) {
  const source=plain(value);
  if(Object.keys(source).length!==keys.length||keys.some(key=>!Object.hasOwn(source,key))) return invalid();
  return source;
}
function digest(value:unknown):string {
  return typeof value==='string'&&/^[a-f0-9]{64}$/.test(value) ? value : invalid();
}
function scanId(value:unknown):string {
  return typeof value==='string'&&Boolean(value.trim())&&value.length<=80&&!/[\u0000-\u001f]/.test(value)
    ? value : invalid();
}
function wellFormed(value:string):boolean {
  for(let index=0;index<value.length;index++) {
    const code=value.charCodeAt(index);
    if(code>=0xd800&&code<=0xdbff) {
      const next=value.charCodeAt(++index);
      if(!(next>=0xdc00&&next<=0xdfff)) return false;
    } else if(code>=0xdc00&&code<=0xdfff) return false;
  }
  return true;
}
function recordedAt(value:unknown):string {
  if(typeof value!=='string'||!/^\d{4}-\d{2}-\d{2}T(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d\.\d{6}Z$/.test(value)) return invalid();
  const day=value.slice(0,10),parsed=new Date(day+'T00:00:00Z');
  if(day<'0001-01-01'||!Number.isFinite(parsed.valueOf())||parsed.toISOString().slice(0,10)!==day) return invalid();
  // Retain all six digits. Ordering this receipt belongs to a microsecond-aware resolver.
  return value;
}
function normalizedPayload(value:unknown):ImmutableForecastPayload {
  let nodes=0;
  const normalize=(item:unknown,depth:number):ImmutableForecastJson=>{
    if(++nodes>JSON_NODES||depth>JSON_DEPTH) return invalid();
    if(item===null||typeof item==='boolean') return item;
    if(typeof item==='string') return wellFormed(item) ? item : invalid();
    if(typeof item==='number') return Number.isFinite(item) ? item : invalid();
    if(Array.isArray(item)) {
      const descriptors=Object.getOwnPropertyDescriptors(item);
      if(Object.getPrototypeOf(item)!==Array.prototype||item.length>JSON_NODES
        ||Object.getOwnPropertySymbols(item).length||Object.keys(descriptors).length!==item.length+1
        ||Object.keys(item).length!==item.length
        ||Object.keys(item).some((key,index)=>key!==String(index))
        ||Object.entries(descriptors).some(([key,entry])=>key!=='length'
          &&(!entry.enumerable||!Object.hasOwn(entry,'value')))) return invalid();
      return item.map(entry=>normalize(entry,depth+1));
    }
    const source=plain(item);
    const entries=Object.keys(source).sort().map(key=>{
      if(!wellFormed(key)) return invalid();
      return [key,normalize(source[key],depth+1)] as const;
    });
    return Object.fromEntries(entries);
  };
  plain(value);
  return normalize(value,0) as ImmutableForecastPayload;
}

/** PRIVATE: validate a trusted ledger TEXT receipt, never a candidate/export or a public response. */
export function readImmutableForecastReceipt(value:unknown,expected:ImmutableForecastReceiptExpected):ImmutableForecastReceipt|null {
  try {
    const source=exact(value,RECEIPT_KEYS),wanted=exact(expected,EXPECTED_KEYS);
    const id=digest(source.id),payload_sha256=digest(source.payload_sha256);
    if(id!==digest(wanted.id)||payload_sha256!==digest(wanted.payload_sha256)) return null;
    const scan_id=scanId(source.scan_id),recorded_at=recordedAt(source.recorded_at);
    if(typeof source.payload!=='string'||source.payload.length>TEXT_BYTES||!wellFormed(source.payload)) return null;
    const bytes=Buffer.from(source.payload,'utf8');
    if(bytes.length>TEXT_BYTES||createHash('sha256').update(bytes).digest('hex')!==payload_sha256) return null;
    // PostgreSQL schema0039 commits the original TEXT bytes, including spacing and escapes.
    // Hash verification must precede parsing or any key sorting/normalization.
    const payload=normalizedPayload(JSON.parse(source.payload) as unknown);
    return {id,scan_id,payload_sha256,recorded_at,payload};
  } catch {return null;}
}
