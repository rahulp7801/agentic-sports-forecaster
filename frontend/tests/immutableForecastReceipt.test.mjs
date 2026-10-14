import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {Buffer} from 'node:buffer';
import {readImmutableForecastReceipt} from '../lib/immutableForecastReceipt.ts';

const id='a'.repeat(64),stamp='2026-10-14T03:00:00.123456Z';
const hash=text=>createHash('sha256').update(Buffer.from(text,'utf8')).digest('hex');
function receipt(payload='{ "z": 3, "player": "Athlète 🏈", "nested": {"second":2,"first":1}, "list":[true,null,2.0] }') {
  return {id,scan_id:'retained-scan-20261014',payload_sha256:hash(payload),recorded_at:stamp,payload};
}
const expected=value=>({id:value.id,payload_sha256:value.payload_sha256});

test('private receipt hashes original UTF-8 TEXT and retains a cloned normalized payload plus exact microseconds',()=>{
  const input=receipt(),output=readImmutableForecastReceipt(input,expected(input));
  assert.deepEqual(output,{id,scan_id:input.scan_id,payload_sha256:input.payload_sha256,recorded_at:stamp,
    payload:{list:[true,null,2],nested:{first:1,second:2},player:'Athlète 🏈',z:3}});
  assert.notEqual(hash(JSON.stringify(output.payload)),input.payload_sha256);
  assert.deepEqual(Object.keys(output),['id','scan_id','payload_sha256','recorded_at','payload']);
  output.payload.nested.first=99;
  assert.equal(JSON.parse(input.payload).nested.first,1);
  const decomposed=receipt('{"name":"e\\u0301","unknown_private_parameters":{"opaque":true}}');
  const retained=readImmutableForecastReceipt(decomposed,expected(decomposed));
  assert.equal(retained.payload.name,'e\u0301');
  assert.deepEqual(retained.payload.unknown_private_parameters,{opaque:true},'Private payload keys are retained only for private readers');
});

test('exact expected identity/hash and the five-field database receipt cannot be replaced by candidates or legacy exports',()=>{
  const input=receipt();
  for(const patch of [{id:'b'.repeat(64)},{payload_sha256:'b'.repeat(64)},{id:'A'.repeat(64)},
    {payload_sha256:'A'.repeat(64)},{scan_id:''},{scan_id:'bad\nscan'},{scan_id:'x'.repeat(81)},
    {recorded_at:null,payload_sha256:null},{recorded_at:null},{payload_sha256:null},
    {payload:JSON.parse(input.payload)},{candidate:true},{outcome:'win'},{original_payload:input.payload}])
    assert.equal(readImmutableForecastReceipt({...input,...patch},expected(input)),null);
  assert.equal(readImmutableForecastReceipt(input,{id:'b'.repeat(64),payload_sha256:input.payload_sha256}),null);
  assert.equal(readImmutableForecastReceipt(input,{id,payload_sha256:'b'.repeat(64)}),null);
  assert.equal(readImmutableForecastReceipt(input),null);
  assert.equal(readImmutableForecastReceipt(input,{...expected(input),proof:'caller supplied'}),null);
  for(const field of Object.keys(input)) {const missing={...input};delete missing[field];assert.equal(readImmutableForecastReceipt(missing,expected(input)),null);}
  const scan={...input,scan_id:' retained scan '};assert.equal(readImmutableForecastReceipt(scan,expected(scan)).scan_id,scan.scan_id);
});

test('spacing, key order and Unicode encoding changes cannot reuse the original TEXT commitment',()=>{
  const original=receipt('{"player":"Athlète","a":1,"b":2}');
  for(const text of ['{"player":"Athlète", "a":1,"b":2}',
    '{"b":2,"a":1,"player":"Athlète"}','{"player":"Athl\\u00e8te","a":1,"b":2}',original.payload+'\n']) {
    assert.deepEqual(JSON.parse(text),JSON.parse(original.payload));
    assert.equal(readImmutableForecastReceipt({...original,payload:text},expected(original)),null);
  }
});

test('hash verification precedes parsing and malformed JSON never exposes its raw error',t=>{
  const originalParse=JSON.parse;let parsed=0;
  t.mock.method(JSON,'parse',(...args)=>{parsed++;return originalParse(...args);});
  const malformed=receipt('{"private_credentials":"synthetic-only",');
  assert.equal(readImmutableForecastReceipt({...malformed,payload_sha256:'b'.repeat(64)},
    {id,payload_sha256:'b'.repeat(64)}),null);
  assert.equal(parsed,0,'A mismatched raw hash must not reach JSON parsing');
  assert.doesNotThrow(()=>assert.equal(readImmutableForecastReceipt(malformed,expected(malformed)),null));
  assert.equal(parsed,1);
});

