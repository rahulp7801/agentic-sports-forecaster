import test from 'node:test';
import assert from 'node:assert/strict';
import { Client } from 'pg';
import { databaseConfig } from '../lib/databaseConfig.ts';

test('custom CA preserves credentials and enforces certificate and hostname verification', () => {
  const value='postgresql+psycopg://reader.project:p%40ss@pooler.example:5432/postgres?sslmode=verify-full';
  const config=databaseConfig(value,'CA contents');
  const parsed=new URL(config.connectionString);
  assert.equal(parsed.hostname,'pooler.example');
  assert.equal(parsed.password,'p%40ss');
  assert.equal(parsed.username,'reader.project');
  assert.equal(parsed.searchParams.has('sslmode'),false);
  assert.deepEqual(config.ssl,{ca:'CA contents',rejectUnauthorized:true});
  assert.throws(()=>databaseConfig(value.replace('verify-full','require'),'CA'),/verify-full/);
  assert.throws(()=>databaseConfig(undefined),/unavailable/);
  assert.equal(new URL(databaseConfig(value).connectionString).searchParams.get('sslmode'),'verify-full');
});

test('hosted connections cannot silently use plaintext or skip certificate verification',()=>{
  const value='postgresql://reader:synthetic@pooler.example/postgres';
  for(const suffix of ['', '?sslmode=disable','?sslmode=require','?sslmode=no-verify']) {
    assert.throws(()=>databaseConfig(value+suffix,undefined,true),/verification/);
  }
  assert.ok(databaseConfig(value+'?sslmode=verify-full','Public CA',true).ssl.rejectUnauthorized);
  assert.ok(databaseConfig('postgresql://localhost/sportsbet').connectionString);
});


test('hosted TLS rejects duplicate modes before pg can select a weaker last value',()=>{
  const value='postgresql://reader:synthetic@pooler.example/postgres?sslmode=verify-full';
  for(const suffix of ['&sslmode=disable','&sslmode=no-verify',
    '&sslmode=require&uselibpqcompat=true','&sslmode=verify-full',
    '&ssl%6dode=disable']) {
    // Test the real driver's parsing without opening a connection.
    for(const ca of [undefined,'CA contents']) {
      assert.throws(()=>new Client(databaseConfig(value+suffix,ca,true)),/verification|verify-full/);
    }
  }
  assert.throws(()=>databaseConfig(value+'&sslmode=disable','CA contents'),/verify-full/);
});

test('valid hosted settings retain effective certificate verification in the real driver',()=>{
  const value='postgresql://reader:synthetic@pooler.example/postgres?sslmode=verify-full';
  for(const ca of [undefined,'CA contents']) {
    for(const suffix of ['','&uselibpqcompat=true']) {
      const client=new Client(databaseConfig(value+suffix,ca,true));
      assert.ok(client.connectionParameters.ssl);
      assert.notEqual(client.connectionParameters.ssl.rejectUnauthorized,false);
      assert.equal(client.connectionParameters.ssl.checkServerIdentity,undefined);
      if(ca) assert.equal(client.connectionParameters.ssl.ca,ca);
    }
  }
  const local=new Client(databaseConfig('postgresql://localhost/sportsbet?sslmode=disable'));
  assert.equal(local.connectionParameters.ssl,false);
});
