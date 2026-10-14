import {NextRequest} from 'next/server.js';
import {getToken} from 'next-auth/jwt';
import {authConfigured,ownerToken} from './ownerPolicy.ts';
import {NO_STORE_HEADERS} from './publicCache.ts';

/** Verify the encrypted session again inside each handler; proxy is not the data boundary. */
export async function isOwner(headers: Headers) {
  if(!authConfigured()) return false;
  try {
    const token=await getToken({req:new NextRequest('https://agentic-ev-analytics-platform.vercel.app',{headers:{cookie:headers.get('cookie') ?? ''}}),
      secret:process.env.NEXTAUTH_SECRET,secureCookie:process.env.NEXTAUTH_URL?.startsWith('https://')});
    return ownerToken(token);
  } catch {return false;}
}

export async function requireOwner(request:Request) {
  return await isOwner(request.headers) ? null : Response.json(
    {error:'Owner authentication required.'},{status:401,headers:NO_STORE_HEADERS});
}
