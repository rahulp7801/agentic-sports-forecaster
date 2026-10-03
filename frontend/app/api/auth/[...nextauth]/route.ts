import NextAuth from 'next-auth';
import type {NextRequest} from 'next/server';
import {authOptions} from '@/lib/authOptions';
import {authConfigured} from '@/lib/ownerPolicy';
import {NO_STORE_HEADERS} from '@/lib/publicCache';
export const dynamic='force-dynamic';
const handler=NextAuth(authOptions);
type Context={params:Promise<{nextauth:string[]}>};
async function auth(request:NextRequest,context:Context) {
  if(!authConfigured()) return Response.json({error:'Owner sign-in is not configured.'},{status:503,headers:NO_STORE_HEADERS});
  const response=await handler(request,context);
  for(const [key,value] of Object.entries(NO_STORE_HEADERS)) response.headers.set(key,value);
  return response;
}
export {auth as GET,auth as POST};
