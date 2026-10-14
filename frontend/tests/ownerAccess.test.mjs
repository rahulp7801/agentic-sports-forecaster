import test from 'node:test';
import assert from 'node:assert/strict';
import {randomBytes} from 'node:crypto';
import {encode} from 'next-auth/jwt';
import {isOwner,requireOwner} from '../lib/ownerAccess.ts';
import {authConfigured,ownerAccount,ownerToken,ownerRedirect,OWNER_GITHUB_ID,SESSION_SECONDS,PRODUCTION_ORIGIN} from '../lib/ownerPolicy.ts';
const secret=randomBytes(32).toString('hex');
Object.assign(process.env,{NEXTAUTH_SECRET:secret,NEXTAUTH_URL:PRODUCTION_ORIGIN,GITHUB_CLIENT_ID:'fixture-client',GITHUB_CLIENT_SECRET:'fixture-secret'});
const valid=()=>({sub:OWNER_GITHUB_ID,ownerId:OWNER_GITHUB_ID,ownerIssuedAt:Date.now()});
const cookies=async(token,key=secret,maxAge=SESSION_SECONDS)=>new Headers({cookie:'__Secure-next-auth.session-token='+await encode({token,secret:key,maxAge})});
test('GitHub owner identity is immutable provider ID, never a username or another provider',()=>{
 assert.equal(ownerAccount({provider:'github',providerAccountId:OWNER_GITHUB_ID}),true);
 for(const account of [null,{provider:'github',providerAccountId:'rahulp7801'},{provider:'github',providerAccountId:'1'},{provider:'google',providerAccountId:OWNER_GITHUB_ID}]) assert.equal(ownerAccount(account),false);
 assert.equal(authConfigured({...process.env,NEXTAUTH_SECRET:undefined}),false);
 assert.equal(authConfigured({...process.env,NEXTAUTH_SECRET:'short'}),false);
 assert.equal(authConfigured({...process.env,NEXTAUTH_URL:'https://attacker.invalid'}),false);
});
test('real encrypted owner cookie is accepted; missing, forged, expired, nonowner and legacy cookies are denied',async()=>{
 assert.equal(await isOwner(await cookies(valid())),true);
 for(const token of [{...valid(),ownerId:'1'},{...valid(),sub:'1'},{...valid(),ownerIssuedAt:Date.now()-SESSION_SECONDS*1000},{...valid(),ownerIssuedAt:Date.now()+60000},{sub:OWNER_GITHUB_ID}]) assert.equal(await isOwner(await cookies(token)),false);
 assert.equal(await isOwner(await cookies(valid(),randomBytes(32).toString('hex'))),false);
 assert.equal(await isOwner(await cookies(valid(),secret,-60)),false);
 assert.equal(await isOwner(new Headers({cookie:'__Secure-next-auth.session-token=invalid'})),false);
 assert.equal(await isOwner(new Headers({authorization:'Bearer '+await encode({token:valid(),secret})})),false);
 assert.equal(await isOwner(new Headers()),false);
 const previous=process.env.GITHUB_CLIENT_SECRET;delete process.env.GITHUB_CLIENT_SECRET;
 assert.equal(await isOwner(await cookies(valid())),false);process.env.GITHUB_CLIENT_SECRET=previous;
 assert.equal(ownerToken({...valid(),ownerIssuedAt:NaN}),false);
 const denied=await requireOwner(new Request(PRODUCTION_ORIGIN+'/api/signals'));
 assert.equal(denied.status,401);for(const k of ['Cache-Control','CDN-Cache-Control','Vercel-CDN-Cache-Control'])assert.equal(denied.headers.get(k),'no-store');
});

test('login and logout redirect only to fixed same-origin application destinations',()=>{
 assert.equal(ownerRedirect('/',PRODUCTION_ORIGIN),PRODUCTION_ORIGIN+'/');
 assert.equal(ownerRedirect('/terminal',PRODUCTION_ORIGIN),PRODUCTION_ORIGIN+'/terminal');
 for(const url of ['https://attacker.invalid','//attacker.invalid','/api/auth/session','javascript:alert(1)','/terminal/other'])assert.equal(ownerRedirect(url,PRODUCTION_ORIGIN),PRODUCTION_ORIGIN+'/terminal');
});


test('release diagnostic headers never grant application owner access',async()=>{
 const headers=new Headers({'x-private-release-probe':'f'.repeat(64),'x-owner-id':OWNER_GITHUB_ID});
 assert.equal(await isOwner(headers),false);
 const denied=await requireOwner(new Request(PRODUCTION_ORIGIN+'/api/signals',{headers}));assert.equal(denied.status,401);
 const nonowner=await cookies({...valid(),ownerId:'1'});nonowner.set('x-private-release-probe','f'.repeat(64));assert.equal(await isOwner(nonowner),false);
 const owner=await cookies(valid());owner.set('x-private-release-probe','f'.repeat(64));assert.equal(await isOwner(owner),true);
});
