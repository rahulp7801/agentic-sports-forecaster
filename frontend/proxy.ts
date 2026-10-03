import {isOwner} from './lib/ownerAccess';
import { NextRequest, NextResponse } from 'next/server';
import {publicRequest} from './lib/publicRequest';
import {NO_STORE_HEADERS} from './lib/publicCache';

export async function proxy(request: NextRequest) {
  const status=publicRequest(request);
  if(status) return NextResponse.json({error:'Request rejected.'},{status,headers:NO_STORE_HEADERS});
  const path=request.nextUrl.pathname;
  const publicApi=path.startsWith('/api/auth/') || path==='/api/waitlist';
  if((path.startsWith('/api/') && !publicApi) || path==='/terminal' || path.startsWith('/terminal/') || path.endsWith('.json')) {
    if(!await isOwner(request.headers)) {
      if(path.startsWith('/api/') || path.endsWith('.json')) return NextResponse.json({error:'Owner authentication required.'},{status:401,headers:NO_STORE_HEADERS});
      return NextResponse.redirect(new URL('/login',request.url),{headers:NO_STORE_HEADERS});
    }
  }
  if(path.startsWith('/api/')) return NextResponse.next({headers:NO_STORE_HEADERS});
  const nonce = Buffer.from(crypto.randomUUID()).toString('base64');
  const development = process.env.NODE_ENV === 'development';
  const policy = `
    default-src 'self';
    script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${development ? " 'unsafe-eval'" : ''};
    style-src 'self' 'nonce-${nonce}';
    style-src-attr 'unsafe-inline';
    img-src 'self' blob: data: https://a.espncdn.com;
    font-src 'self';
    connect-src 'self';
    worker-src 'self' blob:;
    media-src 'none';
    object-src 'none';
    base-uri 'self';
    form-action 'self';
    frame-src 'none';
    frame-ancestors 'none';
    manifest-src 'self';
    upgrade-insecure-requests;
  `.replace(/\s{2,}/g, ' ').trim();

  const requestHeaders = new Headers(request.headers);
  requestHeaders.set('x-nonce', nonce);
  requestHeaders.set('Content-Security-Policy', policy);

  const response = NextResponse.next({ request: { headers: requestHeaders } });
  response.headers.set('Content-Security-Policy', policy);
  for(const [key,value] of Object.entries(NO_STORE_HEADERS)) response.headers.set(key,value);
  return response;
}

export const config = {
  matcher: [{
    source: '/((?!_next/static|_next/image|favicon.ico).*)',
  }],
};
