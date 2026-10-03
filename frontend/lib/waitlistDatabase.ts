import {Client} from 'pg';
import {databaseConfig} from './databaseConfig.ts';
import {queryWithClient} from './queryWithClient.ts';
/** Separate credentials can execute one bounded write function, and cannot read the dashboard. */
export async function writeWaitlist(email:string) {
  const url=process.env.WAITLIST_DATABASE_URL;
  if(!url || url===process.env.DATABASE_URL) throw new Error('Service unavailable');
  const client=new Client({...databaseConfig(url,process.env.DATABASE_SSL_CA,process.env.VERCEL==='1'),
    connectionTimeoutMillis:5000,statement_timeout:5000,query_timeout:6000});
  const result=await queryWithClient<{accepted:boolean}>(client,'SELECT private_access.join_waitlist($1) AS accepted',[email]);
  return result.rows[0]?.accepted===true;
}