test('canonical UTC receipts preserve microsecond distinctions and reject pg Date rounding or invalid timestamp forms',()=>{
  const input=receipt();
  for(const recorded_at of ['2026-10-14T03:00:00.000001Z','2026-10-14T03:00:00.000002Z',
    '2024-02-29T23:59:59.999999Z','2099-01-01T00:00:00.000000Z']) {
    const output=readImmutableForecastReceipt({...input,recorded_at},expected(input));
    assert.equal(output.recorded_at,recorded_at,'Receipt reader does not qualify chronology or round microseconds');
  }
  const first='2026-10-14T03:00:00.000001Z',second='2026-10-14T03:00:00.000002Z';
  assert.equal(Date.parse(first),Date.parse(second));
  assert.notEqual(readImmutableForecastReceipt({...input,recorded_at:first},expected(input)).recorded_at,
    readImmutableForecastReceipt({...input,recorded_at:second},expected(input)).recorded_at);
  for(const recorded_at of [new Date(stamp),'2026-10-14T03:00:00.123Z','2026-10-14T03:00:00Z',
    '2026-10-14T03:00:00.1234567Z','2026-10-14T03:00:00.123456+00:00',
    '2026-10-14T03:00:00.123456','2026-02-30T03:00:00.123456Z','0000-10-14T03:00:00.123456Z',
    '2026-10-14T24:00:00.123456Z','2026-10-14T03:60:00.123456Z','2026-10-14T03:00:60.123456Z'])
    assert.equal(readImmutableForecastReceipt({...input,recorded_at},expected(input)),null);
});

test('raw payload must be a safe plain JSON object with finite and well-formed values',()=>{
  for(const text of ['null','[]','"text"','1','true','{"value":1e999}','{"value":NaN}',
    '{"value":Infinity}','{"value":"\\ud800"}','{"value":"\\udc00"}',
    '{"value":"'+String.fromCharCode(0xd800)+'"}']) {
    const value=receipt(text);assert.equal(readImmutableForecastReceipt(value,expected(value)),null);
  }
  const emoji=receipt('{"value":"\\ud83c\\udfc8"}');
  assert.equal(readImmutableForecastReceipt(emoji,expected(emoji)).payload.value,'🏈');
  const prototype=receipt('{"__proto__":{"polluted":true},"constructor":{"prototype":{"polluted":true}}}');
  const output=readImmutableForecastReceipt(prototype,expected(prototype));
  assert.equal(Object.getPrototypeOf(output.payload),Object.prototype);
  assert.ok(Object.hasOwn(output.payload,'__proto__'));assert.equal(output.payload.__proto__.polluted,true);
  assert.equal({}.polluted,undefined);
});

test('TEXT bytes, parsed nodes and depth have exact bounded admission',()=>{
  const prefix='{"padding":"',suffix='"}',maximum=1024*1024;
  const atLimit=receipt(prefix+'x'.repeat(maximum-Buffer.byteLength(prefix+suffix))+suffix);
  assert.ok(readImmutableForecastReceipt(atLimit,expected(atLimit)));
  const oversized=receipt(atLimit.payload+' ');assert.equal(readImmutableForecastReceipt(oversized,expected(oversized)),null);
  const multibyte=receipt(prefix+'🏈'.repeat(262144)+suffix);
  assert.ok(multibyte.payload.length<maximum);assert.ok(Buffer.byteLength(multibyte.payload)>maximum);
  assert.equal(readImmutableForecastReceipt(multibyte,expected(multibyte)),null);
  const atNodes=receipt('{"nodes":['+Array(49998).fill('null').join(',')+']}');
  assert.ok(readImmutableForecastReceipt(atNodes,expected(atNodes)));
  const overNodes=receipt('{"nodes":['+Array(49999).fill('null').join(',')+']}');
  assert.equal(readImmutableForecastReceipt(overNodes,expected(overNodes)),null);
  const atDepth=receipt('{"next":'.repeat(32)+'null'+'}'.repeat(32));
  assert.ok(readImmutableForecastReceipt(atDepth,expected(atDepth)));
  const overDepth=receipt('{"next":'.repeat(33)+'null'+'}'.repeat(33));
  assert.equal(readImmutableForecastReceipt(overDepth,expected(overDepth)),null);
});

test('receipt and expected-binding getters or exotic containers cannot execute',()=>{
  let accessed=0;const input=receipt(),getter={...input};
  Object.defineProperty(getter,'payload',{enumerable:true,get(){accessed++;return input.payload;}});
  assert.equal(readImmutableForecastReceipt(getter,expected(input)),null);
  const getterExpected={...expected(input)};
  Object.defineProperty(getterExpected,'id',{enumerable:true,get(){accessed++;return id;}});
  assert.equal(readImmutableForecastReceipt(input,getterExpected),null);
  const symbol={...input};symbol[Symbol('hidden')]='private';assert.equal(readImmutableForecastReceipt(symbol,expected(input)),null);
  const hidden={...input};Object.defineProperty(hidden,'hidden',{value:'private'});
  assert.equal(readImmutableForecastReceipt(hidden,expected(input)),null);
  class Row {constructor(){Object.assign(this,input);}}
  assert.equal(readImmutableForecastReceipt(new Row(),expected(input)),null);assert.equal(accessed,0);
});
