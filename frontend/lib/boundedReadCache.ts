/** Per-process cache for public read models. No user/session data belongs here. */
export class BoundedReadCache<T> {
  private values=new Map<string,{value:T;expires:number;bytes:number}>();
  private pending=new Map<string,Promise<T>>();
  private bytes=0;
  private readonly options:{maxEntries:number;maxBytes:number;maxEntryBytes:number;maxPending:number};
  private readonly clock:()=>number;
  constructor(options:{maxEntries:number;maxBytes:number;maxEntryBytes:number;maxPending:number},clock=Date.now) {
    if(Object.values(options).some(value=>!Number.isSafeInteger(value) || value<=0))throw new Error("Invalid cache bounds");
    this.options=options;this.clock=clock;
  }
  get size(){return this.values.size;}
  get pendingCount(){return this.pending.size;}
  get byteSize(){return this.bytes;}
  private remove(key:string){const entry=this.values.get(key);if(entry){this.bytes-=entry.bytes;this.values.delete(key);}}
  async read(key:string,ttlMs:number,load:()=>Promise<T>):Promise<T> {
    if(key.length>1024 || !Number.isFinite(ttlMs) || ttlMs<=0) throw new Error('Invalid cache request');
    const now=this.clock();
    for(const [id,entry] of this.values) if(entry.expires<=now)this.remove(id);
    const hit=this.values.get(key);
    if(hit){this.values.delete(key);this.values.set(key,hit);return structuredClone(hit.value);}
    const waiting=this.pending.get(key);
    if(waiting)return structuredClone(await waiting);
    if(this.pending.size>=this.options.maxPending)throw new Error('Service busy');
    const work=Promise.resolve().then(load).then(value=>{
      // Successful public results only. Failures never poison future requests.
      const encoded=JSON.stringify(value);
      const bytes=encoded===undefined ? Infinity : new TextEncoder().encode(encoded).byteLength;
      if(bytes<=this.options.maxEntryBytes && bytes<=this.options.maxBytes && this.options.maxEntries>0){
        while(this.values.size>=this.options.maxEntries || this.bytes+bytes>this.options.maxBytes){
          this.remove(this.values.keys().next().value!);
        }
        this.values.set(key,{value:structuredClone(value),expires:this.clock()+ttlMs,bytes});this.bytes+=bytes;
      }
      return value;
    });
    this.pending.set(key,work);
    try{return structuredClone(await work);}finally{if(this.pending.get(key)===work)this.pending.delete(key);}
  }
}
